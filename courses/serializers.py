from ast import Module
from rest_framework import serializers

from users.serializers import ApprenantSerializer, FormateurSerializer
from .models import Cours, InscriptionCours, Participation, Sequence, Session, Suivi
        
        
class CoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cours
        fields = ['id', 'nom', 'description']  # Ajouter les champs de votre modèle Cours

class ModuleSerializer(serializers.ModelSerializer):
    cours = CoursSerializer()

    class Meta:
        model = Module
        fields = ['id', 'titre', 'description', 'cours']

class SequenceSerializer(serializers.ModelSerializer):
    # Sérialiser l'attribut module lié (clé étrangère)
    module = ModuleSerializer()  # Utilisation d'un serializer imbriqué pour 'module'

    class Meta:
        model = Sequence
        fields = ['id', 'titre', 'module']

class InscriptionCoursSerializer(serializers.ModelSerializer):
    # Sérialiser les relations apprenant et cours avec des serializers imbriqués
    apprenant = ApprenantSerializer()
    cours = CoursSerializer()

    class Meta:
        model = InscriptionCours
        fields = ['id', 'apprenant', 'cours', 'date_inscription', 'statut']
        
        
class SuiviSerializer(serializers.ModelSerializer):
    apprenant = ApprenantSerializer()
    cours = CoursSerializer()

    class Meta:
        model = Suivi
        fields = ['id', 'apprenant', 'cours', 'date_debut', 'progression', 'note', 'commentaires']
        
        
class SessionSerializer(serializers.ModelSerializer):
    formateur = FormateurSerializer()
    cours = CoursSerializer()

    class Meta:
        model = Session
        fields = ['id', 'titre', 'date_debut', 'date_fin', 'formateur', 'cours']
        
        
class ParticipationSerializer(serializers.ModelSerializer):
    session = SessionSerializer()  # Sérialiser la session liée
    apprenant = ApprenantSerializer()  # Sérialiser l'apprenant lié

    class Meta:
        model = Participation
        fields = ['id', 'session', 'apprenant', 'date_participation']