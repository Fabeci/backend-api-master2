# evaluations/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
import csv
from io import BytesIO
from django.http import HttpResponse
from django.db.models import Prefetch
from users.models import Apprenant, Parent as ParentModel
from courses.models import InscriptionCours
from .models import Evaluation, PassageEvaluation, ReponseQuestion
from .models import (
    Quiz, Question, Reponse, Evaluation, PassageEvaluation,
    ReponseQuestion, PassageQuiz, ReponseQuiz
)
from .serializers import (
    EvaluationAccessibiliteSerializer, QuizSerializer, QuizDetailSerializer,
    QuestionSerializer, QuestionCreateSerializer, ReponseSerializer,
    EvaluationSerializer, EvaluationDetailSerializer,
    PassageEvaluationSerializer, PassageEvaluationDetailSerializer,
    PassageEvaluationCreateSerializer, ReponseQuestionSerializer,
    ReponseQuestionCreateSerializer, CorrectionReponseSerializer,
    CorrectionEvaluationSerializer, PassageQuizSerializer,
    PassageQuizDetailSerializer, ReponseQuizSerializer,
)


# ============================================================================
# HELPERS RÔLES
# ============================================================================

def _get_role(user):
    if hasattr(user, 'role') and user.role:
        return user.role.name
    return None


def _is_super_admin(user):
    return getattr(user, 'is_superuser', False)


def _block_super_admin(user):
    """Retourne une Response 403 si SuperAdmin, sinon None."""
    if _is_super_admin(user):
        return api_error(
            "Les SuperAdmins ne gèrent pas les ressources internes.",
            http_status=status.HTTP_403_FORBIDDEN
        )
    return None


def _require_roles(user, *roles):
    """Retourne None si autorisé, sinon une Response 403."""
    if _is_super_admin(user):
        return api_error(
            "Les SuperAdmins ne gèrent pas les ressources internes.",
            http_status=status.HTTP_403_FORBIDDEN
        )
    role = _get_role(user)
    if role not in roles:
        return api_error(
            f"Action réservée aux rôles : {', '.join(roles)}.",
            http_status=status.HTTP_403_FORBIDDEN
        )
    return None


def _formateur_owns_cours(user, cours):
    institution_id = getattr(user, 'institution_id', None)
    return (
        getattr(cours, 'enseignant_id', None) == user.id and
        getattr(cours, 'institution_id', None) == institution_id
    )


def _filter_by_institution(qs, user):
    """Filtre par institution de l'utilisateur."""
    institution_id = getattr(user, 'institution_id', None)
    if institution_id:
        return qs.filter(cours__institution_id=institution_id)
    return qs.none()


def _filter_quiz_by_institution(qs, user):
    institution_id = getattr(user, 'institution_id', None)
    if institution_id:
        return qs.filter(sequence__institution_id=institution_id)
    return qs.none()


def _filter_passage_for_parent(qs, user, model='evaluation'):
    """Filtre les passages pour un parent (données de ses enfants)."""
    enfants_ids = list(Apprenant.objects.filter(tuteur=user).values_list('id', flat=True))
    if not enfants_ids:
        return qs.none()
    return qs.filter(apprenant_id__in=enfants_ids)


def _get_annee_scolaire_id(request):
    """
    Extrait l'annee_scolaire_id depuis :
      1. Header X-Annee-Scolaire-ID
      2. Query param annee_scolaire_id
      3. Attribut profil utilisateur
    """
    def _to_int(v):
        if v is None:
            return None
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return None

    return (
        _to_int(request.headers.get("X-Annee-Scolaire-ID"))
        or _to_int(request.query_params.get("annee_scolaire_id"))
        or _to_int(getattr(request.user, "annee_scolaire_active_id", None))
    )


def _apply_annee_filter_eval(qs, annee_scolaire_id):
    """Filtre les évaluations par année scolaire via leur cours."""
    if not annee_scolaire_id:
        return qs
    return qs.filter(cours__annee_scolaire_id=annee_scolaire_id)


def _apply_annee_filter_quiz(qs, annee_scolaire_id):
    """Filtre les quiz par année scolaire via leur sequence→module→cours."""
    if not annee_scolaire_id:
        return qs
    return qs.filter(sequence__module__cours__annee_scolaire_id=annee_scolaire_id)


# ============================================================================
# RÉPONSES STANDARDISÉES
# ============================================================================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    return Response(
        {"success": True, "status": http_status, "message": message, "data": data},
        status=http_status,
    )


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST, data=None):
    payload = {"success": False, "status": http_status, "message": message, "data": data}
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# ============================================================================
# QUIZ
# ============================================================================

class QuizListCreateAPIView(APIView):
    """
    Permissions :
    - SuperAdmin   : BLOQUÉ
    - Admin/Responsable : CRUD complet
    - Formateur    : CRUD sur ses cours
    - Apprenant    : Lecture seule (ses cours)
    - Parent       : BLOQUÉ
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _block_super_admin(request.user)
        if err:
            return err

        role = _get_role(request.user)
        if role == 'Parent':
            return api_error("Accès non autorisé.", http_status=status.HTTP_403_FORBIDDEN)

        annee_scolaire_id = _get_annee_scolaire_id(request)

        try:
            sequence_id = request.query_params.get('sequence')
            qs = Quiz.objects.select_related('sequence').all()

            if role in ('Admin', 'ResponsableAcademique'):
                qs = _filter_quiz_by_institution(qs, request.user)
                # ✅ Filtre par année scolaire
                qs = _apply_annee_filter_quiz(qs, annee_scolaire_id)

            elif role == 'Formateur':
                institution_id = getattr(request.user, 'institution_id', None)
                qs = qs.filter(
                    sequence__institution_id=institution_id,
                    sequence__module__cours__enseignant=request.user
                )
                qs = _apply_annee_filter_quiz(qs, annee_scolaire_id)

            elif role == 'Apprenant':
                cours_ids = InscriptionCours.objects.filter(
                    apprenant=request.user, statut='inscrit'
                ).values_list('cours_id', flat=True)
                qs = qs.filter(sequence__module__cours_id__in=cours_ids)
                # Apprenant : année forcée depuis son inscription, pas de filtre supplémentaire

            else:
                qs = qs.none()

            if sequence_id:
                qs = qs.filter(sequence_id=sequence_id)

            return api_success("Liste des quiz récupérée.", QuizSerializer(qs, many=True).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err

        serializer = QuizSerializer(data=request.data)
        if serializer.is_valid():
            if _get_role(request.user) == 'Formateur':
                sequence_id = request.data.get('sequence')
                if sequence_id:
                    from courses.models import Sequence
                    seq = get_object_or_404(Sequence, pk=sequence_id)
                    if seq.module.cours.enseignant_id != request.user.id:
                        return api_error(
                            "Vous ne pouvez créer des quiz que dans vos propres cours.",
                            http_status=status.HTTP_403_FORBIDDEN
                        )
            quiz = serializer.save()
            return api_success("Quiz créé.", QuizSerializer(quiz).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation.", errors=serializer.errors)


class QuizDetailAPIView(APIView):
    """Détails d'un quiz avec permissions par rôle."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err
        if _get_role(request.user) == 'Parent':
            return api_error("Accès non autorisé.", http_status=status.HTTP_403_FORBIDDEN)

        quiz = get_object_or_404(Quiz, pk=pk)
        return api_success("Quiz trouvé.", QuizDetailSerializer(quiz).data)

    def put(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        quiz = get_object_or_404(Quiz, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if quiz.sequence.module.cours.enseignant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        serializer = QuizSerializer(quiz, data=request.data, partial=True)
        if serializer.is_valid():
            return api_success("Quiz mis à jour.", QuizSerializer(serializer.save()).data)
        return api_error("Erreur de validation.", errors=serializer.errors)

    def delete(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        quiz = get_object_or_404(Quiz, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if quiz.sequence.module.cours.enseignant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        quiz.delete()
        return api_success("Quiz supprimé.", None, status.HTTP_204_NO_CONTENT)


# ============================================================================
# QUESTIONS ET RÉPONSES
# ============================================================================

class QuestionListCreateAPIView(APIView):
    """
    Permissions :
    - SuperAdmin   : BLOQUÉ
    - Admin/Responsable : CRUD complet
    - Formateur    : CRUD sur ses quiz/évaluations
    - Apprenant    : Lecture seule SANS champ est_correcte
    - Parent       : BLOQUÉ
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        if role == 'Parent':
            return api_error("Accès non autorisé.", http_status=status.HTTP_403_FORBIDDEN)

        annee_scolaire_id = _get_annee_scolaire_id(request)

        try:
            quiz_id = request.query_params.get('quiz')
            evaluation_id = request.query_params.get('evaluation')
            qs = Question.objects.prefetch_related('reponses_predefinies').all()

            if role in ('Admin', 'ResponsableAcademique'):
                institution_id = getattr(request.user, 'institution_id', None)
                qs = qs.filter(
                    Q(quiz__sequence__institution_id=institution_id) |
                    Q(evaluation__cours__institution_id=institution_id)
                )
                # ✅ Filtre par année
                if annee_scolaire_id:
                    qs = qs.filter(
                        Q(quiz__sequence__module__cours__annee_scolaire_id=annee_scolaire_id) |
                        Q(evaluation__cours__annee_scolaire_id=annee_scolaire_id)
                    )

            elif role == 'Formateur':
                qs = qs.filter(
                    Q(quiz__sequence__module__cours__enseignant=request.user) |
                    Q(evaluation__cours__enseignant=request.user)
                )
                if annee_scolaire_id:
                    qs = qs.filter(
                        Q(quiz__sequence__module__cours__annee_scolaire_id=annee_scolaire_id) |
                        Q(evaluation__cours__annee_scolaire_id=annee_scolaire_id)
                    )

            elif role == 'Apprenant':
                cours_ids = InscriptionCours.objects.filter(
                    apprenant=request.user, statut='inscrit'
                ).values_list('cours_id', flat=True)
                qs = qs.filter(
                    Q(quiz__sequence__module__cours_id__in=cours_ids) |
                    Q(evaluation__cours_id__in=cours_ids)
                )
            else:
                qs = qs.none()

            if quiz_id:
                qs = qs.filter(quiz_id=quiz_id)
            elif evaluation_id:
                qs = qs.filter(evaluation_id=evaluation_id)

            data = QuestionSerializer(qs, many=True).data

            if role == 'Apprenant':
                data = _mask_correct_answers(data)

            return api_success("Liste des questions récupérée.", data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        serializer = QuestionCreateSerializer(data=request.data)
        if serializer.is_valid():
            question = serializer.save()
            return api_success("Question créée.", QuestionSerializer(question).data,
                               status.HTTP_201_CREATED)
        return api_error("Erreur de validation.", errors=serializer.errors)


class QuestionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        if role == 'Parent':
            return api_error("Accès non autorisé.", http_status=status.HTTP_403_FORBIDDEN)

        question = get_object_or_404(Question, pk=pk)
        data = QuestionSerializer(question).data
        if role == 'Apprenant':
            data = _mask_correct_answers_single(data)
        return api_success("Question trouvée.", data)

    def put(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        question = get_object_or_404(Question, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_question(request.user, question):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        serializer = QuestionSerializer(question, data=request.data, partial=True)
        if serializer.is_valid():
            return api_success("Question mise à jour.", QuestionSerializer(serializer.save()).data)
        return api_error("Erreur de validation.", errors=serializer.errors)

    def delete(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        question = get_object_or_404(Question, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_question(request.user, question):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        question.delete()
        return api_success("Question supprimée.", None, status.HTTP_204_NO_CONTENT)


class ReponseListCreateAPIView(APIView):
    """
    Réponses prédéfinies :
    - Apprenant : lecture SANS est_correcte
    - Parent : BLOQUÉ
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        if role == 'Parent':
            return api_error("Accès non autorisé.", http_status=status.HTTP_403_FORBIDDEN)

        try:
            question_id = request.query_params.get('question')
            qs = Reponse.objects.select_related('question').all()
            if question_id:
                qs = qs.filter(question_id=question_id)

            data = ReponseSerializer(qs, many=True).data

            if role == 'Apprenant':
                for item in data:
                    item.pop('est_correcte', None)

            return api_success("Liste des réponses récupérée.", data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        serializer = ReponseSerializer(data=request.data)
        if serializer.is_valid():
            return api_success("Réponse créée.", ReponseSerializer(serializer.save()).data,
                               status.HTTP_201_CREATED)
        return api_error("Erreur de validation.", errors=serializer.errors)


class ReponseDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        if role == 'Parent':
            return api_error("Accès non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
        reponse = get_object_or_404(Reponse, pk=pk)
        data = ReponseSerializer(reponse).data
        if role == 'Apprenant':
            data.pop('est_correcte', None)
        return api_success("Réponse trouvée.", data)

    def put(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        reponse = get_object_or_404(Reponse, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_question(request.user, reponse.question):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        serializer = ReponseSerializer(reponse, data=request.data, partial=True)
        if serializer.is_valid():
            return api_success("Réponse mise à jour.", ReponseSerializer(serializer.save()).data)
        return api_error("Erreur de validation.", errors=serializer.errors)

    def delete(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        reponse = get_object_or_404(Reponse, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_question(request.user, reponse.question):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        reponse.delete()
        return api_success("Réponse supprimée.", None, status.HTTP_204_NO_CONTENT)


# ============================================================================
# ÉVALUATIONS
# ============================================================================

class EvaluationListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _block_super_admin(request.user)
        if err:
            return err

        role = _get_role(request.user)

        if role is None:
            return api_error("Rôle utilisateur introuvable.", http_status=status.HTTP_403_FORBIDDEN)

        annee_scolaire_id = _get_annee_scolaire_id(request)

        try:
            cours_id = request.query_params.get('cours')
            enseignant_id = request.query_params.get('enseignant')
            est_publiee = request.query_params.get('publiee')

            qs = Evaluation.objects.select_related('cours', 'enseignant').prefetch_related('questions').all()

            if role in ('Admin', 'ResponsableAcademique'):
                qs = _filter_by_institution(qs, request.user)
                # ✅ Filtre par année scolaire
                qs = _apply_annee_filter_eval(qs, annee_scolaire_id)

            elif role == 'Formateur':
                institution_id = getattr(request.user, 'institution_id', None)
                if not institution_id:
                    qs = qs.none()
                else:
                    qs = qs.filter(
                        cours__enseignant=request.user,
                        cours__institution_id=institution_id
                    )
                    # ✅ Filtre par année scolaire
                    qs = _apply_annee_filter_eval(qs, annee_scolaire_id)

            elif role == 'Apprenant':
                cours_ids = InscriptionCours.objects.filter(
                    apprenant=request.user, statut='inscrit'
                ).values_list('cours_id', flat=True)
                qs = qs.filter(cours_id__in=cours_ids, est_publiee=True)
                # Apprenant : année fixée par son inscription, pas de filtre supplémentaire

            elif role == 'Parent':
                try:
                    parent_obj = ParentModel.objects.get(pk=request.user.pk)
                    enfant_ids = Apprenant.objects.filter(
                        tuteur=parent_obj
                    ).values_list('id', flat=True)
                    cours_ids = InscriptionCours.objects.filter(
                        apprenant_id__in=enfant_ids
                    ).values_list('cours_id', flat=True).distinct()
                    qs = qs.filter(cours_id__in=cours_ids, est_publiee=True)
                except Exception:
                    qs = qs.none()

            else:
                qs = qs.none()

            if cours_id:
                qs = qs.filter(cours_id=cours_id)
            if enseignant_id:
                qs = qs.filter(enseignant_id=enseignant_id)
            if est_publiee is not None:
                qs = qs.filter(est_publiee=est_publiee.lower() == 'true')

            return api_success(
                "Liste des évaluations récupérée.",
                EvaluationSerializer(qs, many=True).data
            )

        except Exception as e:
            return api_error(
                "Erreur serveur.",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        if _get_role(request.user) == 'Formateur':
            cours_id = request.data.get('cours')
            if cours_id:
                from courses.models import Cours
                cours = get_object_or_404(Cours, pk=cours_id)
                if not _formateur_owns_cours(request.user, cours):
                    return api_error(
                        "Vous ne pouvez créer des évaluations que dans vos propres cours.",
                        http_status=status.HTTP_403_FORBIDDEN
                    )
        serializer = EvaluationSerializer(data=request.data)
        if serializer.is_valid():
            return api_success("Évaluation créée.", EvaluationSerializer(serializer.save()).data,
                               status.HTTP_201_CREATED)
        return api_error("Erreur de validation.", errors=serializer.errors)


class EvaluationDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err

        role = _get_role(request.user)
        evaluation = get_object_or_404(Evaluation, pk=pk)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(request.user, 'institution_id', None)
            if evaluation.cours.institution_id != institution_id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        elif role == 'Formateur':
            if not _formateur_owns_cours(request.user, evaluation.cours):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        elif role == 'Apprenant':
            is_inscrit = InscriptionCours.objects.filter(
                apprenant=request.user,
                cours=evaluation.cours,
                statut='inscrit'
            ).exists()
            if not is_inscrit or not evaluation.est_publiee:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        elif role == 'Parent':
            try:
                parent_obj = ParentModel.objects.get(pk=request.user.pk)
                enfant_ids = Apprenant.objects.filter(
                    tuteur=parent_obj
                ).values_list('id', flat=True)
                is_accessible = InscriptionCours.objects.filter(
                    apprenant_id__in=enfant_ids,
                    cours=evaluation.cours
                ).exists()
                if not is_accessible or not evaluation.est_publiee:
                    return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            except Exception:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        else:
            return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        return api_success("Évaluation trouvée.", EvaluationDetailSerializer(evaluation).data)

    def put(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        evaluation = get_object_or_404(Evaluation, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_cours(request.user, evaluation.cours):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        serializer = EvaluationSerializer(evaluation, data=request.data, partial=True)
        if serializer.is_valid():
            return api_success("Évaluation mise à jour.", EvaluationSerializer(serializer.save()).data)
        return api_error("Erreur de validation.", errors=serializer.errors)

    def delete(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        evaluation = get_object_or_404(Evaluation, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_cours(request.user, evaluation.cours):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        evaluation.delete()
        return api_success("Évaluation supprimée.", None, status.HTTP_204_NO_CONTENT)


class EvaluationPublierAPIView(APIView):
    """Publier/dépublier : Admin, Responsable, Formateur (propriétaire)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        try:
            evaluation = get_object_or_404(Evaluation, pk=pk)
            if _get_role(request.user) == 'Formateur':
                if not _formateur_owns_cours(request.user, evaluation.cours):
                    return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

            action = request.data.get('action', 'publier')
            if action not in ['publier', 'depublier']:
                return api_error("Action invalide. Utilisez 'publier' ou 'depublier'.")

            if action == 'publier':
                if evaluation.type_evaluation in ('structuree', 'mixte') and not evaluation.questions.exists():
                    return api_error("L'évaluation doit contenir au moins une question.")
                if evaluation.type_evaluation in ('simple', 'mixte'):
                    if not evaluation.consigne_texte and not evaluation.fichier_sujet:
                        return api_error("Une consigne ou un fichier sujet est requis.")

            evaluation.est_publiee = (action == 'publier')
            evaluation.save()
            msg = "Évaluation publiée." if action == 'publier' else "Évaluation dépubliée."
            return api_success(msg, EvaluationSerializer(evaluation).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EvaluationAccessibiliteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err

        role = _get_role(request.user)

        try:
            evaluation = get_object_or_404(Evaluation, pk=pk)
            apprenant_id = request.query_params.get('apprenant')
            if not apprenant_id:
                return api_error("Le paramètre 'apprenant' est requis.")

            if role == 'Parent':
                try:
                    parent_obj = ParentModel.objects.get(pk=request.user.pk)
                    enfant_ids = list(
                        Apprenant.objects.filter(tuteur=parent_obj).values_list('id', flat=True)
                    )
                    if int(apprenant_id) not in enfant_ids:
                        return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
                    is_accessible = InscriptionCours.objects.filter(
                        apprenant_id=apprenant_id,
                        cours=evaluation.cours
                    ).exists()
                    if not is_accessible or not evaluation.est_publiee:
                        return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
                except (ParentModel.DoesNotExist, ValueError):
                    return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

            passage = PassageEvaluation.objects.filter(
                evaluation=evaluation, apprenant_id=apprenant_id
            ).first()

            data = {
                'evaluation_id': evaluation.id,
                'est_publiee': evaluation.est_publiee,
                'est_accessible': evaluation.est_accessible(),
                'peut_soumettre': evaluation.peut_soumettre(),
                'date_debut': evaluation.date_debut,
                'date_fin': evaluation.date_fin,
                'passage_existe': passage is not None,
                'passage': None,
                'action_possible': None
            }
            if passage:
                data['passage'] = {
                    'id': passage.id, 'statut': passage.statut,
                    'date_debut': passage.date_debut,
                    'peut_etre_repris': passage.peut_etre_repris(),
                    'peut_etre_soumis': passage.peut_etre_soumis(),
                    'note': passage.note, 'est_corrige': passage.est_corrige
                }
                if passage.statut == 'en_cours':
                    data['action_possible'] = 'reprendre' if passage.peut_etre_repris() else 'date_expiree'
                elif passage.statut == 'soumis':
                    data['action_possible'] = 'en_attente_correction'
                elif passage.statut == 'corrige':
                    data['action_possible'] = 'voir_resultat'
            else:
                data['action_possible'] = 'commencer' if evaluation.est_accessible() else 'non_accessible'

            return api_success("Informations d'accessibilité récupérées.",
                               EvaluationAccessibiliteSerializer(data).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PASSAGES D'ÉVALUATIONS
# ============================================================================

class PassageEvaluationDemarrerAPIView(APIView):
    """Démarrer un passage : Apprenant uniquement."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            apprenant_id = request.data.get('apprenant')
            evaluation_id = request.data.get('evaluation')
            if not apprenant_id or not evaluation_id:
                return api_error("Les champs 'apprenant' et 'evaluation' sont requis.")

            if str(request.user.id) != str(apprenant_id):
                return api_error("Vous ne pouvez démarrer que votre propre évaluation.",
                                 http_status=status.HTTP_403_FORBIDDEN)

            evaluation = get_object_or_404(Evaluation, pk=evaluation_id)
            passage_existant = PassageEvaluation.objects.filter(
                apprenant_id=apprenant_id, evaluation=evaluation
            ).first()

            if passage_existant:
                if passage_existant.statut == 'en_cours':
                    return api_success("Passage en cours récupéré.",
                                       PassageEvaluationDetailSerializer(passage_existant).data)
                return api_error(
                    f"Évaluation déjà soumise (statut: {passage_existant.statut}).",
                    data={'passage_id': passage_existant.id, 'statut': passage_existant.statut}
                )

            if not evaluation.est_accessible():
                return api_error("Cette évaluation n'est pas accessible actuellement.",
                                 http_status=status.HTTP_403_FORBIDDEN)

            passage = PassageEvaluation.objects.create(
                apprenant_id=apprenant_id, evaluation=evaluation, statut='en_cours'
            )
            if evaluation.type_evaluation in ('structuree', 'mixte'):
                for question in evaluation.questions.all():
                    ReponseQuestion.objects.create(
                        passage_evaluation=passage, question=question, statut='non_repondu'
                    )

            return api_success("Évaluation démarrée.",
                               PassageEvaluationDetailSerializer(passage).data,
                               status.HTTP_201_CREATED)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PassageEvaluationReprendreAPIView(APIView):
    """Reprendre : Apprenant (le sien) uniquement."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            if passage.apprenant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if passage.statut != 'en_cours':
                return api_error(f"Ce passage ne peut pas être repris (statut: {passage.statut}).")
            if not passage.peut_etre_repris():
                return api_error("La date limite est dépassée.", http_status=status.HTTP_403_FORBIDDEN)
            return api_success("Passage récupéré.", PassageEvaluationDetailSerializer(passage).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PassageEvaluationSauvegarderAPIView(APIView):
    """Sauvegarder : Apprenant (le sien) uniquement."""
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            if passage.apprenant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if passage.statut != 'en_cours':
                return api_error("Impossible de sauvegarder après soumission.")
            if passage.evaluation.type_evaluation != 'simple':
                return api_error("Route uniquement pour les évaluations simples.")
            serializer = PassageEvaluationSerializer(passage, data=request.data, partial=True)
            if serializer.is_valid():
                return api_success("Progression sauvegardée.",
                                   PassageEvaluationSerializer(serializer.save()).data)
            return api_error("Erreur de validation.", errors=serializer.errors)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PassageEvaluationSoumettreAPIView(APIView):
    """Soumettre : Apprenant (le sien) uniquement."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            if passage.apprenant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if passage.statut != 'en_cours':
                return api_error(f"Déjà soumise (statut: {passage.statut}).")
            if not passage.peut_etre_soumis():
                return api_error("Date limite dépassée.", http_status=status.HTTP_403_FORBIDDEN)

            if passage.evaluation.type_evaluation == 'structuree':
                if not passage.reponses_questions.exclude(statut='non_repondu').exists():
                    return api_error("Aucune question répondue.")
            elif passage.evaluation.type_evaluation == 'simple':
                if not passage.reponse_texte and not passage.fichier_reponse:
                    return api_error("Aucune réponse fournie.")

            passage.statut = 'soumis'
            passage.date_soumission = timezone.now()
            passage.save()

            if passage.evaluation.type_evaluation == 'structuree':
                if passage.evaluation.est_auto_corrigeable():
                    passage.auto_corriger()
                    msg = "Évaluation soumise et corrigée automatiquement."
                else:
                    passage.auto_corriger_qcm_uniquement()
                    msg = "Évaluation soumise, en attente de correction."
            else:
                msg = "Évaluation soumise, en attente de correction."

            return api_success(msg, PassageEvaluationDetailSerializer(passage).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PassageEvaluationListAPIView(APIView):
    """
    Liste des passages :
    - Admin/Responsable : tous les passages de l'institution
    - Formateur : passages de ses cours
    - Apprenant : ses propres passages
    - Parent : passages de ses enfants
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        try:
            apprenant_id = request.query_params.get('apprenant')
            evaluation_id = request.query_params.get('evaluation')
            statut = request.query_params.get('statut')

            qs = PassageEvaluation.objects.select_related('apprenant', 'evaluation').all()

            if role in ('Admin', 'ResponsableAcademique'):
                institution_id = getattr(request.user, 'institution_id', None)
                qs = qs.filter(evaluation__cours__institution_id=institution_id)
                # ✅ Filtre par année scolaire
                if annee_scolaire_id:
                    qs = qs.filter(evaluation__cours__annee_scolaire_id=annee_scolaire_id)

            elif role == 'Formateur':
                qs = qs.filter(evaluation__cours__enseignant=request.user)
                if annee_scolaire_id:
                    qs = qs.filter(evaluation__cours__annee_scolaire_id=annee_scolaire_id)

            elif role == 'Apprenant':
                qs = qs.filter(apprenant=request.user)

            elif role == 'Parent':
                qs = _filter_passage_for_parent(qs, request.user)

            else:
                qs = qs.none()

            if apprenant_id:
                qs = qs.filter(apprenant_id=apprenant_id)
            if evaluation_id:
                qs = qs.filter(evaluation_id=evaluation_id)
            if statut:
                qs = qs.filter(statut=statut)

            return api_success("Liste des passages récupérée.", PassageEvaluationSerializer(qs, many=True).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PassageEvaluationDetailAPIView(APIView):
    """Détail d'un passage selon rôle."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)

        passage = get_object_or_404(PassageEvaluation, pk=pk)

        if role == 'Apprenant' and passage.apprenant_id != request.user.id:
            return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        if role == 'Parent':
            enfants_ids = list(Apprenant.objects.filter(tuteur=request.user).values_list('id', flat=True))
            if passage.apprenant_id not in enfants_ids:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        if role == 'Formateur':
            if not _formateur_owns_cours(request.user, passage.evaluation.cours):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        return api_success("Passage trouvé.", PassageEvaluationDetailSerializer(passage).data)


# ============================================================================
# RÉPONSES AUX QUESTIONS
# ============================================================================

class ReponseQuestionSauvegarderAPIView(APIView):
    """Sauvegarder une réponse : Apprenant uniquement."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            passage_evaluation_id = request.data.get('passage_evaluation')
            question_id = request.data.get('question')
            if not passage_evaluation_id or not question_id:
                return api_error("'passage_evaluation' et 'question' sont requis.")

            passage = get_object_or_404(PassageEvaluation, pk=passage_evaluation_id)
            if passage.apprenant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if passage.statut != 'en_cours':
                return api_error("Impossible de modifier après soumission.")

            reponse, _ = ReponseQuestion.objects.get_or_create(
                passage_evaluation_id=passage_evaluation_id,
                question_id=question_id
            )
            if 'choix_selectionnes' in request.data:
                reponse.choix_selectionnes.set(request.data['choix_selectionnes'])
            if 'reponse_texte' in request.data:
                reponse.reponse_texte = request.data['reponse_texte']
            if 'fichier_reponse' in request.FILES:
                reponse.fichier_reponse = request.FILES['fichier_reponse']

            reponse.statut = 'repondu' if (
                reponse.choix_selectionnes.exists() or reponse.reponse_texte or reponse.fichier_reponse
            ) else 'non_repondu'
            reponse.save()

            return api_success("Réponse sauvegardée.", ReponseQuestionSerializer(reponse).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ReponseQuestionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        reponse = get_object_or_404(ReponseQuestion, pk=pk)
        if role == 'Apprenant' and reponse.passage_evaluation.apprenant_id != request.user.id:
            return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        if role == 'Parent':
            enfants_ids = list(Apprenant.objects.filter(tuteur=request.user).values_list('id', flat=True))
            if reponse.passage_evaluation.apprenant_id not in enfants_ids:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        return api_success("Réponse trouvée.", ReponseQuestionSerializer(reponse).data)


# ============================================================================
# CORRECTION
# ============================================================================

class CorrectionReponseAPIView(APIView):
    """Corriger une réponse manuelle : Admin, Responsable, Formateur."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        try:
            reponse = get_object_or_404(ReponseQuestion, pk=pk)
            if _get_role(request.user) == 'Formateur':
                if not _formateur_owns_cours(request.user, reponse.passage_evaluation.evaluation.cours):
                    return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if reponse.question.mode_correction == 'automatique':
                return api_error("Cette question est corrigée automatiquement.")
            if reponse.passage_evaluation.statut not in ('soumis', 'corrige'):
                return api_error("Le passage doit être soumis pour être corrigé.")

            serializer = CorrectionReponseSerializer(reponse, data=request.data, partial=True)
            if serializer.is_valid():
                reponse = serializer.save()
                reponse.statut = 'corrige'
                reponse.date_correction = timezone.now()
                reponse.save()
                return api_success("Réponse corrigée.", ReponseQuestionSerializer(reponse).data)
            return api_error("Erreur de validation.", errors=serializer.errors)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CorrectionEvaluationAPIView(APIView):
    """Corriger une évaluation : Admin, Responsable, Formateur."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            if _get_role(request.user) == 'Formateur':
                if not _formateur_owns_cours(request.user, passage.evaluation.cours):
                    return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if passage.statut not in ('soumis', 'corrige'):
                return api_error("Le passage doit être soumis pour être corrigé.")

            if passage.evaluation.type_evaluation == 'structuree':
                non_corriges = passage.reponses_questions.filter(
                    question__mode_correction='manuelle', statut__in=['non_repondu', 'repondu']
                ).count()
                if non_corriges > 0:
                    return api_error(f"{non_corriges} réponse(s) manuelle(s) non corrigée(s).")
                note_calculee = sum(
                    float(r.points_obtenus or 0) for r in passage.reponses_questions.all()
                )
                note_finale = request.data.get('note', note_calculee)
            else:
                note_finale = request.data.get('note')
                if note_finale is None:
                    return api_error("La note est requise pour les évaluations simples.")

            passage.note = note_finale
            passage.commentaire_enseignant = request.data.get('commentaire_enseignant', '')
            passage.statut = 'corrige'
            passage.date_correction = timezone.now()
            passage.save()
            return api_success("Évaluation corrigée.", PassageEvaluationDetailSerializer(passage).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EvaluationsACorrigerAPIView(APIView):
    """Liste des évaluations à corriger : Formateur/Admin/Responsable."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _require_roles(request.user, 'Admin', 'ResponsableAcademique', 'Formateur')
        if err:
            return err
        try:
            role = _get_role(request.user)
            annee_scolaire_id = _get_annee_scolaire_id(request)
            qs = PassageEvaluation.objects.select_related('apprenant', 'evaluation').filter(statut='soumis')

            if role in ('Admin', 'ResponsableAcademique'):
                institution_id = getattr(request.user, 'institution_id', None)
                qs = qs.filter(evaluation__cours__institution_id=institution_id)
                # ✅ Filtre par année scolaire
                if annee_scolaire_id:
                    qs = qs.filter(evaluation__cours__annee_scolaire_id=annee_scolaire_id)

            elif role == 'Formateur':
                qs = qs.filter(evaluation__cours__enseignant=request.user)
                if annee_scolaire_id:
                    qs = qs.filter(evaluation__cours__annee_scolaire_id=annee_scolaire_id)

            enseignant_id = request.query_params.get('enseignant')
            if enseignant_id:
                qs = qs.filter(evaluation__enseignant_id=enseignant_id)

            return api_success("Évaluations à corriger récupérées.",
                               PassageEvaluationSerializer(qs, many=True).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PASSAGES QUIZ
# ============================================================================

class PassageQuizListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        try:
            apprenant_id = request.query_params.get('apprenant')
            quiz_id = request.query_params.get('quiz')
            qs = PassageQuiz.objects.select_related('apprenant', 'quiz').all()

            if role in ('Admin', 'ResponsableAcademique'):
                institution_id = getattr(request.user, 'institution_id', None)
                qs = qs.filter(quiz__sequence__institution_id=institution_id)
                # ✅ Filtre par année scolaire
                if annee_scolaire_id:
                    qs = qs.filter(quiz__sequence__module__cours__annee_scolaire_id=annee_scolaire_id)

            elif role == 'Formateur':
                qs = qs.filter(quiz__sequence__module__cours__enseignant=request.user)
                if annee_scolaire_id:
                    qs = qs.filter(quiz__sequence__module__cours__annee_scolaire_id=annee_scolaire_id)

            elif role == 'Apprenant':
                qs = qs.filter(apprenant=request.user)

            elif role == 'Parent':
                qs = _filter_passage_for_parent(qs, request.user, model='quiz')

            else:
                qs = qs.none()

            if apprenant_id:
                qs = qs.filter(apprenant_id=apprenant_id)
            if quiz_id:
                qs = qs.filter(quiz_id=quiz_id)

            return api_success("Passages de quiz récupérés.", PassageQuizSerializer(qs, many=True).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        serializer = PassageQuizSerializer(data=request.data)
        if serializer.is_valid():
            if str(serializer.validated_data.get('apprenant', {}).id if hasattr(
                    serializer.validated_data.get('apprenant'), 'id') else '') != str(request.user.id):
                return api_error("Vous ne pouvez passer que vos propres quiz.",
                                 http_status=status.HTTP_403_FORBIDDEN)
            passage = serializer.save()
            for question in passage.quiz.questions.all():
                ReponseQuiz.objects.create(passage_quiz=passage, question=question)
            return api_success("Passage créé.", PassageQuizDetailSerializer(passage).data,
                               status.HTTP_201_CREATED)
        return api_error("Erreur de validation.", errors=serializer.errors)


class PassageQuizDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)
        passage = get_object_or_404(PassageQuiz, pk=pk)
        if role == 'Apprenant' and passage.apprenant_id != request.user.id:
            return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        if role == 'Parent':
            enfants_ids = list(Apprenant.objects.filter(tuteur=request.user).values_list('id', flat=True))
            if passage.apprenant_id not in enfants_ids:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        return api_success("Passage de quiz trouvé.", PassageQuizDetailSerializer(passage).data)


class ReponseQuizSubmitAPIView(APIView):
    """Soumettre une réponse quiz : Apprenant uniquement."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            passage_quiz_id = request.data.get('passage_quiz')
            question_id = request.data.get('question')
            choix_ids = request.data.get('choix_selectionnes', [])
            if not passage_quiz_id or not question_id:
                return api_error("'passage_quiz' et 'question' sont requis.")

            passage = get_object_or_404(PassageQuiz, pk=passage_quiz_id)
            if passage.apprenant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

            reponse, _ = ReponseQuiz.objects.get_or_create(
                passage_quiz_id=passage_quiz_id, question_id=question_id
            )
            reponse.choix_selectionnes.set(choix_ids)
            reponse.calculer_points_automatique()
            return api_success("Réponse enregistrée.", ReponseQuizSerializer(reponse).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PassageQuizTerminerAPIView(APIView):
    """Terminer un quiz : Apprenant (le sien) uniquement."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        err = _require_roles(request.user, 'Apprenant')
        if err:
            return err
        try:
            passage = get_object_or_404(PassageQuiz, pk=pk)
            if passage.apprenant_id != request.user.id:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
            if passage.termine:
                return api_error("Ce quiz a déjà été terminé.")
            passage.calculer_score()
            passage.termine = True
            passage.save()
            return api_success("Quiz terminé.", PassageQuizDetailSerializer(passage).data)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# STATISTIQUES
# ============================================================================

class StatistiquesApprenantAPIView(APIView):
    """
    Stats apprenant :
    - Apprenant : ses propres stats
    - Admin/Responsable/Formateur : stats de tout apprenant de leur institution
    - Parent : stats de ses enfants
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, apprenant_id):
        err = _block_super_admin(request.user)
        if err:
            return err
        role = _get_role(request.user)

        if role == 'Apprenant' and str(request.user.id) != str(apprenant_id):
            return api_error("Vous ne pouvez voir que vos propres statistiques.",
                             http_status=status.HTTP_403_FORBIDDEN)
        if role == 'Parent':
            enfants_ids = list(Apprenant.objects.filter(tuteur=request.user).values_list('id', flat=True))
            if int(apprenant_id) not in enfants_ids:
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        annee_scolaire_id = _get_annee_scolaire_id(request)

        try:
            passages_quiz = PassageQuiz.objects.filter(apprenant_id=apprenant_id, termine=True)
            passages_eval = PassageEvaluation.objects.filter(apprenant_id=apprenant_id)
            passages_corriges = passages_eval.filter(statut='corrige')

            # ✅ Filtre par année scolaire pour les stats aussi
            if annee_scolaire_id and role not in ('Apprenant', 'Parent'):
                passages_quiz = passages_quiz.filter(
                    quiz__sequence__module__cours__annee_scolaire_id=annee_scolaire_id
                )
                passages_eval = passages_eval.filter(
                    evaluation__cours__annee_scolaire_id=annee_scolaire_id
                )
                passages_corriges = passages_corriges.filter(
                    evaluation__cours__annee_scolaire_id=annee_scolaire_id
                )

            score_moyen = passages_quiz.aggregate(Avg('score'))['score__avg']
            note_moyenne = passages_corriges.aggregate(Avg('note'))['note__avg']

            stats = {
                'apprenant_id': apprenant_id,
                'nombre_quiz_passes': passages_quiz.count(),
                'score_moyen_quiz': round(score_moyen, 2) if score_moyen else 0,
                'nombre_evaluations_passees': passages_eval.count(),
                'nombre_evaluations_corrigees': passages_corriges.count(),
                'nombre_evaluations_en_attente': passages_eval.filter(statut='soumis').count(),
                'note_moyenne': round(note_moyenne, 2) if note_moyenne else 0,
            }
            return api_success("Statistiques récupérées.", stats)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StatistiquesEvaluationAPIView(APIView):
    """Stats évaluation : Admin, Responsable, Formateur uniquement."""
    permission_classes = [IsAuthenticated]

    def get(self, request, evaluation_id):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        try:
            evaluation = get_object_or_404(Evaluation, pk=evaluation_id)
            if _get_role(request.user) == 'Formateur':
                if not _formateur_owns_cours(request.user, evaluation.cours):
                    return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

            tous_passages = PassageEvaluation.objects.filter(evaluation_id=evaluation_id)
            passages_corriges = tous_passages.filter(statut='corrige')

            stats = {
                'evaluation_id': evaluation_id,
                'nb_passages': tous_passages.count(),
                'nb_passages_soumis': tous_passages.filter(statut='soumis').count(),
                'nb_passages_corriges': passages_corriges.count(),
                'nb_passages_en_cours': tous_passages.filter(statut='en_cours').count(),
                'bareme': evaluation.bareme,
                'moyenne_note': None, 'note_min': None,
                'note_max': None, 'taux_reussite': None,
                'stats_par_question': [], 'nb_questions': 0,
            }

            if passages_corriges.exists():
                notes = [n for n in passages_corriges.values_list('note', flat=True) if n is not None]
                if notes:
                    moyenne = sum(notes) / len(notes)
                    stats.update({
                        'moyenne_note': round(moyenne, 2),
                        'note_min': round(min(notes), 2),
                        'note_max': round(max(notes), 2),
                        'taux_reussite': round(
                            len([n for n in notes if n >= evaluation.bareme / 2]) / len(notes) * 100, 2
                        ),
                    })

            if evaluation.type_evaluation in ('structuree', 'mixte'):
                stats_par_question = []
                for question in evaluation.questions.all().order_by('ordre'):
                    reponses_q = ReponseQuestion.objects.filter(
                        passage_evaluation__evaluation_id=evaluation_id, question=question
                    )
                    nb_reponses = reponses_q.exclude(statut='non_repondu').count()
                    if question.mode_correction == 'automatique':
                        nb_correctes = reponses_q.filter(points_obtenus=question.points).count()
                        taux = round((nb_correctes / nb_reponses) * 100, 2) if nb_reponses > 0 else None
                        stats_par_question.append({
                            'question_id': question.id, 'enonce': question.enonce_texte,
                            'type_question': question.type_question, 'points': question.points,
                            'nb_reponses': nb_reponses, 'nb_correctes': nb_correctes,
                            'moyenne_points': None, 'taux_reussite': taux,
                        })
                    else:
                        points_list = list(
                            reponses_q.filter(statut='corrige').values_list('points_obtenus', flat=True)
                        )
                        moyenne_pts = round(sum(points_list) / len(points_list), 2) if points_list else None
                        taux = round((moyenne_pts / question.points) * 100, 2) if moyenne_pts else None
                        stats_par_question.append({
                            'question_id': question.id, 'enonce': question.enonce_texte,
                            'type_question': question.type_question, 'points': question.points,
                            'nb_reponses': nb_reponses, 'nb_correctes': None,
                            'moyenne_points': moyenne_pts, 'taux_reussite': taux,
                        })
                stats['stats_par_question'] = stats_par_question
                stats['nb_questions'] = len(stats_par_question)

            return api_success("Statistiques récupérées.", stats)
        except Exception as e:
            return api_error("Erreur serveur.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# EXPORT
# ============================================================================

class EvaluationExportAPIView(APIView):
    """Export : Admin, Responsable, Formateur (propriétaire)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        err = _require_roles(request.user, 'Admin', 'Responsable', 'Formateur')
        if err:
            return err
        evaluation = get_object_or_404(Evaluation, pk=pk)
        if _get_role(request.user) == 'Formateur':
            if not _formateur_owns_cours(request.user, evaluation.cours):
                return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)

        export_format = request.query_params.get("format", "csv").lower()
        detail = request.query_params.get("detail", "false").lower() == "true"

        passages = (
            PassageEvaluation.objects
            .select_related("apprenant", "evaluation", "evaluation__cours")
            .filter(evaluation=evaluation)
            .order_by("apprenant__nom", "apprenant__prenom")
        )

        if export_format == "xlsx":
            try:
                from openpyxl import Workbook
            except ImportError:
                return api_error("openpyxl non installé.",
                                 http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return self._export_detail_xlsx(evaluation, passages) if detail \
                else self._export_resume_xlsx(evaluation, passages)

        return self._export_detail_csv(evaluation, passages) if detail \
            else self._export_resume_csv(evaluation, passages)

    def _get_user_info(self, apprenant):
        return {
            'nom': getattr(apprenant, 'nom', '') or '',
            'prenom': getattr(apprenant, 'prenom', '') or '',
            'email': getattr(apprenant, 'email', '') or '',
        }

    def _export_resume_csv(self, evaluation, passages):
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_resume.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["evaluation_id", "evaluation", "cours", "apprenant_id", "nom", "prenom",
                         "email", "statut", "note", "bareme", "pourcentage",
                         "date_debut", "date_soumission", "date_correction"])
        for p in passages:
            info = self._get_user_info(p.apprenant)
            pct = p.pourcentage()
            writer.writerow([
                evaluation.id, evaluation.titre,
                evaluation.cours.titre if evaluation.cours else "",
                p.apprenant_id, info['nom'], info['prenom'], info['email'],
                p.statut, p.note if p.note is not None else "", evaluation.bareme,
                pct if pct is not None else "",
                p.date_debut, p.date_soumission, p.date_correction,
            ])
        return response

    def _export_detail_csv(self, evaluation, passages):
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_detail.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(["evaluation_id", "evaluation", "cours", "apprenant_id", "nom", "prenom",
                         "email", "statut_passage", "question_id", "ordre", "type_question", "enonce",
                         "statut_reponse", "points_obtenus", "points_question",
                         "reponse_texte", "fichier_reponse", "choix_selectionnes"])
        passage_ids = list(passages.values_list("id", flat=True))
        reponses = (
            ReponseQuestion.objects
            .select_related("passage_evaluation", "passage_evaluation__apprenant", "question")
            .prefetch_related("choix_selectionnes")
            .filter(passage_evaluation_id__in=passage_ids)
            .order_by("passage_evaluation__apprenant__nom", "question__ordre")
        )
        passage_map = {p.id: p for p in passages}
        for rq in reponses:
            p = passage_map.get(rq.passage_evaluation_id)
            if not p:
                continue
            info = self._get_user_info(p.apprenant)
            choix_txt = "; ".join(rq.choix_selectionnes.values_list("texte", flat=True))
            writer.writerow([
                evaluation.id, evaluation.titre,
                evaluation.cours.titre if evaluation.cours else "",
                p.apprenant_id, info['nom'], info['prenom'], info['email'], p.statut,
                rq.question_id, rq.question.ordre, rq.question.type_question,
                (rq.question.enonce_texte or '')[:200], rq.statut, rq.points_obtenus,
                rq.question.points, (rq.reponse_texte or '')[:200],
                rq.fichier_reponse.url if rq.fichier_reponse else "", choix_txt,
            ])
        return response

    def _export_resume_xlsx(self, evaluation, passages):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Résumé"
        ws.append(["evaluation_id", "evaluation", "cours", "apprenant_id", "nom", "prenom",
                   "email", "statut", "note", "bareme", "pourcentage",
                   "date_debut", "date_soumission", "date_correction"])
        for p in passages:
            info = self._get_user_info(p.apprenant)
            pct = p.pourcentage()
            ws.append([evaluation.id, evaluation.titre,
                       evaluation.cours.titre if evaluation.cours else "",
                       p.apprenant_id, info['nom'], info['prenom'], info['email'],
                       p.statut, p.note if p.note is not None else "", evaluation.bareme,
                       pct if pct is not None else "",
                       p.date_debut, p.date_soumission, p.date_correction])
        buff = BytesIO()
        wb.save(buff)
        buff.seek(0)
        response = HttpResponse(buff.getvalue(),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_resume.xlsx"'
        return response

    def _export_detail_xlsx(self, evaluation, passages):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Détail"
        ws.append(["evaluation_id", "evaluation", "cours", "apprenant_id", "nom", "prenom",
                   "email", "statut_passage", "question_id", "ordre", "type_question", "enonce",
                   "statut_reponse", "points_obtenus", "points_question",
                   "reponse_texte", "fichier_reponse", "choix_selectionnes"])
        passage_ids = list(passages.values_list("id", flat=True))
        reponses = (
            ReponseQuestion.objects
            .select_related("passage_evaluation", "passage_evaluation__apprenant", "question")
            .prefetch_related("choix_selectionnes")
            .filter(passage_evaluation_id__in=passage_ids)
            .order_by("passage_evaluation__apprenant__nom", "question__ordre")
        )
        passage_map = {p.id: p for p in passages}
        for rq in reponses:
            p = passage_map.get(rq.passage_evaluation_id)
            if not p:
                continue
            info = self._get_user_info(p.apprenant)
            choix_txt = "; ".join(rq.choix_selectionnes.values_list("texte", flat=True))
            ws.append([evaluation.id, evaluation.titre,
                       evaluation.cours.titre if evaluation.cours else "",
                       p.apprenant_id, info['nom'], info['prenom'], info['email'], p.statut,
                       rq.question_id, rq.question.ordre, rq.question.type_question,
                       (rq.question.enonce_texte or '')[:200], rq.statut, rq.points_obtenus,
                       rq.question.points, (rq.reponse_texte or '')[:200],
                       rq.fichier_reponse.url if rq.fichier_reponse else "", choix_txt])
        buff = BytesIO()
        wb.save(buff)
        buff.seek(0)
        response = HttpResponse(buff.getvalue(),
                                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_detail.xlsx"'
        return response


# ============================================================================
# HELPERS INTERNES
# ============================================================================

def _formateur_owns_question(formateur, question):
    """Vérifie que le formateur est propriétaire de la question."""
    if question.quiz:
        return question.quiz.sequence.module.cours.enseignant_id == formateur.id
    if question.evaluation:
        return question.evaluation.cours.enseignant_id == formateur.id
    return False


def _mask_correct_answers(questions_data):
    """Masque est_correcte dans une liste de questions sérialisées."""
    for q in questions_data:
        for rep in q.get('reponses_predefinies', []):
            rep.pop('est_correcte', None)
    return questions_data


def _mask_correct_answers_single(question_data):
    """Masque est_correcte dans une seule question sérialisée."""
    for rep in question_data.get('reponses_predefinies', []):
        rep.pop('est_correcte', None)
    return question_data