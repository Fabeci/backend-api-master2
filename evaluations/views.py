# evaluations/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Avg, Count, Q
from django.utils import timezone

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
# FONCTIONS UTILITAIRES (vos méthodes standards)
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
            # Filtrer par séquence si fournie
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
            # Filtrer par apprenant ou quiz
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
        """
        Soumet une réponse à une question de quiz
        Body: {
            "passage_quiz": 1,
            "question": 5,
            "choix_selectionnes": [2, 3]
        }
        """
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
            # Filtrer par quiz ou évaluation
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
            # Filtrer par question
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
            # Filtrer par cours ou enseignant
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
            action = request.data.get('action', 'publier')  # 'publier' ou 'depublier'
            
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


# ============================================================================
# VUES POUR PASSAGES D'ÉVALUATIONS
# ============================================================================

class PassageEvaluationListCreateAPIView(APIView):
    """Liste des passages d'évaluations ou création d'un nouveau passage"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Récupère la liste des passages d'évaluations"""
        try:
            # Filtrer par apprenant, évaluation ou statut
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
    
    def post(self, request):
        """Créer un nouveau passage d'évaluation"""
        serializer = PassageEvaluationCreateSerializer(data=request.data)
        if serializer.is_valid():
            passage = serializer.save()
            
            return api_success(
                "Passage d'évaluation créé avec succès",
                PassageEvaluationDetailSerializer(passage).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
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
    
    def put(self, request, pk):
        """Mettre à jour un passage (pour évaluation simple)"""
        passage = get_object_or_404(PassageEvaluation, pk=pk)
        serializer = PassageEvaluationSerializer(passage, data=request.data, partial=True)
        if serializer.is_valid():
            passage = serializer.save()
            return api_success(
                "Passage d'évaluation mis à jour avec succès",
                PassageEvaluationSerializer(passage).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class PassageEvaluationSoumettreAPIView(APIView):
    """Soumettre une évaluation"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        """Soumet une évaluation pour correction"""
        try:
            passage = get_object_or_404(PassageEvaluation, pk=pk)
            
            if passage.statut != 'en_cours':
                return api_error(
                    "Cette évaluation a déjà été soumise",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérifier que toutes les questions ont été répondues (pour structurée)
            if passage.evaluation.type_evaluation == 'structuree':
                questions_non_repondues = passage.reponses_questions.filter(
                    statut='non_repondu'
                ).count()
                
                if questions_non_repondues > 0:
                    return api_error(
                        f"{questions_non_repondues} question(s) non répondue(s)",
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Soumettre
            passage.statut = 'soumis'
            passage.date_soumission = timezone.now()
            passage.save()
            
            # Auto-correction des QCM
            for reponse in passage.reponses_questions.filter(
                question__mode_correction='automatique'
            ):
                reponse.calculer_points_automatique()
            
            # Calculer la note si tout est auto-corrigé
            if not passage.necessite_correction:
                total_points = sum(
                    r.points_obtenus 
                    for r in passage.reponses_questions.all()
                )
                passage.note = total_points
                passage.statut = 'corrige'
                passage.date_correction = timezone.now()
                passage.save()
            
            serializer = PassageEvaluationDetailSerializer(passage)
            return api_success(
                "Évaluation soumise avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la soumission de l'évaluation",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# VUES POUR RÉPONSES AUX QUESTIONS D'ÉVALUATION
# ============================================================================

class ReponseQuestionSubmitAPIView(APIView):
    """Soumettre une réponse à une question d'évaluation"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """
        Soumet une réponse à une question d'évaluation
        Body: {
            "passage_evaluation": 1,
            "question": 5,
            "choix_selectionnes": [2],  // Pour QCM
            "reponse_texte": "...",     // Pour texte
            "fichier_reponse": file     // Pour fichier
        }
        """
        serializer = ReponseQuestionCreateSerializer(data=request.data)
        if serializer.is_valid():
            reponse = serializer.save()
            return api_success(
                "Réponse enregistrée avec succès",
                ReponseQuestionSerializer(reponse).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def put(self, request, pk):
        """Modifier une réponse existante"""
        reponse = get_object_or_404(ReponseQuestion, pk=pk)
        
        # Vérifier que l'évaluation n'est pas encore soumise
        if reponse.passage_evaluation.statut != 'en_cours':
            return api_error(
                "Impossible de modifier après soumission",
                http_status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = ReponseQuestionSerializer(reponse, data=request.data, partial=True)
        if serializer.is_valid():
            reponse = serializer.save()
            return api_success(
                "Réponse mise à jour avec succès",
                ReponseQuestionSerializer(reponse).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
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
            
            serializer = CorrectionReponseSerializer(reponse, data=request.data, partial=True)
            if serializer.is_valid():
                reponse = serializer.save()
                return api_success(
                    "Réponse corrigée avec succès",
                    CorrectionReponseSerializer(reponse).data,
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
            
            # Vérifier que toutes les réponses manuelles sont corrigées
            reponses_non_corrigees = passage.reponses_questions.filter(
                question__mode_correction='manuelle',
                statut__in=['non_repondu', 'repondu']
            ).count()
            
            if reponses_non_corrigees > 0:
                return api_error(
                    f"{reponses_non_corrigees} réponse(s) non corrigée(s)",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = CorrectionEvaluationSerializer(passage, data=request.data, partial=True)
            if serializer.is_valid():
                passage = serializer.save()
                return api_success(
                    "Évaluation corrigée avec succès",
                    PassageEvaluationDetailSerializer(passage).data,
                    status.HTTP_200_OK
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
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
            # Filtrer par enseignant
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