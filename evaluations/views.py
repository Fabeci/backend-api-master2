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

from .models import Evaluation, PassageEvaluation, ReponseQuestion

from .models import (
    Quiz, 
    Question, 
    Reponse, 
    Evaluation, 
    PassageEvaluation,
    ReponseQuestion,
    PassageQuiz,
    ReponseQuiz
)

from .serializers import (
    EvaluationAccessibiliteSerializer,
    QuizSerializer,
    QuizDetailSerializer,
    QuestionSerializer,
    QuestionCreateSerializer,
    ReponseSerializer,
    EvaluationSerializer,
    EvaluationDetailSerializer,
    PassageEvaluationSerializer,
    PassageEvaluationDetailSerializer,
    PassageEvaluationCreateSerializer,
    ReponseQuestionSerializer,
    ReponseQuestionCreateSerializer,
    CorrectionReponseSerializer,
    CorrectionEvaluationSerializer,
    PassageQuizSerializer,
    PassageQuizDetailSerializer,
    ReponseQuizSerializer,
)


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    """Réponse standardisée pour les succès"""
    return Response(
        {
            "success": True,
            "status": http_status,
            "message": message,
            "data": data,
        },
        status=http_status,
    )


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST, data=None):
    """Réponse standardisée pour les erreurs"""
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
        "data": data,
    }
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# ============================================================================
# VUES POUR QUIZ
# ============================================================================

class QuizListCreateAPIView(APIView):
    """Liste tous les quiz ou crée un nouveau quiz"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste de tous les quiz"""
        try:
            sequence_id = request.query_params.get('sequence')
            
            quizz = Quiz.objects.select_related('sequence').all()
            
            if sequence_id:
                quizz = quizz.filter(sequence_id=sequence_id)
            
            serializer = QuizSerializer(quizz, many=True)
            return api_success(
                "Liste des quiz récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des quiz",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée un nouveau quiz"""
        serializer = QuizSerializer(data=request.data)
        if serializer.is_valid():
            quiz = serializer.save()
            return api_success(
                "Quiz créé avec succès",
                QuizSerializer(quiz).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class QuizDetailAPIView(APIView):
    """Détails d'un quiz avec toutes ses questions"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'un quiz"""
        quiz = get_object_or_404(Quiz, pk=pk)
        serializer = QuizDetailSerializer(quiz)
        return api_success(
            "Quiz trouvé avec succès",
            serializer.data,
            status.HTTP_200_OK
        )
    
    def put(self, request, pk):
        """Met à jour un quiz"""
        quiz = get_object_or_404(Quiz, pk=pk)
        serializer = QuizSerializer(quiz, data=request.data, partial=True)
        if serializer.is_valid():
            quiz = serializer.save()
            return api_success(
                "Quiz mis à jour avec succès",
                QuizSerializer(quiz).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request, pk):
        """Supprime un quiz"""
        quiz = get_object_or_404(Quiz, pk=pk)
        quiz.delete()
        return api_success(
            "Quiz supprimé avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )


class PassageQuizListCreateAPIView(APIView):
    """Liste des passages de quiz ou création d'un nouveau passage"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste des passages de quiz"""
        try:
            apprenant_id = request.query_params.get('apprenant')
            quiz_id = request.query_params.get('quiz')
            
            passages = PassageQuiz.objects.select_related(
                'apprenant',
                'quiz'
            ).prefetch_related('reponses_quiz').all()
            
            if apprenant_id:
                passages = passages.filter(apprenant_id=apprenant_id)
            if quiz_id:
                passages = passages.filter(quiz_id=quiz_id)
            
            serializer = PassageQuizSerializer(passages, many=True)
            return api_success(
                "Liste des passages de quiz récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des passages de quiz",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request):
        """Créer un nouveau passage de quiz"""
        serializer = PassageQuizSerializer(data=request.data)
        if serializer.is_valid():
            passage = serializer.save()
            
            # Créer les réponses vides pour toutes les questions
            for question in passage.quiz.questions.all():
                ReponseQuiz.objects.create(
                    passage_quiz=passage,
                    question=question
                )
            
            return api_success(
                "Passage de quiz créé avec succès",
                PassageQuizDetailSerializer(passage).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class PassageQuizDetailAPIView(APIView):
    """Détails d'un passage de quiz"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'un passage de quiz"""
        passage = get_object_or_404(PassageQuiz, pk=pk)
        serializer = PassageQuizDetailSerializer(passage)
        return api_success(
            "Détails du passage de quiz récupérés avec succès",
            serializer.data,
            status.HTTP_200_OK
        )


class ReponseQuizSubmitAPIView(APIView):
    """Soumettre une réponse à une question de quiz"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Soumet une réponse à une question de quiz"""
        try:
            passage_quiz_id = request.data.get('passage_quiz')
            question_id = request.data.get('question')
            choix_ids = request.data.get('choix_selectionnes', [])
            
            if not passage_quiz_id or not question_id:
                return api_error(
                    "Les champs 'passage_quiz' et 'question' sont requis",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Récupérer ou créer la réponse
            reponse, created = ReponseQuiz.objects.get_or_create(
                passage_quiz_id=passage_quiz_id,
                question_id=question_id
            )
            
            # Mettre à jour les choix
            reponse.choix_selectionnes.set(choix_ids)
            
            # Auto-correction
            reponse.calculer_points_automatique()
            
            serializer = ReponseQuizSerializer(reponse)
            return api_success(
                "Réponse enregistrée et corrigée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de l'enregistrement de la réponse",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PassageQuizTerminerAPIView(APIView):
    """Terminer un quiz et calculer le score final"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """Termine un passage de quiz et calcule le score final"""
        try:
            passage = get_object_or_404(PassageQuiz, pk=pk)
            
            if passage.termine:
                return api_error(
                    "Ce quiz a déjà été terminé",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculer le score
            passage.calculer_score()
            passage.termine = True
            passage.save()
            
            serializer = PassageQuizDetailSerializer(passage)
            return api_success(
                "Quiz terminé avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la finalisation du quiz",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# VUES POUR QUESTIONS ET RÉPONSES
# ============================================================================

class QuestionListCreateAPIView(APIView):
    """Liste toutes les questions ou crée une nouvelle question"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste des questions"""
        try:
            quiz_id = request.query_params.get('quiz')
            evaluation_id = request.query_params.get('evaluation')
            
            questions = Question.objects.prefetch_related('reponses_predefinies').all()
            
            if quiz_id:
                questions = questions.filter(quiz_id=quiz_id)
            elif evaluation_id:
                questions = questions.filter(evaluation_id=evaluation_id)
            
            serializer = QuestionSerializer(questions, many=True)
            return api_success(
                "Liste des questions récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des questions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Créer une question avec ses réponses prédéfinies"""
        serializer = QuestionCreateSerializer(data=request.data)
        if serializer.is_valid():
            question = serializer.save()
            return api_success(
                "Question créée avec succès",
                QuestionSerializer(question).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class QuestionDetailAPIView(APIView):
    """Détails, mise à jour ou suppression d'une question"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'une question"""
        question = get_object_or_404(Question, pk=pk)
        serializer = QuestionSerializer(question)
        return api_success(
            "Question trouvée avec succès",
            serializer.data,
            status.HTTP_200_OK
        )
    
    def put(self, request, pk):
        """Met à jour une question"""
        question = get_object_or_404(Question, pk=pk)
        serializer = QuestionSerializer(question, data=request.data, partial=True)
        if serializer.is_valid():
            question = serializer.save()
            return api_success(
                "Question mise à jour avec succès",
                QuestionSerializer(question).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request, pk):
        """Supprime une question"""
        question = get_object_or_404(Question, pk=pk)
        question.delete()
        return api_success(
            "Question supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )


class ReponseListCreateAPIView(APIView):
    """Liste toutes les réponses prédéfinies ou crée une nouvelle réponse"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste des réponses prédéfinies"""
        try:
            question_id = request.query_params.get('question')
            
            reponses = Reponse.objects.select_related('question').all()
            
            if question_id:
                reponses = reponses.filter(question_id=question_id)
            
            serializer = ReponseSerializer(reponses, many=True)
            return api_success(
                "Liste des réponses récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des réponses",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée une nouvelle réponse prédéfinie"""
        serializer = ReponseSerializer(data=request.data)
        if serializer.is_valid():
            reponse = serializer.save()
            return api_success(
                "Réponse créée avec succès",
                ReponseSerializer(reponse).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class ReponseDetailAPIView(APIView):
    """Détails, mise à jour ou suppression d'une réponse prédéfinie"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'une réponse"""
        reponse = get_object_or_404(Reponse, pk=pk)
        serializer = ReponseSerializer(reponse)
        return api_success(
            "Réponse trouvée avec succès",
            serializer.data,
            status.HTTP_200_OK
        )
    
    def put(self, request, pk):
        """Met à jour une réponse"""
        reponse = get_object_or_404(Reponse, pk=pk)
        serializer = ReponseSerializer(reponse, data=request.data, partial=True)
        if serializer.is_valid():
            reponse = serializer.save()
            return api_success(
                "Réponse mise à jour avec succès",
                ReponseSerializer(reponse).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request, pk):
        """Supprime une réponse"""
        reponse = get_object_or_404(Reponse, pk=pk)
        reponse.delete()
        return api_success(
            "Réponse supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )


# ============================================================================
# VUES POUR ÉVALUATIONS
# ============================================================================

class EvaluationListCreateAPIView(APIView):
    """Liste toutes les évaluations ou crée une nouvelle évaluation"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste des évaluations"""
        try:
            cours_id = request.query_params.get('cours')
            enseignant_id = request.query_params.get('enseignant')
            est_publiee = request.query_params.get('publiee')
            
            evaluations = Evaluation.objects.select_related(
                'cours',
                'enseignant'
            ).prefetch_related('questions').all()
            
            if cours_id:
                evaluations = evaluations.filter(cours_id=cours_id)
            if enseignant_id:
                evaluations = evaluations.filter(enseignant_id=enseignant_id)
            if est_publiee is not None:
                evaluations = evaluations.filter(est_publiee=est_publiee.lower() == 'true')
            
            serializer = EvaluationSerializer(evaluations, many=True)
            return api_success(
                "Liste des évaluations récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des évaluations",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée une nouvelle évaluation"""
        serializer = EvaluationSerializer(data=request.data)
        if serializer.is_valid():
            evaluation = serializer.save()
            return api_success(
                "Évaluation créée avec succès",
                EvaluationSerializer(evaluation).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class EvaluationDetailAPIView(APIView):
    """Détails d'une évaluation avec toutes ses questions"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'une évaluation"""
        evaluation = get_object_or_404(Evaluation, pk=pk)
        serializer = EvaluationDetailSerializer(evaluation)
        return api_success(
            "Évaluation trouvée avec succès",
            serializer.data,
            status.HTTP_200_OK
        )
    
    def put(self, request, pk):
        """Met à jour une évaluation"""
        evaluation = get_object_or_404(Evaluation, pk=pk)
        serializer = EvaluationSerializer(evaluation, data=request.data, partial=True)
        if serializer.is_valid():
            evaluation = serializer.save()
            return api_success(
                "Évaluation mise à jour avec succès",
                EvaluationSerializer(evaluation).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request, pk):
        """Supprime une évaluation"""
        evaluation = get_object_or_404(Evaluation, pk=pk)
        evaluation.delete()
        return api_success(
            "Évaluation supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )


class EvaluationPublierAPIView(APIView):
    """Publier ou dépublier une évaluation"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """Publie ou dépublie une évaluation"""
        try:
            evaluation = get_object_or_404(Evaluation, pk=pk)
            action = request.data.get('action', 'publier')
            
            if action not in ['publier', 'depublier']:
                return api_error(
                    "Action invalide. Utilisez 'publier' ou 'depublier'",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            evaluation.est_publiee = (action == 'publier')
            evaluation.save()
            
            message = "Évaluation publiée avec succès" if action == 'publier' else "Évaluation dépubliée avec succès"
            
            serializer = EvaluationSerializer(evaluation)
            return api_success(message, serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error(
                "Erreur lors de la publication/dépublication",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EvaluationAccessibiliteAPIView(APIView):
    """Vérifier l'accessibilité d'une évaluation pour un apprenant"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """
        Retourne les informations d'accessibilité d'une évaluation
        Inclut: est_accessible, peut_commencer, peut_reprendre, passage existant, etc.
        """
        try:
            evaluation = get_object_or_404(Evaluation, pk=pk)
            apprenant_id = request.query_params.get('apprenant')
            
            if not apprenant_id:
                return api_error(
                    "Le paramètre 'apprenant' est requis",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérifier si un passage existe
            passage = PassageEvaluation.objects.filter(
                evaluation=evaluation,
                apprenant_id=apprenant_id
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
                    'id': passage.id,
                    'statut': passage.statut,
                    'date_debut': passage.date_debut,
                    'peut_etre_repris': passage.peut_etre_repris(),
                    'peut_etre_soumis': passage.peut_etre_soumis(),
                    'note': passage.note,
                    'est_corrige': passage.est_corrige
                }
                
                # Déterminer l'action possible
                if passage.statut == 'en_cours':
                    if passage.peut_etre_repris():
                        data['action_possible'] = 'reprendre'
                    else:
                        data['action_possible'] = 'date_expiree'
                elif passage.statut == 'soumis':
                    data['action_possible'] = 'en_attente_correction'
                elif passage.statut == 'corrige':
                    data['action_possible'] = 'voir_resultat'
            else:
                # Pas de passage
                if evaluation.est_accessible():
                    data['action_possible'] = 'commencer'
                else:
                    data['action_possible'] = 'non_accessible'
            
            serializer = EvaluationAccessibiliteSerializer(data)
            return api_success(
                "Informations d'accessibilité récupérées",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la vérification d'accessibilité",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# VUES POUR PASSAGES D'ÉVALUATIONS (NOUVELLE LOGIQUE)
# ============================================================================

class PassageEvaluationDemarrerAPIView(APIView):
    """Démarrer une nouvelle évaluation"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Démarre une évaluation pour un apprenant
        Body: {"apprenant": 1, "evaluation": 5}
        """
        try:
            apprenant_id = request.data.get('apprenant')
            evaluation_id = request.data.get('evaluation')
            
            if not apprenant_id or not evaluation_id:
                return api_error(
                    "Les champs 'apprenant' et 'evaluation' sont requis",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            evaluation = get_object_or_404(Evaluation, pk=evaluation_id)
            
            # Vérifier qu'il n'existe pas déjà un passage
            passage_existant = PassageEvaluation.objects.filter(
                apprenant_id=apprenant_id,
                evaluation=evaluation
            ).first()
            
            if passage_existant:
                return api_error(
                    f"Un passage existe déjà avec le statut: {passage_existant.statut}",
                    data={'passage_id': passage_existant.id, 'statut': passage_existant.statut},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérifier l'accessibilité
            if not evaluation.est_accessible():
                return api_error(
                    "Cette évaluation n'est pas accessible actuellement",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            # Créer le passage
            passage = PassageEvaluation.objects.create(
                apprenant_id=apprenant_id,
                evaluation=evaluation,
                statut='en_cours'
            )
            
            # Pour évaluations structurées, créer les réponses vides
            if evaluation.type_evaluation == 'structuree':
                for question in evaluation.questions.all():
                    ReponseQuestion.objects.create(
                        passage_evaluation=passage,
                        question=question,
                        statut='non_repondu'
                    )
            
            serializer = PassageEvaluationDetailSerializer(passage)
            return api_success(
                "Évaluation démarrée avec succès",
                serializer.data,
                status.HTTP_201_CREATED
            )
        except Exception as e:
            return api_error(
                "Erreur lors du démarrage de l'évaluation",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PassageEvaluationReprendreAPIView(APIView):
    """Reprendre une évaluation en cours"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """
        Récupère un passage en cours pour le reprendre
        Vérifie que le statut est 'en_cours' et que la date_fin n'est pas dépassée
        """
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            
            if passage.statut != 'en_cours':
                return api_error(
                    f"Ce passage ne peut pas être repris (statut: {passage.statut})",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            if not passage.peut_etre_repris():
                return api_error(
                    "La date limite pour cette évaluation est dépassée",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = PassageEvaluationDetailSerializer(passage)
            return api_success(
                "Passage récupéré pour reprise",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la reprise de l'évaluation",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PassageEvaluationSauvegarderAPIView(APIView):
    """Sauvegarder la progression (pour évaluations simples)"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, pk):
        """
        Sauvegarde les réponses d'une évaluation simple en cours
        Body: {"reponse_texte": "...", "fichier_reponse": file}
        """
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            
            if passage.statut != 'en_cours':
                return api_error(
                    "Impossible de sauvegarder après soumission",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            if passage.evaluation.type_evaluation != 'simple':
                return api_error(
                    "Cette route est uniquement pour les évaluations simples",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Mise à jour partielle
            serializer = PassageEvaluationSerializer(
                passage, 
                data=request.data, 
                partial=True
            )
            
            if serializer.is_valid():
                passage = serializer.save()
                return api_success(
                    "Progression sauvegardée",
                    PassageEvaluationSerializer(passage).data,
                    status.HTTP_200_OK
                )
            
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la sauvegarde",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PassageEvaluationSoumettreAPIView(APIView):
    """Soumettre une évaluation (bascule irréversible)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """
        Soumet une évaluation pour correction
        - Vérifie que le statut est 'en_cours'
        - Vérifie que la date_fin n'est pas dépassée
        - Auto-corrige si 100% QCM
        - Sinon, passe en statut 'soumis'
        """
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            
            # Vérifications
            if passage.statut != 'en_cours':
                return api_error(
                    f"Cette évaluation a déjà été soumise (statut: {passage.statut})",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            if not passage.peut_etre_soumis():
                return api_error(
                    "La date limite pour soumettre cette évaluation est dépassée",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            # Vérifications spécifiques selon le type
            if passage.evaluation.type_evaluation == 'structuree':
                # Vérifier qu'au moins une question a été répondue (optionnel)
                questions_repondues = passage.reponses_questions.exclude(
                    statut='non_repondu'
                ).count()
                
                if questions_repondues == 0:
                    return api_error(
                        "Aucune question n'a été répondue",
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            
            elif passage.evaluation.type_evaluation == 'simple':
                # Vérifier qu'il y a au moins une réponse
                if not passage.reponse_texte and not passage.fichier_reponse:
                    return api_error(
                        "Aucune réponse fournie",
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Passer en statut soumis
            passage.statut = 'soumis'
            passage.date_soumission = timezone.now()
            passage.save()
            
            # Tentative d'auto-correction
            if passage.evaluation.type_evaluation == 'structuree':
                if passage.evaluation.est_auto_corrigeable():
                    # Auto-correction complète
                    passage.auto_corriger()
                    message = "Évaluation soumise et corrigée automatiquement"
                else:
                    # Auto-correction des QCM uniquement
                    passage.auto_corriger_qcm_uniquement()
                    message = "Évaluation soumise, en attente de correction"
            else:
                # Évaluation simple : toujours correction manuelle
                message = "Évaluation soumise, en attente de correction"
            
            serializer = PassageEvaluationDetailSerializer(passage)
            return api_success(
                message,
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la soumission de l'évaluation",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PassageEvaluationListAPIView(APIView):
    """Liste des passages d'évaluations avec filtres"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste des passages d'évaluations"""
        try:
            apprenant_id = request.query_params.get('apprenant')
            evaluation_id = request.query_params.get('evaluation')
            statut = request.query_params.get('statut')
            
            passages = PassageEvaluation.objects.select_related(
                'apprenant',
                'evaluation'
            ).prefetch_related('reponses_questions').all()
            
            if apprenant_id:
                passages = passages.filter(apprenant_id=apprenant_id)
            if evaluation_id:
                passages = passages.filter(evaluation_id=evaluation_id)
            if statut:
                passages = passages.filter(statut=statut)
            
            serializer = PassageEvaluationSerializer(passages, many=True)
            return api_success(
                "Liste des passages d'évaluations récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des passages",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PassageEvaluationDetailAPIView(APIView):
    """Détails d'un passage d'évaluation"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'un passage d'évaluation"""
        passage = get_object_or_404(PassageEvaluation, pk=pk)
        serializer = PassageEvaluationDetailSerializer(passage)
        return api_success(
            "Détails du passage d'évaluation récupérés avec succès",
            serializer.data,
            status.HTTP_200_OK
        )


# ============================================================================
# VUES POUR RÉPONSES AUX QUESTIONS D'ÉVALUATION
# ============================================================================

class ReponseQuestionSauvegarderAPIView(APIView):
    """Sauvegarder une réponse à une question (pendant l'évaluation)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Crée ou met à jour une réponse à une question
        Body: {
            "passage_evaluation": 1,
            "question": 5,
            "choix_selectionnes": [2],
            "reponse_texte": "...",
            "fichier_reponse": file
        }
        """
        try:
            passage_evaluation_id = request.data.get('passage_evaluation')
            question_id = request.data.get('question')
            
            if not passage_evaluation_id or not question_id:
                return api_error(
                    "Les champs 'passage_evaluation' et 'question' sont requis",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            passage = get_object_or_404(PassageEvaluation, pk=passage_evaluation_id)
            
            # Vérifier que le passage est en cours
            if passage.statut != 'en_cours':
                return api_error(
                    "Impossible de modifier après soumission",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Récupérer ou créer la réponse
            reponse, created = ReponseQuestion.objects.get_or_create(
                passage_evaluation_id=passage_evaluation_id,
                question_id=question_id
            )
            
            # Mise à jour
            if 'choix_selectionnes' in request.data:
                reponse.choix_selectionnes.set(request.data['choix_selectionnes'])
            
            if 'reponse_texte' in request.data:
                reponse.reponse_texte = request.data['reponse_texte']
            
            if 'fichier_reponse' in request.FILES:
                reponse.fichier_reponse = request.FILES['fichier_reponse']
            
            # Marquer comme répondu si pas vide
            if (reponse.choix_selectionnes.exists() or 
                reponse.reponse_texte or 
                reponse.fichier_reponse):
                reponse.statut = 'repondu'
            else:
                reponse.statut = 'non_repondu'
            
            reponse.save()
            
            serializer = ReponseQuestionSerializer(reponse)
            return api_success(
                "Réponse sauvegardée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la sauvegarde de la réponse",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReponseQuestionDetailAPIView(APIView):
    """Détails d'une réponse à une question"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Récupère les détails d'une réponse"""
        reponse = get_object_or_404(ReponseQuestion, pk=pk)
        serializer = ReponseQuestionSerializer(reponse)
        return api_success(
            "Réponse trouvée avec succès",
            serializer.data,
            status.HTTP_200_OK
        )


# ============================================================================
# VUES POUR CORRECTION (ENSEIGNANTS)
# ============================================================================

class CorrectionReponseAPIView(APIView):
    """Corriger une réponse individuelle (correction manuelle)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """
        Corrige une réponse manuelle
        Body: {
            "points_obtenus": 7.5,
            "commentaire_correcteur": "Bonne réponse mais..."
        }
        """
        try:
            reponse = get_object_or_404(ReponseQuestion, pk=pk)
            
            # Vérifier que la question nécessite correction manuelle
            if reponse.question.mode_correction == 'automatique':
                return api_error(
                    "Cette question est corrigée automatiquement",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérifier que le passage est soumis
            if reponse.passage_evaluation.statut != 'soumis':
                return api_error(
                    "Le passage doit être soumis pour être corrigé",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = CorrectionReponseSerializer(reponse, data=request.data, partial=True)
            if serializer.is_valid():
                reponse = serializer.save()
                reponse.statut = 'corrige'
                reponse.date_correction = timezone.now()
                reponse.save()
                
                return api_success(
                    "Réponse corrigée avec succès",
                    ReponseQuestionSerializer(reponse).data,
                    status.HTTP_200_OK
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la correction",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CorrectionEvaluationAPIView(APIView):
    """Corriger une évaluation complète et attribuer la note finale"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """
        Corrige une évaluation complète
        Body: {
            "note": 15.5,
            "commentaire_enseignant": "Bon travail général..."
        }
        """
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            
            # Vérifier que le passage est soumis
            if passage.statut != 'soumis':
                return api_error(
                    "Le passage doit être soumis pour être corrigé",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Pour évaluations structurées, vérifier que toutes les réponses manuelles sont corrigées
            if passage.evaluation.type_evaluation == 'structuree':
                reponses_non_corrigees = passage.reponses_questions.filter(
                    question__mode_correction='manuelle',
                    statut__in=['non_repondu', 'repondu']
                ).count()
                
                if reponses_non_corrigees > 0:
                    return api_error(
                        f"{reponses_non_corrigees} réponse(s) manuelle(s) non corrigée(s)",
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Calculer la note automatiquement basée sur les réponses
                note_calculee = sum(
                    float(r.points_obtenus or 0) 
                    for r in passage.reponses_questions.all()
                )
                
                # Utiliser la note fournie ou la note calculée
                note_finale = request.data.get('note', note_calculee)
            else:
                # Pour évaluation simple, utiliser la note fournie
                note_finale = request.data.get('note')
                if note_finale is None:
                    return api_error(
                        "La note est requise pour les évaluations simples",
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            
            passage.note = note_finale
            passage.commentaire_enseignant = request.data.get('commentaire_enseignant', '')
            passage.statut = 'corrige'
            passage.date_correction = timezone.now()
            passage.save()
            
            serializer = PassageEvaluationDetailSerializer(passage)
            return api_success(
                "Évaluation corrigée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la correction de l'évaluation",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EvaluationsACorrigerAPIView(APIView):
    """Liste des évaluations en attente de correction"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère les évaluations en attente de correction"""
        try:
            enseignant_id = request.query_params.get('enseignant')
            
            passages = PassageEvaluation.objects.select_related(
                'apprenant',
                'evaluation'
            ).filter(statut='soumis')
            
            if enseignant_id:
                passages = passages.filter(evaluation__enseignant_id=enseignant_id)
            
            serializer = PassageEvaluationSerializer(passages, many=True)
            return api_success(
                "Liste des évaluations à corriger récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des évaluations à corriger",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# VUES STATISTIQUES
# ============================================================================

class StatistiquesApprenantAPIView(APIView):
    """Statistiques d'un apprenant"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, apprenant_id):
        """Récupère les statistiques complètes d'un apprenant"""
        try:
            # Quiz
            passages_quiz = PassageQuiz.objects.filter(
                apprenant_id=apprenant_id,
                termine=True
            )
            
            # Évaluations
            passages_eval = PassageEvaluation.objects.filter(
                apprenant_id=apprenant_id
            )
            
            passages_corriges = passages_eval.filter(statut='corrige')
            
            score_moyen_quiz = passages_quiz.aggregate(Avg('score'))['score__avg']
            note_moyenne_eval = passages_corriges.aggregate(Avg('note'))['note__avg']
            
            stats = {
                'apprenant_id': apprenant_id,
                
                # Quiz
                'nombre_quiz_passes': passages_quiz.count(),
                'score_moyen_quiz': round(score_moyen_quiz, 2) if score_moyen_quiz else 0,
                
                # Évaluations
                'nombre_evaluations_passees': passages_eval.count(),
                'nombre_evaluations_corrigees': passages_corriges.count(),
                'nombre_evaluations_en_attente': passages_eval.filter(statut='soumis').count(),
                'note_moyenne': round(note_moyenne_eval, 2) if note_moyenne_eval else 0,
            }
            
            return api_success(
                "Statistiques de l'apprenant récupérées avec succès",
                stats,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du calcul des statistiques",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StatistiquesEvaluationAPIView(APIView):
    """Statistiques d'une évaluation"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, evaluation_id):
        """Récupère les statistiques d'une évaluation"""
        try:
            passages = PassageEvaluation.objects.filter(
                evaluation_id=evaluation_id,
                statut='corrige'
            )
            
            if not passages.exists():
                return api_success(
                    "Aucun passage corrigé pour cette évaluation",
                    {
                        'evaluation_id': evaluation_id,
                        'nombre_passages': 0
                    },
                    status.HTTP_200_OK
                )
            
            notes = list(passages.values_list('note', flat=True))
            bareme = passages.first().evaluation.bareme
            
            stats = {
                'evaluation_id': evaluation_id,
                'nombre_passages': len(notes),
                'note_moyenne': round(sum(notes) / len(notes), 2),
                'note_min': round(min(notes), 2),
                'note_max': round(max(notes), 2),
                'taux_reussite': round(len([n for n in notes if n >= bareme/2]) / len(notes) * 100, 2),
                'bareme': bareme,
            }
            
            return api_success(
                "Statistiques de l'évaluation récupérées avec succès",
                stats,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du calcul des statistiques",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class EvaluationExportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        evaluation = get_object_or_404(Evaluation, pk=pk)

        export_format = request.query_params.get("format", "csv").lower()
        detail = request.query_params.get("detail", "false").lower() == "true"

        # Récupérer passages + apprenants
        passages = (
            PassageEvaluation.objects
            .select_related("apprenant", "apprenant__user", "evaluation", "evaluation__cours")
            .filter(evaluation=evaluation)
            .order_by("apprenant__user__last_name", "apprenant__user__first_name")
        )

        if export_format == "csv":
            if detail:
                return self._export_detail_csv(evaluation, passages)
            return self._export_resume_csv(evaluation, passages)

        if export_format == "xlsx":
            if detail:
                return self._export_detail_xlsx(evaluation, passages)
            return self._export_resume_xlsx(evaluation, passages)

        return api_error(
            "Format non supporté",
            errors={"format": "Utilise csv ou xlsx"},
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def _export_resume_csv(self, evaluation, passages):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_resume.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "evaluation_id", "evaluation", "cours",
            "apprenant_id", "nom", "prenom", "email",
            "statut", "note", "bareme", "pourcentage",
            "date_debut", "date_soumission", "date_correction"
        ])

        for p in passages:
            user = getattr(p.apprenant, "user", None)
            nom = getattr(user, "last_name", "") if user else ""
            prenom = getattr(user, "first_name", "") if user else ""
            email = getattr(user, "email", "") if user else ""

            writer.writerow([
                evaluation.id,
                evaluation.titre,
                evaluation.cours.titre if evaluation.cours else "",
                p.apprenant_id,
                nom,
                prenom,
                email,
                p.statut,
                p.note if p.note is not None else "",
                evaluation.bareme,
                p.pourcentage() if p.pourcentage() is not None else "",
                p.date_debut,
                p.date_soumission,
                p.date_correction,
            ])

        return response

    def _export_detail_csv(self, evaluation, passages):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_detail.csv"'
        writer = csv.writer(response)

        writer.writerow([
            "evaluation_id", "evaluation", "cours",
            "apprenant_id", "nom", "prenom", "email",
            "statut_passage",
            "question_id", "ordre", "type_question",
            "enonce",
            "statut_reponse", "points_obtenus", "points_question",
            "reponse_texte", "fichier_reponse", "choix_selectionnes"
        ])

        # Charger réponses questions en batch
        passage_ids = list(passages.values_list("id", flat=True))
        reponses = (
            ReponseQuestion.objects
            .select_related(
                "passage_evaluation", "passage_evaluation__apprenant", "passage_evaluation__apprenant__user",
                "question"
            )
            .prefetch_related("choix_selectionnes")
            .filter(passage_evaluation_id__in=passage_ids)
            .order_by("passage_evaluation__apprenant__user__last_name", "question__ordre")
        )

        # Map passage_id -> PassageEvaluation pour accéder au statut + user
        passage_map = {p.id: p for p in passages}

        for rq in reponses:
            p = passage_map.get(rq.passage_evaluation_id)
            user = getattr(p.apprenant, "user", None) if p else None

            choix_txt = "; ".join(list(rq.choix_selectionnes.values_list("texte", flat=True)))

            writer.writerow([
                evaluation.id,
                evaluation.titre,
                evaluation.cours.titre if evaluation.cours else "",
                p.apprenant_id if p else "",
                getattr(user, "last_name", "") if user else "",
                getattr(user, "first_name", "") if user else "",
                getattr(user, "email", "") if user else "",
                p.statut if p else "",
                rq.question_id,
                rq.question.ordre,
                rq.question.type_question,
                (rq.question.enonce_texte or "")[:200],  # limiter la taille
                rq.statut,
                rq.points_obtenus,
                rq.question.points,
                (rq.reponse_texte or "")[:200],
                rq.fichier_reponse.url if rq.fichier_reponse else "",
                choix_txt,
            ])

        return response

    # -------- XLSX (nécessite openpyxl) --------
    def _export_resume_xlsx(self, evaluation, passages):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Résumé"

        ws.append([
            "evaluation_id", "evaluation", "cours",
            "apprenant_id", "nom", "prenom", "email",
            "statut", "note", "bareme", "pourcentage",
            "date_debut", "date_soumission", "date_correction"
        ])

        for p in passages:
            user = getattr(p.apprenant, "user", None)
            ws.append([
                evaluation.id,
                evaluation.titre,
                evaluation.cours.titre if evaluation.cours else "",
                p.apprenant_id,
                getattr(user, "last_name", "") if user else "",
                getattr(user, "first_name", "") if user else "",
                getattr(user, "email", "") if user else "",
                p.statut,
                p.note if p.note is not None else "",
                evaluation.bareme,
                p.pourcentage() if p.pourcentage() is not None else "",
                p.date_debut,
                p.date_soumission,
                p.date_correction,
            ])

        buff = BytesIO()
        wb.save(buff)
        buff.seek(0)

        response = HttpResponse(
            buff.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_resume.xlsx"'
        return response

    def _export_detail_xlsx(self, evaluation, passages):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Détail"

        ws.append([
            "evaluation_id", "evaluation", "cours",
            "apprenant_id", "nom", "prenom", "email",
            "statut_passage",
            "question_id", "ordre", "type_question",
            "enonce",
            "statut_reponse", "points_obtenus", "points_question",
            "reponse_texte", "fichier_reponse", "choix_selectionnes"
        ])

        passage_ids = list(passages.values_list("id", flat=True))
        reponses = (
            ReponseQuestion.objects
            .select_related(
                "passage_evaluation", "passage_evaluation__apprenant", "passage_evaluation__apprenant__user",
                "question"
            )
            .prefetch_related("choix_selectionnes")
            .filter(passage_evaluation_id__in=passage_ids)
            .order_by("passage_evaluation__apprenant__user__last_name", "question__ordre")
        )
        passage_map = {p.id: p for p in passages}

        for rq in reponses:
            p = passage_map.get(rq.passage_evaluation_id)
            user = getattr(p.apprenant, "user", None) if p else None
            choix_txt = "; ".join(list(rq.choix_selectionnes.values_list("texte", flat=True)))

            ws.append([
                evaluation.id,
                evaluation.titre,
                evaluation.cours.titre if evaluation.cours else "",
                p.apprenant_id if p else "",
                getattr(user, "last_name", "") if user else "",
                getattr(user, "first_name", "") if user else "",
                getattr(user, "email", "") if user else "",
                p.statut if p else "",
                rq.question_id,
                rq.question.ordre,
                rq.question.type_question,
                (rq.question.enonce_texte or "")[:200],
                rq.statut,
                rq.points_obtenus,
                rq.question.points,
                (rq.reponse_texte or "")[:200],
                rq.fichier_reponse.url if rq.fichier_reponse else "",
                choix_txt,
            ])

        buff = BytesIO()
        wb.save(buff)
        buff.seek(0)

        response = HttpResponse(
            buff.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="evaluation_{evaluation.id}_detail.xlsx"'
        return response