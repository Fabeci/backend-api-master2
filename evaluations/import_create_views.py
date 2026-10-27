# evaluations/import_create_views.py
# =============================================================================
# Création DIRECTE depuis un fichier (sans passer par le formulaire) :
#   POST /api/v1/evaluations/importer/   (multipart: file, cours, [titre, type_evaluation])
#   POST /api/v1/quiz/importer/          (multipart: file, sequence, [titre])
# =============================================================================

import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission

from courses.models import Cours, Sequence
from courses.utils import can_create_in_context
from courses.views import api_error, api_success

from .import_questions import extract_questions
from .models import Evaluation, Question, Quiz, Reponse

logger = logging.getLogger(__name__)

QUIZ_TYPES = {"choix_unique", "choix_multiple"}


def _allowed_types(quiz: bool):
    return QUIZ_TYPES if quiz else None  # None = tous les types d'évaluation


def _creer_questions(items, *, quiz=None, evaluation=None, warnings=None, errors=None):
    """Crée les questions une par une ; une question invalide n'annule pas les autres."""
    allowed = _allowed_types(quiz is not None)
    created = 0
    for i, q in enumerate(items, start=1):
        try:
            tq = q.get("type_question") or "choix_unique"
            if allowed is not None and tq not in allowed:
                if warnings is not None:
                    warnings.append(f"Question {i} : type « {tq} » non valide pour un quiz → 'choix_unique'.")
                tq = "choix_unique"

            with transaction.atomic():
                question = Question.objects.create(
                    quiz=quiz,
                    evaluation=evaluation,
                    enonce_texte=(q.get("enonce_texte") or f"Question {i}").strip(),
                    type_question=tq,
                    mode_correction="automatique",
                    points=float(q.get("points") or 1),
                    ordre=i,
                    indication_reponse=(q.get("indication_reponse") or "").strip(),
                )
                for j, r in enumerate(q.get("reponses") or [], start=1):
                    Reponse.objects.create(
                        question=question,
                        texte=(r.get("texte") or "").strip(),
                        est_correcte=bool(r.get("est_correcte")),
                        ordre=j,
                    )
            created += 1
        except Exception as exc:
            logger.exception("Création de la question %s échouée", i)
            if errors is not None:
                errors.append({
                    "question": i,
                    "enonce": (q.get("enonce_texte") or "")[:200],
                    "message": str(exc),
                })
    return created


class EvaluationImportCreateAPIView(APIView):
    """Crée une évaluation (brouillon) + ses questions depuis un fichier."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get("file")
        cours_id = request.data.get("cours") or request.data.get("cours_id")
        if not f:
            return api_error("Aucun fichier fourni.", http_status=status.HTTP_400_BAD_REQUEST)
        if not cours_id:
            return api_error("Le cours cible est obligatoire.", http_status=status.HTTP_400_BAD_REQUEST)

        cours = get_object_or_404(Cours.objects.select_related("enseignant"), pk=cours_id)
        user = request.user
        role = user.role.name if getattr(user, "role", None) else None
        if role != "Formateur":
            return api_error("Import réservé aux formateurs.", http_status=status.HTTP_403_FORBIDDEN)
        if not can_create_in_context(user, cours):
            return api_error("Action réservée au créateur du cours.", http_status=status.HTTP_403_FORBIDDEN)

        try:
            res = extract_questions(f.name, f.read())
        except Exception as exc:
            logger.exception("Import évaluation échoué (%s)", getattr(f, "name", "?"))
            return api_error("Impossible d'extraire les questions du fichier.",
                             errors={"detail": str(exc)}, http_status=status.HTTP_400_BAD_REQUEST)

        questions = res.get("questions") or []
        if not questions:
            return api_error("Aucune question exploitable dans le fichier.",
                             errors={"warnings": res.get("warnings", [])}, http_status=status.HTTP_400_BAD_REQUEST)

        titre = (request.data.get("titre") or f"Évaluation importée ({f.name})")[:255]
        type_eval = request.data.get("type_evaluation") or "structuree"
        bareme = sum(float(q.get("points") or 1) for q in questions)

        evaluation = Evaluation.objects.create(
            cours=cours,
            enseignant=cours.enseignant,
            titre=titre,
            type_evaluation=type_eval,
            bareme=bareme,
            consigne_texte=(request.data.get("consigne_texte") or "").strip(),
            est_publiee=False,
        )
        errors = []
        created = _creer_questions(questions, evaluation=evaluation, warnings=None, errors=errors)
        if created == 0:
            evaluation.delete()
            return api_error(
                "Aucune question n'a pu être créée.",
                errors={"errors": errors, "warnings": res.get("warnings", [])},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        return api_success(
            f"Évaluation créée avec {created} question(s)"
            + (f", {len(errors)} question(s) ignorée(s)." if errors else "."),
            {
                "evaluation_id": evaluation.id,
                "questions": created,
                "errors": errors,
                "warnings": res.get("warnings", []),
            },
            status.HTTP_201_CREATED,
        )


class QuizImportCreateAPIView(APIView):
    """Crée un quiz + ses questions depuis un fichier."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get("file")
        sequence_id = request.data.get("sequence") or request.data.get("sequence_id")
        if not f:
            return api_error("Aucun fichier fourni.", http_status=status.HTTP_400_BAD_REQUEST)
        if not sequence_id:
            return api_error("La séquence cible est obligatoire.", http_status=status.HTTP_400_BAD_REQUEST)

        seq = get_object_or_404(Sequence.objects.select_related("module__cours"), pk=sequence_id)
        user = request.user
        role = user.role.name if getattr(user, "role", None) else None
        if role != "Formateur":
            return api_error("Import réservé aux formateurs.", http_status=status.HTTP_403_FORBIDDEN)
        if not can_create_in_context(user, seq.module.cours):
            return api_error("Action réservée au créateur du cours.", http_status=status.HTTP_403_FORBIDDEN)

        try:
            res = extract_questions(f.name, f.read())
        except Exception as exc:
            logger.exception("Import quiz échoué (%s)", getattr(f, "name", "?"))
            return api_error("Impossible d'extraire les questions du fichier.",
                             errors={"detail": str(exc)}, http_status=status.HTTP_400_BAD_REQUEST)

        questions = res.get("questions") or []
        if not questions:
            return api_error("Aucune question exploitable dans le fichier.",
                             errors={"warnings": res.get("warnings", [])}, http_status=status.HTTP_400_BAD_REQUEST)

        warnings = list(res.get("warnings", []))
        titre = (request.data.get("titre") or f"Quiz importé ({f.name})")[:255]
        quiz = Quiz.objects.create(titre=titre, sequence=seq)
        errors = []
        created = _creer_questions(questions, quiz=quiz, warnings=warnings, errors=errors)
        if created == 0:
            quiz.delete()
            return api_error(
                "Aucune question n'a pu être créée.",
                errors={"errors": errors, "warnings": warnings},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        return api_success(
            f"Quiz créé avec {created} question(s)"
            + (f", {len(errors)} question(s) ignorée(s)." if errors else "."),
            {"quiz_id": quiz.id, "questions": created, "errors": errors, "warnings": warnings},
            status.HTTP_201_CREATED,
        )
