# -*- coding: utf-8 -*-
# academics/views.py - VERSION AVEC FILTRAGE PAR RÔLE

import secrets
import string
import uuid
from django.db import transaction
from core.rbac import RBACPermission
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework.parsers import MultiPartParser, FormParser

from rest_framework.permissions import AllowAny, IsAuthenticated
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

from rest_framework.throttling import AnonRateThrottle


class InstitutionCreateAnonThrottle(AnonRateThrottle):
    """Limite la création anonyme d'établissement (onboarding public)."""
    scope = "institution_create"
    rate = "5/hour"


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
    # Message plus précis quand des erreurs de champ sont fournies
    if errors and isinstance(errors, dict) and (not message or message == "Erreur de validation"):
        for _field, _val in errors.items():
            _msgs = _val if isinstance(_val, (list, tuple)) else [_val]
            _first = next((str(m) for m in _msgs if m), None)
            if _first:
                message = f"{_field} : {_first}"
                break
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
        "data": data,
    }
    _code_map = {
        400: "VALIDATION_ERROR", 401: "NOT_AUTHENTICATED", 403: "PERMISSION_DENIED",
        404: "NOT_FOUND", 409: "CONFLICT", 429: "THROTTLED",
    }
    payload["code"] = _code_map.get(http_status, "SERVER_ERROR" if http_status >= 500 else "ERROR")
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# ============================================================================
# INSTITUTION
# ============================================================================

class InstitutionAPIView(APIView):
    """
    - GET/PUT/PATCH/DELETE : Auth obligatoire + filtrage par rôle
    - POST : Auth obligatoire + RBAC (création PUBLIQUE retirée)
    """
    permission_classes = [IsAuthenticated, RBACPermission]  # défaut

    def get_permissions(self):
        # ✅ Création PUBLIQUE retirée : la création d'un établissement est
        #    désormais réservée aux profils authentifiés habilités (plus
        #    d'auto-inscription anonyme).
        return [IsAuthenticated(), RBACPermission()]

    def get_throttles(self):
        # ✅ Limite uniquement la création publique (onboarding) — corrige
        # l'absence de limitation sur un endpoint anonyme.
        if self.request.method == "POST" and not getattr(self.request.user, "is_authenticated", False):
            return [InstitutionCreateAnonThrottle()]
        return super().get_throttles()

    def get(self, request, pk=None):
        if pk:
            institution = get_filtered_academic_object(Institution, pk, request, "Institution")
            serializer = InstitutionSerializer(institution)
            return api_success("Institution trouvée", serializer.data, status.HTTP_200_OK)

        qs = Institution.objects.all()
        qs = filter_academics_queryset(qs, request, "Institution", is_detail=False)
        serializer = InstitutionSerializer(qs, many=True)
        return api_success("Liste des institutions", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        """
        Création d'établissement — réservée à l'administration (SuperAdmin/Admin).
        La création PUBLIQUE (auto-inscription) a été retirée.
        """
        user = request.user
        role = user.role.name if getattr(user, "role", None) else None
        if not (getattr(user, "is_superuser", False) or role == "Admin"):
            return api_error(
                "Création d'établissement réservée à l'administration.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        # ✅ sécurité : forcer un admin pour éviter institutions "orphelines"
        if not request.data.get("admin_account") and not request.data.get("existing_admin_id"):
            return api_error(
                "Vous devez fournir admin_account (création admin) ou existing_admin_id.",
                http_status=status.HTTP_400_BAD_REQUEST
            )

        serializer = InstitutionSerializer(data=request.data, context={"request": request})
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

        serializer = InstitutionSerializer(institution, data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return api_success("Institution mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        institution = get_filtered_academic_object(Institution, pk, request, "Institution")
        if not can_modify_academic_resource(request.user, institution, "Institution"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InstitutionSerializer(institution, data=request.data, partial=True, context={"request": request})
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


class InstitutionLogoUploadAPIView(APIView):
    """
    PATCH /api/institutions/<pk>/upload-logo/
    Upload ou suppression du logo d'une institution.
    Seul l'Admin de l'institution ou un SuperUser peut modifier le logo.
    """
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]   # ← parsers multipart explicites

    def patch(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)

        # Vérification des droits
        user = request.user
        role_name = getattr(getattr(user, "role", None), "name", None)
        is_admin_of_inst = (
            role_name == "Admin"
            and hasattr(user, "institution")
            and user.institution_id == institution.id
        )
        if not user.is_superuser and not is_admin_of_inst:
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        # Upload
        logo_file = request.FILES.get("logo")
        if logo_file:
            import os as _os
            _ext = _os.path.splitext(logo_file.name or '')[1].lower()
            if _ext not in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}:
                return api_error("Format d'image non autorisé (jpg, png, gif, webp).",
                                 http_status=status.HTTP_400_BAD_REQUEST)
            if logo_file.size > 5 * 1024 * 1024:
                return api_error("Logo trop volumineux (max 5 Mo).",
                                 http_status=status.HTTP_400_BAD_REQUEST)
            try:
                from PIL import Image
                Image.open(logo_file).verify()
                logo_file.seek(0)
            except Exception:
                return api_error("Fichier image invalide.",
                                 http_status=status.HTTP_400_BAD_REQUEST)
            # Supprimer l'ancien logo s'il existe
            if institution.logo:
                institution.logo.delete(save=False)
            institution.logo = logo_file
            institution.save(update_fields=["logo"])

            serializer = InstitutionSerializer(institution, context={"request": request})
            return api_success(
                "Logo mis à jour",
                {"logo_url": serializer.data.get("logo_url")},
                status.HTTP_200_OK,
            )

        # Suppression du logo
        if "remove_logo" in request.data and request.data["remove_logo"] in ("1", "true", "True"):
            if institution.logo:
                institution.logo.delete(save=False)
                institution.logo = None
                institution.save(update_fields=["logo"])
            return api_success("Logo supprimé", {"logo_url": None}, status.HTTP_200_OK)

        return api_error(
            "Aucun fichier fourni. Envoyez 'logo' (fichier) ou 'remove_logo=1'.",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
        
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        qs = Groupe.objects.all().prefetch_related("enseignants")
        qs = filter_academics_queryset(qs, request, "Groupe", is_detail=False)

        serializer = GroupeSerializer(qs, many=True)
        return api_success("Liste des groupes", serializer.data, status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "ResponsableAcademique"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des groupes",
                http_status=status.HTTP_403_FORBIDDEN
            )

        # L'institution est déduite du compte AVANT validation (le champ peut être requis).
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if not request.user.is_superuser and not data.get("institution"):
            data["institution"] = request.user.institution_id

        serializer = GroupeSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        qs = Classe.objects.all()
        qs = filter_academics_queryset(qs, request, "Classe", is_detail=False)

        serializer = ClasseSerializer(qs, many=True)
        return api_success("Liste des classes", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "ResponsableAcademique"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des classes",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = ClasseSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            # L'établissement est TOUJOURS celui du compte (mono-établissement).
            if not request.user.is_superuser:
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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

        serializer = ClasseSerializer(classe, data=request.data, context={"request": request})
        if serializer.is_valid():
            if not request.user.is_superuser:
                serializer.validated_data["institution_id"] = request.user.institution_id
            serializer.save()
            return api_success("Classe mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        classe = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, classe, "Classe"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = ClasseSerializer(classe, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            if not request.user.is_superuser:
                serializer.validated_data["institution_id"] = request.user.institution_id
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        qs = Filiere.objects.all()
        qs = filter_academics_queryset(qs, request, "Filiere", is_detail=False)
        serializer = FiliereSerializer(qs, many=True, context={"request": request})
        return api_success("Liste des filières", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "ResponsableAcademique"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des filières",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = FiliereSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            filiere = serializer.save()
            return api_success(
                "Filière créée avec succès",
                FiliereSerializer(filiere, context={"request": request}).data,
                status.HTTP_201_CREATED
            )
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class FiliereDetailAPIView(APIView):
    """Détail d'une filière (filtré par établissement)."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        return get_filtered_academic_object(Filiere, pk, request, "Filiere")

    def _peut_modifier(self, request, filiere):
        return (
            request.user.is_superuser
            or can_modify_academic_resource(request.user, filiere, "Filiere")
        )

    def get(self, request, pk):
        filiere = self.get_object(pk, request)
        serializer = FiliereSerializer(filiere, context={"request": request})
        return api_success("Filière trouvée", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        filiere = self.get_object(pk, request)
        if not self._peut_modifier(request, filiere):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = FiliereSerializer(filiere, data=request.data, context={"request": request})
        if serializer.is_valid():
            filiere = serializer.save()
            return api_success(
                "Filière mise à jour",
                FiliereSerializer(filiere, context={"request": request}).data,
                status.HTTP_200_OK
            )
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        filiere = self.get_object(pk, request)
        if not self._peut_modifier(request, filiere):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = FiliereSerializer(filiere, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            filiere = serializer.save()
            return api_success(
                "Filière mise à jour partiellement",
                FiliereSerializer(filiere, context={"request": request}).data,
                status.HTTP_200_OK
            )
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        filiere = self.get_object(pk, request)
        if not self._peut_modifier(request, filiere):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        filiere.delete()
        return api_success("Filière supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)

# ============================================================================
# DÉPARTEMENT
# ============================================================================

class DepartementListCreateAPIView(APIView):
    """Départements : filtrés par institution"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        qs = Departement.objects.select_related("institution", "responsable_academique")
        qs = filter_academics_queryset(qs, request, "Departement", is_detail=False)

        serializer = DepartementSerializer(qs, many=True)
        return api_success("Liste des départements", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "ResponsableAcademique"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des départements",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = DepartementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # L'établissement vient du compte connecté (mono-établissement).
        from core.tenant import default_institution
        institution = getattr(request.user, "institution", None) or default_institution()
        if not institution:
            return api_error(
                "Aucun établissement associé à votre compte.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        obj = serializer.save(institution=institution)
        return api_success("Département créé avec succès", DepartementSerializer(obj).data, status.HTTP_201_CREATED)


class DepartementDetailAPIView(APIView):
    """Détail d'un département"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        qs = Inscription.objects.all()
        qs = filter_academics_queryset(qs, request, "Inscription", is_detail=False)

        serializer = InscriptionSerializer(qs, many=True)
        return api_success("Liste des inscriptions", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        role_name = request.user.role.name if hasattr(request.user, "role") and request.user.role else None
        if not request.user.is_superuser and role_name not in ["Admin", "ResponsableAcademique"]:
            return api_error(
                "Seuls les Admins/Responsables peuvent créer des inscriptions",
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = InscriptionSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            # L'établissement est TOUJOURS celui du compte (mono-établissement).
            if not request.user.is_superuser:
                serializer.validated_data["institution_id"] = request.user.institution_id

            obj = serializer.save()
            return api_success("Inscription créée avec succès", InscriptionSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class InscriptionDetailAPIView(APIView):
    """Détail d'une inscription"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        return get_filtered_academic_object(Inscription, pk, request, "Inscription")

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Inscription trouvée", InscriptionSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Inscription"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InscriptionSerializer(obj, data=request.data, context={"request": request})
        if serializer.is_valid():
            if not request.user.is_superuser:
                serializer.validated_data["institution_id"] = request.user.institution_id
            serializer.save()
            return api_success("Inscription mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Inscription"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        serializer = InscriptionSerializer(obj, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            if not request.user.is_superuser:
                serializer.validated_data["institution_id"] = request.user.institution_id
            serializer.save()
            return api_success("Inscription mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_modify_academic_resource(request.user, obj, "Inscription"):
            return api_error("Accès refusé", http_status=status.HTTP_403_FORBIDDEN)

        obj.delete()
        return api_success("Inscription supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# LMD — BULLETIN (Sup'Info)
# ============================================================================

class BulletinAPIView(APIView):
    """Bulletin semestriel/annuel : moyennes EC → UE → semestre, crédits, mention."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    rbac_resource = "resultats"

    def get(self, request, apprenant_id, annee_id):
        from users.models import Apprenant
        from users.access_control import user_can_access_apprenant
        from .models import Semestre, AnneeScolaire
        from .services.lmd import bulletin

        apprenant = Apprenant.objects.filter(pk=apprenant_id).select_related("groupe__classe").first()
        if apprenant is None:
            return Response({"success": False, "status": 404, "message": "Apprenant introuvable."},
                            status=status.HTTP_404_NOT_FOUND)

        if not user_can_access_apprenant(request.user, apprenant):
            return Response({"success": False, "status": 403, "message": "Accès refusé."},
                            status=status.HTTP_403_FORBIDDEN)

        annee = AnneeScolaire.objects.filter(pk=annee_id).first()
        if annee is None:
            return Response({"success": False, "status": 404, "message": "Année scolaire introuvable."},
                            status=status.HTTP_404_NOT_FOUND)

        classe = getattr(getattr(apprenant, "groupe", None), "classe", None)
        semestres = (
            Semestre.objects.filter(classe=classe, annee_scolaire=annee).order_by("numero")
            if classe else Semestre.objects.none()
        )

        data = bulletin(apprenant, semestres, annee)
        return Response({"success": True, "status": 200, "message": "Bulletin.", "data": data},
                        status=status.HTTP_200_OK)


class BulletinExportAPIView(APIView):
    """Export CSV du bulletin (semestre → UE → EC + synthèse)."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    rbac_resource = "resultats"

    def get(self, request, apprenant_id, annee_id):
        import csv
        from django.http import HttpResponse
        from users.models import Apprenant
        from users.access_control import user_can_access_apprenant
        from .models import Semestre, AnneeScolaire
        from .services.lmd import bulletin

        apprenant = Apprenant.objects.filter(pk=apprenant_id).select_related("groupe__classe").first()
        if apprenant is None:
            return Response({"success": False, "message": "Apprenant introuvable."}, status=404)
        if not user_can_access_apprenant(request.user, apprenant):
            return Response({"success": False, "message": "Accès refusé."}, status=403)

        annee = AnneeScolaire.objects.filter(pk=annee_id).first()
        if annee is None:
            return Response({"success": False, "message": "Année introuvable."}, status=404)

        classe = getattr(getattr(apprenant, "groupe", None), "classe", None)
        semestres = (Semestre.objects.filter(classe=classe, annee_scolaire=annee).order_by("numero")
                     if classe else Semestre.objects.none())

        data = bulletin(apprenant, semestres, annee)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="bulletin_{apprenant_id}_{annee_id}.csv"'
        response.write("\ufeff")  # BOM Excel
        w = csv.writer(response, delimiter=";")
        w.writerow(["SOMAPRO - Bulletin", f"{apprenant.prenom} {apprenant.nom}", str(annee)])
        w.writerow([])
        w.writerow(["Semestre", "UE", "EC", "Crédits", "Coefficient", "Moyenne", "État"])

        for s in data["semestres"]:
            for u in s["ues"]:
                w.writerow([s["libelle"], f'{u["code"]} — {u["libelle"]}', "",
                            u["credits"], u["coefficient"], u["moyenne"] or "",
                            "Validée" if u["valide"] else "Ajournée"])
                for e in u["ecs"]:
                    w.writerow(["", "", e["code"], e["credits"], e["coefficient"],
                                e["moyenne"] or "", ""])

        w.writerow([])
        w.writerow(["Moyenne annuelle", data["moyenne_annee"] or ""])
        w.writerow(["Crédits acquis", f'{data["credits_acquis"]}/{data["credits_annee"]}'])
        w.writerow(["Mention", data["mention"] or ""])
        w.writerow(["Décision", "Admis" if data["valide_annee"] else "Ajourné"])
        return response


class BulletinPDFAPIView(APIView):
    """Bulletin au format PDF (ReportLab)."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    rbac_resource = "resultats"

    def get(self, request, apprenant_id, annee_id):
        from django.http import HttpResponse
        from users.models import Apprenant
        from users.access_control import user_can_access_apprenant
        from .models import Semestre, AnneeScolaire
        from .services.lmd import bulletin
        from .services.bulletin_pdf import rendre_bulletin_pdf

        apprenant = Apprenant.objects.filter(pk=apprenant_id).select_related("groupe__classe").first()
        if apprenant is None:
            return Response({"success": False, "message": "Apprenant introuvable."}, status=404)
        if not user_can_access_apprenant(request.user, apprenant):
            return Response({"success": False, "message": "Accès refusé."}, status=403)

        annee = AnneeScolaire.objects.filter(pk=annee_id).first()
        if annee is None:
            return Response({"success": False, "message": "Année introuvable."}, status=404)

        classe = getattr(getattr(apprenant, "groupe", None), "classe", None)
        semestres = (Semestre.objects.filter(classe=classe, annee_scolaire=annee).order_by("numero")
                     if classe else Semestre.objects.none())

        data = bulletin(apprenant, semestres, annee)
        pdf = rendre_bulletin_pdf(apprenant, annee, data)

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="bulletin_{apprenant_id}_{annee_id}.pdf"'
        return response
