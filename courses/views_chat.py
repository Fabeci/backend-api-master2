# courses/views_chat.py
"""Endpoints de l'assistant pédagogique IA (chat par bloc de cours).

Sécurité :
  - l'identité vient TOUJOURS de `request.user` (jamais d'un id transmis) ;
  - un apprenant doit être inscrit au cours et le bloc doit être disponible ;
  - une conversation n'est accessible qu'à son propriétaire ;
  - les messages sont limités en taille et le débit est throttlé.
"""
from __future__ import annotations

import json
import threading
from datetime import timedelta

from django.db import close_old_connections
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.rbac import display_role
from users.access_control import get_own_apprenant
from users.views import api_error, api_success

from .models import BlocContenu, ConversationTuteur, MessageTuteur, QuizTuteur
from .publication import bloc_disponible
from .services import chat_tuteur, difficulte as difficulte_service, quiz_tuteur
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
        "sources": message.sources or [],
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


def _evaluation_en_cours(apprenant, cours) -> bool:
    """Vrai si l'apprenant a un passage d'évaluation non soumis pour ce cours.

    C'est un contrôle SERVEUR, indépendant de la formulation de la question :
    impossible de contourner en demandant « la réponse » autrement.
    """
    from evaluations.models import PassageEvaluation

    return PassageEvaluation.objects.filter(
        apprenant=apprenant,
        statut="en_cours",
        evaluation__cours=cours,
    ).exists()




def _sse(evenement: str, donnees: dict) -> str:
    """Formate un événement Server-Sent Events."""
    return f"event: {evenement}\ndata: {json.dumps(donnees, default=str)}\n\n"


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
        evaluation_active = _evaluation_en_cours(apprenant, bloc.sequence.module.cours)
        return api_success(
            "Conversation chargée.",
            {
                "evaluation": {
                    "en_cours": evaluation_active,
                    "message": (
                        "Une évaluation est en cours pour ce cours : "
                        "l'assistant est suspendu jusqu'à la remise de votre copie."
                        if evaluation_active else ""
                    ),
                },
                "conversation": _conv_data(conv),
                "messages": _messages_data(conv),
                "suggestions": chat_tuteur.suggestions(bloc),
                "difficulte": difficulte_service.analyser(conv),
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

        # Anti-triche : aucune question pendant une évaluation en cours.
        if _evaluation_en_cours(apprenant, bloc.sequence.module.cours):
            return api_error(
                "Une évaluation est en cours pour ce cours : l'assistant est "
                "désactivé jusqu'à la remise de votre copie.",
                http_status=423,
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
            assistant.sources = resultat.get("sources") or []
            assistant.save()
            conv.save(update_fields=["maj_le"])
            return api_success(
                "Réponse générée.",
                {
                    "evaluation": {"en_cours": False, "message": ""},
                    "conversation": _conv_data(conv),
                    "message": _msg_data(assistant),
                    "messages": _messages_data(conv),
                    "difficulte": difficulte_service.analyser(conv),
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


class BlocChatStreamAPIView(APIView):
    """POST : même logique que BlocChatAPIView, mais réponse en flux SSE."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatTuteurThrottle]

    def post(self, request, bloc_id: int):
        bloc = _bloc_complet(bloc_id)
        apprenant, erreur, code = _acces_bloc(request.user, bloc)
        if erreur:
            return api_error(erreur, http_status=code)

        if _evaluation_en_cours(apprenant, bloc.sequence.module.cours):
            return api_error(
                "Une évaluation est en cours pour ce cours : l'assistant est "
                "désactivé jusqu'à la remise de votre copie.",
                http_status=423,
            )

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

        # Idempotence : on rejoue la réponse déjà produite, en flux.
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

                def rejouer():
                    if reponse and reponse.contenu:
                        yield _sse("delta", {"delta": reponse.contenu})
                    yield _sse("done", {
                        "message": _msg_data(reponse) if reponse else None,
                        "conversation": _conv_data(conv),
                        "messages": _messages_data(conv),
                    })

                response = StreamingHttpResponse(rejouer(), content_type="text/event-stream")
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"
                return response

        limite = timezone.now() - timedelta(seconds=EN_COURS_TTL_SECONDES)
        if conv.messages.filter(role="assistant", statut="en_cours", cree_le__gte=limite).exists():
            return api_error(
                "Une réponse est déjà en cours pour cette conversation. Patientez un instant.",
                http_status=status.HTTP_409_CONFLICT,
            )

        MessageTuteur.objects.create(
            conversation=conv, role="user", contenu=contenu,
            statut="termine", client_id=client_id,
        )
        assistant = MessageTuteur.objects.create(
            conversation=conv, role="assistant", contenu="", statut="en_cours",
        )

        def generer():
            morceaux = []
            termine = False
            try:
                for evenement in chat_tuteur.repondre_flux(conv, contenu):
                    if evenement.get("type") == "delta":
                        texte = evenement.get("text") or ""
                        if texte:
                            morceaux.append(texte)
                            yield _sse("delta", {"delta": texte})
                    elif evenement.get("type") == "done":
                        assistant.contenu = "".join(morceaux)
                        assistant.statut = "termine"
                        assistant.fournisseur = (evenement.get("provider") or "")[:40]
                        assistant.modele = (evenement.get("model") or "")[:80]
                        assistant.sources = evenement.get("sources") or []
                        assistant.save()
                        conv.save(update_fields=["maj_le"])
                        termine = True
                        yield _sse("done", {
                            "message": _msg_data(assistant),
                            "conversation": _conv_data(conv),
                            "messages": _messages_data(conv),
                            "difficulte": difficulte_service.analyser(conv),
                        })
                        return
                    elif evenement.get("type") == "error":
                        raise RuntimeError(evenement.get("message") or "Erreur IA")
            except GeneratorExit:
                # Client déconnecté : on conserve la réponse partielle.
                assistant.contenu = "".join(morceaux)
                assistant.statut = "interrompu"
                assistant.save()
                raise
            except Exception as exc:  # noqa: BLE001
                assistant.contenu = "".join(morceaux) or (
                    "Je n'ai pas pu générer de réponse pour le moment. Réessayez."
                )
                assistant.statut = "erreur"
                assistant.erreur = str(exc)[:255]
                assistant.save()
                conv.save(update_fields=["maj_le"])
                yield _sse("error", {
                    "message": "L'assistant n'a pas pu répondre. Réessayez.",
                    "data": {"messages": _messages_data(conv)},
                })
            finally:
                if not termine and assistant.statut == "en_cours":
                    assistant.contenu = "".join(morceaux)
                    assistant.statut = "interrompu"
                    assistant.save()
                close_old_connections()

        response = StreamingHttpResponse(generer(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class BlocQuizAPIView(APIView):
    """POST : génère un mini-quiz (3 QCM) à partir du bloc courant."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatTuteurThrottle]

    def post(self, request, bloc_id: int):
        bloc = _bloc_complet(bloc_id)
        apprenant, erreur, code = _acces_bloc(request.user, bloc)
        if erreur:
            return api_error(erreur, http_status=code)

        if _evaluation_en_cours(apprenant, bloc.sequence.module.cours):
            return api_error(
                "Une évaluation est en cours pour ce cours : l'assistant est "
                "désactivé jusqu'à la remise de votre copie.",
                http_status=423,
            )

        conv = _conversation_active(apprenant, bloc)
        questions, erreur_quiz, source_quiz = quiz_tuteur.generer_quiz(conv)
        if erreur_quiz:
            return Response(
                {
                    "success": False,
                    "status": status.HTTP_502_BAD_GATEWAY,
                    "code": "AI_PROVIDER_ERROR",
                    "message": "Impossible de générer le quiz pour le moment. Réessayez.",
                    "detail": erreur_quiz,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        quiz = QuizTuteur.objects.create(
            conversation=conv,
            apprenant=apprenant,
            bloc=bloc,
            cours=bloc.sequence.module.cours,
            titre=(bloc.titre or "")[:255],
            questions=questions,
            statut="en_cours",
        )

        return api_success("Quiz généré.", {
            "quiz_id": quiz.id,
            "titre": quiz.titre,
            "source": source_quiz,
            "questions": quiz_tuteur.questions_publiques(questions),
        })


class QuizCorrectionAPIView(APIView):
    """POST : corrige un quiz (barème et explications restent côté serveur)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        quiz = get_object_or_404(
            QuizTuteur.objects.select_related("bloc__sequence__module__cours"),
            pk=pk,
        )
        apprenant = get_own_apprenant(request.user)
        if apprenant is None or quiz.apprenant_id != apprenant.id:
            return api_error("Quiz introuvable.", http_status=status.HTTP_404_NOT_FOUND)

        if not bloc_disponible(quiz.bloc):
            return api_error("Ce contenu n'est plus disponible.", http_status=status.HTTP_403_FORBIDDEN)

        reponses = request.data.get("reponses")
        if not isinstance(reponses, list) or len(reponses) != len(quiz.questions):
            return api_error("Réponses invalides.", http_status=status.HTTP_400_BAD_REQUEST)
        for reponse in reponses:
            if reponse is None:
                continue
            if not isinstance(reponse, int) or not 0 <= reponse < quiz_tuteur.NB_OPTIONS:
                return api_error("Réponses invalides.", http_status=status.HTTP_400_BAD_REQUEST)

        if quiz.statut == "corrige":
            score = quiz.score or 0
            _, details = quiz_tuteur.corriger(quiz.questions, quiz.reponses)
        else:
            score, details = quiz_tuteur.corriger(quiz.questions, reponses)
            quiz.reponses = reponses
            quiz.score = score
            quiz.statut = "corrige"
            quiz.corrige_le = timezone.now()
            quiz.save(update_fields=["reponses", "score", "statut", "corrige_le"])

        publiques = quiz_tuteur.questions_publiques(quiz.questions)
        for index, question in enumerate(quiz.questions):
            publiques[index]["bonne_reponse"] = question["bonne_reponse"]
            publiques[index]["explication"] = question.get("explication", "")

        return api_success("Quiz corrigé.", {
            "quiz_id": quiz.id,
            "score": score,
            "details": details,
            "questions": publiques,
        })
