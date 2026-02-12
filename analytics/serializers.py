from rest_framework import serializers
from .models import BlocAnalytics, ContenuGenere, RecommandationPedagogique

class BlocAnalyticsSerializer(serializers.ModelSerializer):
    bloc_titre = serializers.CharField(source='bloc.titre', read_only=True)
    
    class Meta:
        model = BlocAnalytics
        fields = '__all__'
        read_only_fields = ('premiere_visite', 'derniere_visite')


class ContenuGenereSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContenuGenere
        fields = '__all__'
        read_only_fields = ('date_generation', 'nombre_consultations')


class RecommandationSerializer(serializers.ModelSerializer):
    bloc_titre = serializers.CharField(source='bloc_cible.titre', read_only=True)
    
    class Meta:
        model = RecommandationPedagogique
        fields = '__all__'
        read_only_fields = ('date_creation', 'date_vue')