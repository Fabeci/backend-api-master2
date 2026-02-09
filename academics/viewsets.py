from academics.models import DomaineEtude, Matiere
from academics.models import AnneeScolaire, DomaineEtude, Matiere, Specialite
from academics.serializers import AnneeScolaireSerializer, DomaineEtudeSerializer, MatiereSerializer, SpecialiteSerializer
from rest_framework import viewsets, status

from users.utils import BaseModelViewSet # type: ignore

class DomaineEtudeViewSet(BaseModelViewSet):
    queryset = DomaineEtude.objects.all()
    serializer_class = DomaineEtudeSerializer


class MatiereViewSet(BaseModelViewSet):
    queryset = Matiere.objects.all()
    serializer_class = MatiereSerializer


class SpecialiteViewSet(BaseModelViewSet):
    queryset = Specialite.objects.all()
    serializer_class = SpecialiteSerializer


class AnneeScolaireViewSet(BaseModelViewSet):
    queryset = AnneeScolaire.objects.all()
    serializer_class = AnneeScolaireSerializer