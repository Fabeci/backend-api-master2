# academics/viewsets.py
# -*- coding: utf-8 -*-

from rest_framework import permissions, status
from rest_framework.response import Response

from academics.models import AnneeScolaire, DomaineEtude, Matiere, Specialite
from academics.serializers import (
    AnneeScolaireSerializer,
    DomaineEtudeSerializer,
    MatiereSerializer,
    SpecialiteSerializer,
)
from users.utils import BaseModelViewSet  # type: ignore
from academics.utils import filter_academics_queryset, get_role_name


# ============================================================================
# HELPERS
# ============================================================================

def _is_super_admin(user):
    return getattr(user, 'is_superuser', False)


def _check_write_permission(user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique')):
    """
    Retourne (True, None) si autorisé, ou (False, Response 403) sinon.
    SuperAdmin est bloqué sur les ressources internes.
    """
    if _is_super_admin(user):
        return False, Response(
            {
                "success": False,
                "status": 403,
                "message": "Les SuperAdmins ne gèrent pas les ressources internes des institutions.",
                "data": None,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    role = get_role_name(user)
    if role not in allowed_roles:
        return False, Response(
            {
                "success": False,
                "status": 403,
                "message": f"Action réservée aux rôles : {', '.join(allowed_roles)}.",
                "data": None,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return True, None


def _check_delete_permission(user, allowed_roles=('Admin',)):
    return _check_write_permission(user, allowed_roles=allowed_roles)


# ============================================================================
# DomaineEtude
# ============================================================================

class DomaineEtudeViewSet(BaseModelViewSet):
    """
    DomaineEtude :
    - SuperAdmin   : BLOQUÉ
    - Admin        : CRUD complet
    - Responsable  : CRUD complet
    - Formateur    : Lecture seule
    - Apprenant    : Lecture seule
    - Parent       : BLOQUÉ
    """
    queryset = DomaineEtude.objects.all()
    serializer_class = DomaineEtudeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "DomaineEtude", is_detail=is_detail)

    def create(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        if not ok:
            return err
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        if not ok:
            return err
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        if not ok:
            return err
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        ok, err = _check_delete_permission(request.user, allowed_roles=('Admin',))
        if not ok:
            return err
        return super().destroy(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        # SuperAdmin bloqué
        if _is_super_admin(request.user):
            return Response(
                {"success": False, "status": 403,
                 "message": "SuperAdmin non autorisé sur les ressources internes.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Parent bloqué
        if get_role_name(request.user) == 'Parent':
            return Response(
                {"success": False, "status": 403,
                 "message": "Accès non autorisé.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if _is_super_admin(request.user) or get_role_name(request.user) == 'Parent':
            return Response(
                {"success": False, "status": 403,
                 "message": "Accès non autorisé.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().retrieve(request, *args, **kwargs)


# ============================================================================
# Matiere
# ============================================================================

class MatiereViewSet(BaseModelViewSet):
    """
    Matiere :
    - SuperAdmin   : BLOQUÉ
    - Admin        : CRUD complet
    - Responsable  : CRUD complet
    - Formateur    : Lecture seule
    - Apprenant    : Lecture seule
    - Parent       : BLOQUÉ
    """
    queryset = Matiere.objects.all()
    serializer_class = MatiereSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "Matiere", is_detail=is_detail)

    def _check_access(self, request):
        if _is_super_admin(request.user) or get_role_name(request.user) == 'Parent':
            return Response(
                {"success": False, "status": 403,
                 "message": "Accès non autorisé.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def list(self, request, *args, **kwargs):
        err = self._check_access(request)
        if err:
            return err
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        err = self._check_access(request)
        if err:
            return err
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        if not ok:
            return err
        # Auto-assigner l'institution
        if not request.user.is_superuser and hasattr(request.user, 'institution_id'):
            request.data._mutable = True if hasattr(request.data, '_mutable') else None
            # On injecte via le serializer context plutôt
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        if not ok:
            return err
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        if not ok:
            return err
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        ok, err = _check_delete_permission(request.user, allowed_roles=('Admin',))
        if not ok:
            return err
        return super().destroy(request, *args, **kwargs)


# ============================================================================
# Specialite
# ============================================================================

class SpecialiteViewSet(BaseModelViewSet):
    """
    Specialite :
    - SuperAdmin   : BLOQUÉ
    - Admin        : CRUD complet
    - Responsable  : CRUD complet
    - Formateur    : Lecture seule
    - Apprenant    : Lecture seule
    - Parent       : BLOQUÉ
    """
    queryset = Specialite.objects.all()
    serializer_class = SpecialiteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")

        print("=== DEBUG SPECIALITE ===")
        print("user =", self.request.user)
        print("role =", get_role_name(self.request.user))
        print("institution_id =", getattr(self.request.user, "institution_id", None))
        print("count before =", qs.count())

        qs = filter_academics_queryset(qs, self.request, "Specialite", is_detail=is_detail)

        print("count after =", qs.count())
        print("========================")

        return qs

    def _block_if_super_or_parent(self, request):
        if _is_super_admin(request.user) or get_role_name(request.user) == 'Parent':
            return Response(
                {"success": False, "status": 403,
                 "message": "Accès non autorisé.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_or_parent(request)
        return err or super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_or_parent(request)
        return err or super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        return err if not ok else super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        return err if not ok else super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin', 'Responsable', 'ResponsableAcademique'))
        return err if not ok else super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        ok, err = _check_delete_permission(request.user, allowed_roles=('Admin',))
        return err if not ok else super().destroy(request, *args, **kwargs)


# ============================================================================
# AnneeScolaire
# ============================================================================

class AnneeScolaireViewSet(BaseModelViewSet):
    """
    AnneeScolaire :
    - SuperAdmin   : BLOQUÉ
    - Admin        : CRUD complet
    - Responsable  : Lecture seule
    - Formateur    : Lecture seule
    - Apprenant    : Lecture seule
    - Parent       : Lecture seule (années actives de ses enfants)
    """
    queryset = AnneeScolaire.objects.all()
    serializer_class = AnneeScolaireSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_detail = self.action in ("retrieve", "update", "partial_update", "destroy")
        return filter_academics_queryset(qs, self.request, "AnneeScolaire", is_detail=is_detail)

    def list(self, request, *args, **kwargs):
        if _is_super_admin(request.user):
            return Response(
                {"success": False, "status": 403,
                 "message": "SuperAdmin non autorisé sur les ressources internes.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if _is_super_admin(request.user):
            return Response(
                {"success": False, "status": 403,
                 "message": "SuperAdmin non autorisé sur les ressources internes.", "data": None},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        # Seul Admin peut créer
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin',))
        return err if not ok else super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin',))
        return err if not ok else super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        ok, err = _check_write_permission(request.user, allowed_roles=('Admin',))
        return err if not ok else super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        ok, err = _check_delete_permission(request.user, allowed_roles=('Admin',))
        return err if not ok else super().destroy(request, *args, **kwargs)