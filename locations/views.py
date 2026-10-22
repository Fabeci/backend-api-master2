from django.shortcuts import render
from rest_framework import viewsets, permissions
from .models import Pays, Ville, Quartier
from .serializers import PaysSerializer, VilleSerializer, QuartierSerializer
# Create your views here.

# Lecture publique (les formulaires d'inscription/onboarding ont besoin des
# référentiels pays/villes/quartiers). Écriture réservée aux utilisateurs
# authentifiés — auparavant ces ViewSets étaient accessibles en anonyme.
class PaysViewSet(viewsets.ModelViewSet):
    queryset = Pays.objects.all()
    serializer_class = PaysSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class VilleViewSet(viewsets.ModelViewSet):
    queryset = Ville.objects.all()
    serializer_class = VilleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class QuartierViewSet(viewsets.ModelViewSet):
    queryset = Quartier.objects.all()
    serializer_class = QuartierSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
