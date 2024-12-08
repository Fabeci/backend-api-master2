from django.shortcuts import render
from rest_framework import viewsets
from .models import Pays, Ville, Quartier
from .serializers import PaysSerializer, VilleSerializer, QuartierSerializer
# Create your views here.

class PaysViewSet(viewsets.ModelViewSet):
    queryset = Pays.objects.all()
    serializer_class = PaysSerializer

class VilleViewSet(viewsets.ModelViewSet):
    queryset = Ville.objects.all()
    serializer_class = VilleSerializer

class QuartierViewSet(viewsets.ModelViewSet):
    queryset = Quartier.objects.all()
    serializer_class = QuartierSerializer