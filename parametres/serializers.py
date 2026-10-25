# parametres/serializers.py
from rest_framework import serializers
from .models import ParametresPlateforme, ParametresInstitution, PreferencesUtilisateur


class ParametresPlateformeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ParametresPlateforme
        exclude = ['id']


class ParametresInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ParametresInstitution
        exclude = ['id', 'institution']


class PreferencesUtilisateurSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PreferencesUtilisateur
        exclude = ['id', 'user']
