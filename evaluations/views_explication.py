# evaluations/views_explication.py
"""« Explique mon erreur » — explication IA d'une question ratée.

Accessible UNIQUEMENT après la remise de la copie (statut soumis/corrigé),
au propriétaire du passage, et pour une question effectivement incorrecte.
"""
from __future__ import annotations

import logging
import re

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.services.llm_provider import call_llm
from courses.models import BlocContenu
from courses.publication import bloc_disponible
from courses.throttles import ChatTuteurThrottle
from users.access_control import get_own_apprenant
from users.views import api_error, api_success

from .models import PassageEvaluation, Question, ReponseQuestion

logger = logging.getLogger(__name__)

MAX_TOKENS = 700
TYPES_CHOIX = ("choix_unique", "choix_multiple")

SYSTEM_PROMPT = (
    "Tu es un tuteur pédagogique bienveillant de SOMAPRO. "
    "L'apprenant a passé une évaluation déjà remise : tu peux donc parler librement "
    "de la bonne réponse. Ton rôle est de l'aider à COMPRENDRE son erreur, pas de le juger.\n"
    "Consignes :\n"
    "1. Explique précisément pourquoi sa réponse est incorrecte (sans le blâmer).\n"
    "2. Rappelle la notion du cours concernée, avec une définition simple.\n"
    "3. Donne un exemple concret ou une analogie.\n"
    "4. Termine par une méthode ou une astuce pour ne plus refaire l'erreur.\n"
    "5. Reste dans le périmètre de la question et du cours fourni ; n'invente pas.\n"
    "6. 150 à 250 mots, en français, en Markdown simple (titres courts, listes, gras)."
)


def _texte(valeur) -> str:
    texte = re.sub(r"\s+", " ", strip_tags(str(valeur or "")))
    return texte.replace("\xa0", " ").strip()


def _reponse_est_correcte(question: Question, reponse: ReponseQuestion) -> bool:
    if (question.type_question or "") in TYPES_CHOIX:
        ids_corrects = set(
            question.reponses_predefinies.filter(est_correcte=True).values_list("id", flat=True)
        )
        ids_choisis = set(reponse.choix_selectionnes.values_list("id", flat=True))
        return bool(ids_corrects) and ids_corrects == ids_choisis
    return (reponse.points_obtenus or 0) > 0


def _bloc_source(evaluation, enonce: str):
    """Bloc du cours le plus proche de la question (pour le lien « voir dans le cours »)."""
    cours = getattr(evaluation, "cours", None)
    if not cours:
        return None

    mots = [
        mot for mot in re.findall(r"[A-Za-zÀ-ÿ]{4,}", _texte(enonce).lower())
    ][:6]
    if not mots:
        return None

    requete = Q()
    for mot in mots:
        requete |= Q(titre__icontains=mot) | Q(contenu_texte__icontains=mot) \
            | Q(contenu_markdown__icontains=mot)

    bloc = (
        BlocContenu.objects
        .filter(sequence__module__cours=cours)
        .filter(requete)
        .order_by("sequence__ordre", "ordre", "id")
        .first()
    )
    if bloc and bloc_disponible(bloc):
        return bloc
    return None


def _construire_prompt(passage, question, reponse, bonnes, bloc) -> str:
    evaluation = passage.evaluation
    cours = getattr(evaluation, "cours", None)

    lignes = [
        f"ÉVALUATION : {_texte(evaluation.titre)}",
        f"COURS : {_texte(getattr(cours, 'titre', ''))}",
        f"QUESTION : {_texte(question.enonce_texte)}",
        f"TYPE : {question.get_type_question_display() if hasattr(question, 'get_type_question_display') else question.type_question}",
    ]

    options = list(question.reponses_predefinies.all())
    if options:
        selectionnees = set(reponse.choix_selectionnes.values_list("id", flat=True)) if reponse else set()
        correctes = {r.id for r in options if r.est_correcte}
        marqueurs = []
        for option in options:
            tags = []
            if option.id in correctes:
                tags.append("correcte")
            if option.id in selectionnees:
                tags.append("choisie par l'apprenant")
            suffixe = f" [{' / '.join(tags)}]" if tags else ""
            marqueurs.append(f"- {_texte(option.texte)}{suffixe}")
        lignes.append("OPTIONS :\n" + "\n".join(marqueurs))

    if reponse and reponse.choix_selectionnes.exists():
        lignes.append(
            "RÉPONSE DE L'APPRENANT : "
            + " ; ".join(_texte(r.texte) for r in reponse.choix_selectionnes.all())
        )
    elif reponse and _texte(reponse.reponse_texte):
        lignes.append("RÉPONSE DE L'APPRENANT : " + _texte(reponse.reponse_texte))
    else:
        lignes.append("RÉPONSE DE L'APPRENANT : aucune réponse fournie.")

    if bonnes:
        lignes.append(
            "BONNE(S) RÉPONSE(S) : " + " ; ".join(_texte(r.texte) for r in bonnes)
        )

    if reponse and _texte(reponse.commentaire_correcteur):
        lignes.append("COMMENTAIRE DU CORRECTEUR : " + _texte(reponse.commentaire_correcteur))

    if _texte(question.indication_reponse):
        lignes.append("INDICATION DU COURS : " + _texte(question.indication_reponse))

    if bloc:
        lignes.append(
            "EXTRAIT DU COURS ASSOCIÉ :\n" + _texte(bloc.contenu_texte or bloc.contenu_html)[:2500]
        )

    lignes.append(
        "Explique maintenant l'erreur de l'apprenant en suivant les consignes."
    )
    return "\n\n".join(lignes)


class PassageEvaluationExplicationAPIView(APIView):
    """POST {question_id} → explication pédagogique de l'erreur."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatTuteurThrottle]

    def post(self, request, pk: int):
        passage = get_object_or_404(
            PassageEvaluation.objects.select_related("evaluation__cours"),
            pk=pk,
        )

        apprenant = get_own_apprenant(request.user)
        if apprenant is None or passage.apprenant_id != apprenant.id:
            return api_error("Passage introuvable.", http_status=status.HTTP_404_NOT_FOUND)

        if (passage.statut or "").lower() not in ("soumis", "corrige"):
            return api_error(
                "L'explication est disponible après la remise de votre copie.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        question_id = request.data.get("question_id")
        try:
            question_id = int(question_id)
        except Exception:  # noqa: BLE001
            return api_error("Question invalide.", http_status=status.HTTP_400_BAD_REQUEST)

        question = get_object_or_404(Question, pk=question_id, evaluation=passage.evaluation)
        reponse = (
            ReponseQuestion.objects
            .filter(passage_evaluation=passage, question=question)
            .prefetch_related("choix_selectionnes")
            .first()
        )

        if reponse is not None and _reponse_est_correcte(question, reponse):
            return api_error(
                "Cette réponse est correcte : il n'y a pas d'erreur à expliquer.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        bonnes = list(question.reponses_predefinies.filter(est_correcte=True))
        bloc = _bloc_source(passage.evaluation, question.enonce_texte)

        resultat = call_llm(
            SYSTEM_PROMPT,
            _construire_prompt(passage, question, reponse, bonnes, bloc),
            json_mode=False,
            max_tokens=MAX_TOKENS,
        )
        if resultat.get("error") or not (resultat.get("content") or "").strip():
            return Response(
                {
                    "success": False,
                    "status": status.HTTP_502_BAD_GATEWAY,
                    "code": "AI_PROVIDER_ERROR",
                    "message": "Impossible de générer l'explication. Réessayez.",
                    "detail": resultat.get("error") or "Réponse vide",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return api_success("Explication générée.", {
            "question_id": question.id,
            "enonce": _texte(question.enonce_texte),
            "reponse_apprenant": (
                " ; ".join(_texte(r.texte) for r in reponse.choix_selectionnes.all())
                if reponse and reponse.choix_selectionnes.exists()
                else _texte(reponse.reponse_texte) if reponse else ""
            ),
            "bonnes_reponses": [_texte(r.texte) for r in bonnes],
            "explication": resultat["content"].strip(),
            "source": (
                {
                    "bloc_id": bloc.id,
                    "bloc_titre": bloc.titre,
                    "cours_id": passage.evaluation.cours_id,
                } if bloc else None
            ),
        })
