from rest_framework import serializers
from .models import Ressource, RessourceSupplementaire, PieceJointe, RessourcePieceJointe, RessourceSuppPieceJointe

class RessourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ressource
        fields = ['id', 'titre', 'fichier', 'sequence', 'date_ajout']

class RessourceSupplementaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = RessourceSupplementaire
        fields = ['id', 'titre', 'fichier', 'sequence', 'apprenant', 'date_ajout']

class PieceJointeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PieceJointe
        fields = ['id', 'fichier', 'ressource', 'ressource_supplementaire']

class RessourcePieceJointeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RessourcePieceJointe
        fields = ['id', 'ressource', 'piece_jointe']

class RessourceSuppPieceJointeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RessourceSuppPieceJointe
        fields = ['id', 'ressource', 'piece_jointe']
