from academics.models import DomaineEtude, Matiere
from academics.models import AnneeScolaire, DomaineEtude, Matiere, Specialite
from academics.serializers import AnneeScolaireSerializer, DomaineEtudeSerializer, MatiereSerializer, SpecialiteSerializer
from rest_framework import viewsets, status # type: ignore

class DomaineEtudeViewSet(viewsets.ModelViewSet):
    queryset = DomaineEtude.objects.all()
    serializer_class = DomaineEtudeSerializer
    

class MatiereViewSet(viewsets.ModelViewSet):
    queryset = Matiere.objects.all()
    serializer_class = MatiereSerializer
    
    
class SpecialiteViewSet(viewsets.ModelViewSet):
    queryset = Specialite.objects.all()
    serializer_class = SpecialiteSerializer
    
    
class AnneeScolaireViewSet(viewsets.ModelViewSet):
    queryset = AnneeScolaire.objects.all()
    serializer_class = AnneeScolaireSerializer