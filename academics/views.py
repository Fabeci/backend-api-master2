# -*- coding: utf-8 -*-
# academics/views.py - VERSION AVEC FILTRAGE PAR RÔLE

import secrets
import string
import uuid
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404

from academics.models import (
    Classe, Departement, Filiere, Groupe,
    Inscription, Institution, Matiere, Specialite, DomaineEtude
)
from academics.serializers import (
    ClasseSerializer, DepartementSerializer, FiliereSerializer,
    GroupeSerializer, InscriptionSerializer, InstitutionSerializer
)

# Import des utilitaires de filtrage
from .utils import (
    get_user_academic_context,
    filter_academics_queryset,
    get_filtered_academic_object,
    can_modify_academic_resource
)


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    return Response({
        "success": True,
        "status": http_status,
        "message": message,
        "data": data,
    }, status=http_status)


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST, data=None):
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
        "data": data,
    }
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# ============================================================================
# INSTITUTION
# ============================================================================

class InstitutionAPIView(APIView):
    """
    Gestion des institutions avec filtrage par rôle.

    - SuperUser : Toutes les institutions
    - Admin/Responsable : Leur institution uniquement
    - Formateur/Apprenant : Leur institution uniquement
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        if pk:
            # Détail : vérifier l'accès
            institution = get_filtered_academic_object(Institution, pk, request, "Institution")
            serializer = InstitutionSerializer(institution)
            return api_success("Institution trouvée", serializer.data, status.HTTP_200_OK)

        # Liste : filtrée par rôle
        qs = Institution.objects.all()
        qs = filter_academics_queryset(qs, request, "Institution", is_detail=False)

        serializer = InstitutionSerializer(qs, many=True)
        return api_success("Liste des institutions", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        """Création (Admin/SuperUser uniquement)"""
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name != "Admin":
            return api_error(
                "Seuls les Admins peuvent créer des institutions",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = InstitutionSerializer(data=request.data)
        if serializer.is_valid():
            institution = serializer.save()
            return api_success(
                "Institution créée avec succès",
                InstitutionSerializer(institution).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def put(self, request, pk):
        institution = get_filtered_academic_object(Institution, pk, request, "Institution")

        if not can_modify_academic_resource(request.user, institution, "Institution"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InstitutionSerializer(institution, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Institution mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        institution = get_filtered_academic_object(Institution, pk, request, "Institution")

        if not can_modify_academic_resource(request.user, institution, "Institution"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InstitutionSerializer(institution, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Institution mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        institution = get_filtered_academic_object(Institution, pk, request, "Institution")

        if not can_modify_academic_resource(request.user, institution, "Institution"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        institution.delete()
        return api_success("Institution supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# GROUPE
# ============================================================================

class GroupeListCreateAPIView(APIView):
    """
    Liste et création de groupes.

    LISTE :
    - Admin/Responsable : Tous les groupes de l'institution
    - Formateur : Tous les groupes de l'institution (vue d'ensemble)
    - Apprenant : Tous les groupes de l'institution (pour explorer)

    CRÉATION :
    - Admin/Responsable uniquement
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Groupe.objects.all().prefetch_related("enseignants")
        qs = filter_academics_queryset(qs, request, "Groupe", is_detail=False)

        serializer = GroupeSerializer(qs, many=True)
        return api_success("Liste des groupes", serializer.data, status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des groupes",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = GroupeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Auto-assigner l'institution si non fournie
        if not request.user.is_superuser and "institution" not in request.data:
            serializer.validated_data["institution_id"] = request.user.institution_id

        groupe = serializer.save()
        return api_success("Groupe créé avec succès", GroupeSerializer(groupe).data, status.HTTP_201_CREATED)


class GroupeDetailAPIView(APIView):
    """
    Détails, mise à jour et suppression d'un groupe.

    DÉTAIL :
    - Admin/Responsable : Tous les groupes de l'institution
    - Formateur : Uniquement SES groupes (où il enseigne)
    - Apprenant : Uniquement SON groupe
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_academic_object(Groupe, pk, request, "Groupe")

    def get(self, request, pk):
        groupe = self.get_object(pk, request)
        serializer = GroupeSerializer(groupe)
        return api_success("Groupe trouvé", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        groupe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, groupe, "Groupe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = GroupeSerializer(groupe, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Groupe mis à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        groupe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, groupe, "Groupe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = GroupeSerializer(groupe, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Groupe mis à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        groupe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, groupe, "Groupe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        groupe.delete()
        return api_success("Groupe supprimé", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# CLASSE
# ============================================================================

class ClasseListCreateAPIView(APIView):
    """
    Liste et création de classes.

    Même logique que Groupe.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Classe.objects.all()
        qs = filter_academics_queryset(qs, request, "Classe", is_detail=False)

        serializer = ClasseSerializer(qs, many=True)
        return api_success("Liste des classes", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des classes",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = ClasseSerializer(data=request.data)
        if serializer.is_valid():
            # Auto-assigner l'institution
            if not request.user.is_superuser and "institution" not in request.data:
                serializer.validated_data["institution_id"] = request.user.institution_id

            obj = serializer.save()
            return api_success("Classe créée avec succès", ClasseSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class ClasseDetailAPIView(APIView):
    """
    Détails d'une classe avec filtrage strict.

    - Formateur : Uniquement classes de SES groupes
    - Apprenant : Uniquement SA classe
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_academic_object(Classe, pk, request, "Classe")

    def get(self, request, pk):
        classe = self.get_object(pk, request)
        serializer = ClasseSerializer(classe)
        return api_success("Classe trouvée", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        classe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, classe, "Classe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = ClasseSerializer(classe, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Classe mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        classe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, classe, "Classe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = ClasseSerializer(classe, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Classe mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        classe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, classe, "Classe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        classe.delete()
        return api_success("Classe supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# FILIÈRE
# ============================================================================

class FiliereListCreateAPIView(APIView):
    """Filières : visibles par tous (modèle transversal)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Filiere.objects.all()
        qs = filter_academics_queryset(qs, request, "Filiere", is_detail=False)

        serializer = FiliereSerializer(qs, many=True)
        return api_success("Liste des filières", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des filières",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = FiliereSerializer(data=request.data)
        if serializer.is_valid():
            filiere = serializer.save()
            return api_success("Filière créée avec succès", FiliereSerializer(filiere).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class FiliereDetailAPIView(APIView):
    """Détail d'une filière"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(Filiere, pk=pk)

    def get(self, request, pk):
        filiere = self.get_object(pk)
        serializer = FiliereSerializer(filiere)
        return api_success("Filière trouvée", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        filiere = self.get_object(pk)

        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = FiliereSerializer(filiere, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Filière mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        filiere = self.get_object(pk)

        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = FiliereSerializer(filiere, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Filière mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        filiere = self.get_object(pk)

        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        filiere.delete()
        return api_success("Filière supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# DÉPARTEMENT
# ============================================================================

class DepartementListCreateAPIView(APIView):
    """Départements : filtrés par institution"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Departement.objects.select_related("institution", "responsable_academique")
        qs = filter_academics_queryset(qs, request, "Departement", is_detail=False)

        serializer = DepartementSerializer(qs, many=True)
        return api_success("Liste des départements", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des départements",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = DepartementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return api_success("Département créé avec succès", DepartementSerializer(obj).data, status.HTTP_201_CREATED)


class DepartementDetailAPIView(APIView):
    """Détail d'un département"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_academic_object(Departement, pk, request, "Departement")

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Département trouvé", DepartementSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Departement"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = DepartementSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success("Département mis à jour", serializer.data, status.HTTP_200_OK)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Departement"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = DepartementSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success("Département mis à jour partiellement", serializer.data, status.HTTP_200_OK)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Departement"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        obj.delete()
        return api_success("Département supprimé", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# INSCRIPTION
# ============================================================================

class InscriptionListCreateAPIView(APIView):
    """
    Inscriptions scolaires.

    - Admin/Responsable : Toutes les inscriptions de l'institution
    - Formateur : Inscriptions dans ses groupes/classes
    - Apprenant : Uniquement sa propre inscription
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Inscription.objects.all()
        qs = filter_academics_queryset(qs, request, "Inscription", is_detail=False)

        serializer = InscriptionSerializer(qs, many=True)
        return api_success("Liste des inscriptions", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "Responsable"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des inscriptions",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = InscriptionSerializer(data=request.data)
        if serializer.is_valid():
            # Auto-assigner l'institution
            if not request.user.is_superuser and "institution" not in request.data:
                serializer.validated_data["institution_id"] = request.user.institution_id

            obj = serializer.save()
            return api_success("Inscription créée avec succès", InscriptionSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class InscriptionDetailAPIView(APIView):
    """Détail d'une inscription"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_academic_object(Inscription, pk, request, "Inscription")

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Inscription trouvée", InscriptionSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Inscription"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InscriptionSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Inscription mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Inscription"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InscriptionSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Inscription mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Inscription"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        obj.delete()
        return api_success("Inscription supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)
