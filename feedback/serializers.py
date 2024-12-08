from rest_framework import serializers
from .models import Feedback, Progression, HistoriqueProgression, PlanAction

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ['id', 'cours', 'evaluation', 'auteur', 'destinataires', 'contenu', 'note', 'date_creation']

class ProgressionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Progression
        fields = ['id', 'apprenant', 'cours', 'pourcentage', 'date_mise_a_jour']

class HistoriqueProgressionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoriqueProgression
        fields = ['id', 'progression', 'date_changement', 'ancienne_progression', 'nouvelle_progression']

class PlanActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanAction
        fields = ['id', 'progression', 'description', 'date_creation', 'date_limite', 'complet']
