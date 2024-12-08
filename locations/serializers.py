from rest_framework import serializers
from .models import Pays, Ville, Quartier

class PaysSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pays
        fields = ['id', 'nom', 'code']

class VilleSerializer(serializers.ModelSerializer):
    pays = PaysSerializer()  # Sérialisation du pays
    class Meta:
        model = Ville
        fields = ['id', 'nom', 'pays']

class QuartierSerializer(serializers.ModelSerializer):
    ville = VilleSerializer()  # Sérialisation de la ville
    class Meta:
        model = Quartier
        fields = ['id', 'nom', 'ville']