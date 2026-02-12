# -*- coding: utf-8 -*-

from rest_framework import permissions
from academics.models import AnneeScolaire, DomaineEtude, Matiere, Specialite
from academics.serializers import (
    AnneeScolaireSerializer,
    DomaineEtudeSerializer,
    MatiereSerializer,
    SpecialiteSerializer,
)

from users.utils import BaseModelViewSet  # type: ignore
from academics.utils import filter_academics_queryset


class DomaineEtudeViewSet(BaseModelViewSet):
    queryset = DomaineEtude.objects.all()
    serializer_class = DomaineEtudeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        # list vs detail
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "DomaineEtude", is_detail=is_detail)


class MatiereViewSet(BaseModelViewSet):
    queryset = Matiere.objects.all()
    serializer_class = MatiereSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "Matiere", is_detail=is_detail)
    


class SpecialiteViewSet(BaseModelViewSet):
    queryset = Specialite.objects.all()
    serializer_class = SpecialiteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "Specialite", is_detail=is_detail)


class AnneeScolaireViewSet(BaseModelViewSet):
    queryset = AnneeScolaire.objects.all()
    serializer_class = AnneeScolaireSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "AnneeScolaire", is_detail=is_detail)
