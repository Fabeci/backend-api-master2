from rest_framework import serializers
from .models import Quiz, Question, Reponse, Evaluation, ApprenantEvaluation, Solution

class QuizSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ['id', 'titre', 'sequence', 'date_creation']

class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'texte', 'quiz', 'evaluation', 'type_question']

class ReponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reponse
        fields = ['id', 'texte', 'question', 'est_correcte', 'est_choix_unique', 'est_choix_multiple']

class EvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evaluation
        fields = ['id', 'cours', 'bareme', 'date_passage']

class ApprenantEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprenantEvaluation
        fields = ['id', 'apprenant', 'evaluation', 'note', 'date_passage']

class SolutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Solution
        fields = ['id', 'question']
