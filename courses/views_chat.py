# courses/views_chat.py
"""Endpoints de l'assistant pédagogique IA (chat par bloc de cours).

Sécurité :
  - l'identité vient TOUJOURS de `request.user` (jamais d'un id transmis) ;
  - un apprenant doit être inscrit au cours et le bloc doit être disponible ;
  - une conversation n'est accessible qu'à son propriétaire ;
  - les messages sont limités en taille et le débit est throttlé.
"""
from __future__ import annotations

import threading
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.rbac import display_role
from users.access_control import get_own_apprenant
from users.views import api_error, api_success

from .models import BlocContenu, ConversationTuteur, MessageTuteur
from .publication import bloc_disponible
from .services import chat_tuteur
from .throttles import ChatTuteurThrottle
from .utils import _get_apprenant_cours_ids

MAX_MESSAGE = chat_tuteur.MAX_QUESTION
EN_COURS_TTL_SECONDES = 90


# ── Sérialisation légère ────────────────────────────────────────────────────

def _conv_data(conv: ConversationTuteur) -> dict:
    return {
        "id": conv.id,
        "bloc": conv.bloc_id,
        "cours": conv.cours_id,
        "titre": conv.titre,
        "statut": conv.statut,
        "cree_le": conv.cree_le,
        "maj_le": conv.maj_le,
    }


def _msg_data(message: MessageTuteur) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "contenu": message.contenu,
        "statut": message.statut,
        "erreur": message.erreur,
        "duree_ms": message.duree_ms,
        "cree_le": message.cree_le,
    }


def _messages_data(conv: ConversationTuteur) -> list:
    return [_msg_data(m) for m in conv.messages.all()[:300]]


# ── Contrôles d'accès ───────────────────────────────────────────────────────

def _role(user) -> str:
    return (display_role(user) or "").strip()


def _bloc_complet(bloc_id: int) -> BlocContenu:
    return get_object_or_404(
        BlocContenu.objects.select_related("sequence__module__cours"),
        pk=bloc_id,
    )


def _acces_bloc(user, bloc: BlocContenu):
    """Retourne (apprenant, None, 200) ou (None, message, code)."""
    from core.tenant import default_institution_id  # import tardif (patchable en tests)

    role = _role(user)
    cours = bloc.sequence.module.cours

    if role == "Apprenant":
        apprenant = get_own_apprenant(user)
        if apprenant is None:
            return None, "Profil apprenant introuvable.", status.HTTP_403_FORBIDDEN
        if not bloc_disponible(bloc):
            return None, "Ce contenu n'est pas encore disponible.", status.HTTP_403_FORBIDDEN
        inscrits = set(_get_apprenant_cours_ids(user, default_institution_id()))
        if cours.id not in inscrits:
            return None, "Vous n'êtes pas inscrit à ce cours.", status.HTTP_403_FORBIDDEN
        return apprenant, None, status.HTTP_200_OK

    if role in ("Admin", "SuperAdmin", "Formateur", "Responsable"):
        return None, "L'assistant pédagogique est réservé aux apprenants.", status.HTTP_403_FORBIDDEN

    return None, "Accès refusé.", status.HTTP_403_FORBIDDEN


def _conversation_active(apprenant, bloc: BlocContenu) -> ConversationTuteur:
    conv = (
        ConversationTuteur.objects
        .filter(apprenant=apprenant, bloc=bloc, statut="active")
        .order_by("-maj_le")
        .first()
    )
    if conv is not None:
        return conv

    cours = bloc.sequence.module.cours
    institution = getattr(cours, "institution", None) or getattr(bloc.sequence, "institution", None)
    return ConversationTuteur.objects.create(
        apprenant=apprenant,
        bloc=bloc,
        cours=cours,
        institution=institution,
        titre=(bloc.titre or "")[:255],
        statut="active",
    )


def _conversation_autorisee(user, pk: int):
    """Retourne (apprenant, conversation) ou lève/renvoie une erreur 404."""
    conv = get_object_or_404(
        ConversationTuteur.objects.select_related("bloc__sequence__module__cours"),
        pk=pk,
    )
    apprenant = get_own_apprenant(user)
    if apprenant is None or conv.apprenant_id != apprenant.id:
        # 404 volontaire : ne révèle pas l'existence d'une conversation d'autrui.
        raise ConversationIntrouvable
    if not bloc_disponible(conv.bloc):
        raise BlocIndisponible
    return apprenant, conv


class ConversationIntrouvable(Exception):
    pass


class BlocIndisponible(Exception):
    pass


# ── Vues ────────────────────────────────────────────────────────────────────

class BlocChatAPIView(APIView):
    """GET : ouvre/retourne la conversation du bloc. POST : envoie une question."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatTuteurThrottle]

    def get(self, request, bloc_id: int):
        bloc = _bloc_complet(bloc_id)
        apprenant, erreur, code = _acces_bloc(request.user, bloc)
        if erreur:
            return api_error(erreur, http_status=code)

        conv = _conversation_active(apprenant, bloc)

        # Précharge le modèle en arrière-plan pendant que l'apprenant lit/écrit.
        threading.Thread(target=chat_tuteur.precharger_modele, daemon=True).start()

        ctx = chat_tuteur.contexte_bloc(bloc)
        return api_success(
            "Conversation chargée.",
            {
                "conversation": _conv_data(conv),
                "messages": _messages_data(conv),
                "suggestions": chat_tuteur.suggestions(bloc),
                "contexte": {
                    "contenu_disponible": ctx["contenu_disponible"],
                    "tronque": ctx["tronque"],
                    "type_bloc": ctx["type_bloc"],
                    "ressources": ctx["ressources"],
                },
                "limites": {"max_message": MAX_MESSAGE},
            },
        )

    def post(self, request, bloc_id: int):
        bloc = _bloc_complet(bloc_id)
        apprenant, erreur, code = _acces_bloc(request.user, bloc)
        if erreur:
            return api_error(erreur, http_status=code)

        contenu = str(request.data.get("contenu") or request.data.get("message") or "").strip()
        client_id = str(request.data.get("client_id") or "").strip()[:64]

        if not contenu:
            return api_error("Le message est vide.", http_status=status.HTTP_400_BAD_REQUEST)
        if len(contenu) > MAX_MESSAGE:
            return api_error(
                f"Message trop long (maximum {MAX_MESSAGE} caractères).",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        conv = _conversation_active(apprenant, bloc)

        # Idempotence : même `client_id` → on renvoie la réponse déjà produite.
        if client_id:
            deja = (
                MessageTuteur.objects
                .filter(conversation=conv, role="user", client_id=client_id)
                .first()
            )
            if deja is not None:
                reponse = (
                    conv.messages
                    .filter(role="assistant", cree_le__gte=deja.cree_le)
                    .order_by("cree_le", "id")
                    .first()
                )
                return api_success(
                    "Message déjà traité.",
                    {
                        "conversation": _conv_data(conv),
                        "message": _msg_data(reponse) if reponse else None,
                        "messages": _messages_data(conv),
                    },
                )

        # Anti double-envoi : une génération récente est encore en cours.
        limite = timezone.now() - timedelta(seconds=EN_COURS_TTL_SECONDES)
        if conv.messages.filter(role="assistant", statut="en_cours", cree_le__gte=limite).exists():
            return api_error(
                "Une réponse est déjà en cours pour cette conversation. Patientez un instant.",
                http_status=status.HTTP_409_CONFLICT,
            )

        MessageTuteur.objects.create(
            conversation=conv,
            role="user",
            contenu=contenu,
            statut="termine",
            client_id=client_id,
        )
        assistant = MessageTuteur.objects.create(
            conversation=conv,
            role="assistant",
            contenu="",
            statut="en_cours",
        )

        resultat = chat_tuteur.repondre(conv, contenu)

        assistant.fournisseur = (resultat.get("provider") or "")[:40]
        assistant.modele = (resultat.get("model") or "")[:80]
        assistant.duree_ms = resultat.get("duree_ms")

        if resultat.get("ok"):
            assistant.contenu = resultat["content"]
            assistant.statut = "termine"
            assistant.save()
            conv.save(update_fields=["maj_le"])
            return api_success(
                "Réponse générée.",
                {
                    "conversation": _conv_data(conv),
                    "message": _msg_data(assistant),
                    "messages": _messages_data(conv),
                },
            )

        assistant.contenu = (
            "Je n'ai pas pu générer de réponse pour le moment. "
            "Vous pouvez réessayer dans quelques instants."
        )
        assistant.statut = "erreur"
        assistant.erreur = (resultat.get("error") or "Erreur IA")[:255]
        assistant.save()
        conv.save(update_fields=["maj_le"])

        return Response(
            {
                "success": False,
                "status": status.HTTP_502_BAD_GATEWAY,
                "code": "AI_PROVIDER_ERROR",
                "message": "L'assistant n'a pas pu répondre. Vous pouvez réessayer.",
                "data": {
                    "conversation": _conv_data(conv),
                    "message": _msg_data(assistant),
                    "messages": _messages_data(conv),
                },
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


class ConversationChatDetailAPIView(APIView):
    """GET : historique d'une conversation. DELETE : suppression définitive."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        try:
            _, conv = _conversation_autorisee(request.user, pk)
        except ConversationIntrouvable:
            return api_error("Conversation introuvable.", http_status=status.HTTP_404_NOT_FOUND)
        except BlocIndisponible:
            return api_error("Ce contenu n'est plus disponible.", http_status=status.HTTP_403_FORBIDDEN)

        return api_success(
            "Historique chargé.",
            {
                "conversation": _conv_data(conv),
                "messages": _messages_data(conv),
                "suggestions": chat_tuteur.suggestions(conv.bloc),
            },
        )

    def delete(self, request, pk: int):
        try:
            _, conv = _conversation_autorisee(request.user, pk)
        except ConversationIntrouvable:
            return api_error("Conversation introuvable.", http_status=status.HTTP_404_NOT_FOUND)
        except BlocIndisponible:
            return api_error("Ce contenu n'est plus disponible.", http_status=status.HTTP_403_FORBIDDEN)

        conv.delete()
        return api_success("Conversation supprimée.", {"id": pk})


class ConversationChatNouvelleAPIView(APIView):
    """POST : archive la conversation courante et en démarre une nouvelle."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        try:
            apprenant, conv = _conversation_autorisee(request.user, pk)
        except ConversationIntrouvable:
            return api_error("Conversation introuvable.", http_status=status.HTTP_404_NOT_FOUND)
        except BlocIndisponible:
            return api_error("Ce contenu n'est plus disponible.", http_status=status.HTTP_403_FORBIDDEN)

        conv.statut = "archivee"
        conv.save(update_fields=["statut", "maj_le"])

        nouvelle = ConversationTuteur.objects.create(
            apprenant=apprenant,
            bloc=conv.bloc,
            cours=conv.cours,
            institution=conv.institution,
            titre=(conv.bloc.titre or "")[:255],
            statut="active",
        )

        return api_success(
            "Nouvelle conversation démarrée.",
            {
                "conversation": _conv_data(nouvelle),
                "messages": [],
                "suggestions": chat_tuteur.suggestions(conv.bloc),
            },
        )
