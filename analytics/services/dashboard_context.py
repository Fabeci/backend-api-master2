# analytics/services/dashboard_context.py
"""
DashboardContext — source de vérité sur l'identité, le rôle et le périmètre
de l'utilisateur connecté.  Toute requête SQL passe obligatoirement par ce
contexte ; aucune donnée ne peut être lue hors périmètre.
"""
from __future__ import annotations

from functools import cached_property
from typing import Optional

from django.utils import timezone


# Noms de rôles reconnus (valeurs en base dans UserRole.name)
ROLE_ADMIN        = 'Admin'
ROLE_RESPONSABLE  = 'Responsable'
ROLE_FORMATEUR    = 'Formateur'
ROLE_APPRENANT    = 'Apprenant'
ROLE_PARENT       = 'Parent'

ALL_ROLES = {
    ROLE_ADMIN, ROLE_RESPONSABLE,
    ROLE_FORMATEUR, ROLE_APPRENANT, ROLE_PARENT,
}


class PermissionDenied(Exception):
    """Levée quand le contexte ne donne pas accès à la ressource demandée."""


class DashboardContext:
    """
    Encapsule l'identité complète de l'utilisateur connecté.

    Utilisée par chaque DashboardService pour :
    - savoir quel périmètre appliquer
    - charger le profil métier (Formateur, Apprenant, …)
    - résoudre l'année scolaire active
    - construire les querysets filtrés de base

    Tous les attributs coûteux sont évalués paresseusement (lazy).
    """

    def __init__(self, user, filters: Optional[dict] = None):
        self.user    = user
        self.filters = filters or {}
        self.now     = timezone.now()
        self.today   = self.now.date()

        # Cache interne
        self._role_name: Optional[str] = None
        self._profile   = None
        self._annee     = None
        self._children  = None   # Parent seulement

    # ── Identité ──────────────────────────────────────────────────────────────

    @cached_property
    def role_name(self) -> Optional[str]:
        if self.user.is_superuser:
            return ROLE_ADMIN
        raw = getattr(getattr(self.user, 'role', None), 'name', None)
        if not raw:
            return None
        # ✅ Canonicalisation : « ResponsableAcademique » → « Responsable », etc.
        # (sans quoi le router de dashboard renvoie 403 pour ce rôle).
        key = str(raw).lower().replace(' ', '').replace('-', '').replace('_', '')
        return {
            'superadmin':            ROLE_ADMIN,
            'admin':                 ROLE_ADMIN,
            'responsable':           ROLE_RESPONSABLE,
            'responsableacademique': ROLE_RESPONSABLE,
            'formateur':             ROLE_FORMATEUR,
            'apprenant':             ROLE_APPRENANT,
            'parent':                ROLE_PARENT,
        }.get(key, raw)

    @cached_property
    def institution(self):
        return getattr(self.user, 'institution', None)

    @cached_property
    def annee(self):
        """
        Résout l'année scolaire dans cet ordre de priorité :
        1. Filtre explicite de la requête (annee_scolaire_id)
        2. annee_scolaire_active sur l'utilisateur
        3. Année active de l'institution
        """
        from academics.models import AnneeScolaire

        annee_id = self.filters.get('annee_scolaire_id')
        if annee_id:
            try:
                return AnneeScolaire.objects.get(pk=annee_id)
            except AnneeScolaire.DoesNotExist:
                pass

        annee = getattr(self.user, 'annee_scolaire_active', None)
        if annee:
            return annee

        if self.institution:
            return (
                AnneeScolaire.objects
                .filter(institution=self.institution, est_active=True)
                .first()
            )
        return None

    @cached_property
    def profile(self):
        """
        Charge le profil métier correspondant au rôle (Formateur, Apprenant…).
        Les vues ne doivent jamais faire Formateur.objects.get(pk=…) elles-mêmes.
        """
        role = self.role_name
        pk   = self.user.pk
        try:
            if role == ROLE_FORMATEUR:
                from users.models import Formateur
                return Formateur.objects.get(pk=pk)
            if role == ROLE_RESPONSABLE:
                from users.models import ResponsableAcademique
                return ResponsableAcademique.objects.get(pk=pk)
            if role == ROLE_APPRENANT:
                from users.models import Apprenant
                return Apprenant.objects.get(pk=pk)
            if role == ROLE_PARENT:
                from users.models import Parent
                return Parent.objects.get(pk=pk)
        except Exception:
            pass
        return self.user

    @cached_property
    def children(self):
        """Apprenants liés à ce Parent (vide pour les autres rôles)."""
        if self.role_name != ROLE_PARENT:
            return []
        from users.models import Apprenant
        return list(Apprenant.objects.filter(tuteur=self.profile).select_related('institution'))

    # ── Vérifications ─────────────────────────────────────────────────────────

    def is_super(self) -> bool:
        return self.user.is_superuser

    def has_role(self, *roles: str) -> bool:
        return self.role_name in roles

    def require_role(self, *roles: str) -> None:
        """Lève PermissionDenied si le rôle n'est pas dans la liste."""
        if not self.is_super() and not self.has_role(*roles):
            raise PermissionDenied(
                f"Rôle requis : {', '.join(roles)}. Rôle actuel : {self.role_name}"
            )

    # ── Querysets de base (périmètre automatique) ──────────────────────────────

    def cours_qs(self, model=None):
        """
        Retourne un queryset de Cours scoped au périmètre de l'utilisateur.
        Remplace les duplications de filtre dans chaque service.
        """
        if model is None:
            from courses.models import Cours as model
        qs = model.objects.all()

        role = self.role_name
        if role in (ROLE_ADMIN, ROLE_RESPONSABLE):
            return qs.filter(institution=self.institution)
        if role == ROLE_FORMATEUR:
            qs = qs.filter(enseignant=self.profile)
            if self.annee:
                qs = qs.filter(annee_scolaire=self.annee)
            return qs
        if role == ROLE_APPRENANT:
            from courses.models import InscriptionCours
            ids = InscriptionCours.objects.filter(apprenant=self.profile).values_list('cours_id', flat=True)
            return qs.filter(id__in=ids)
        if role == ROLE_PARENT:
            from courses.models import InscriptionCours
            enfant_ids = [e.id for e in self.children]
            ids = InscriptionCours.objects.filter(apprenant__in=enfant_ids).values_list('cours_id', flat=True)
            return qs.filter(id__in=ids)
        return qs.none()

    def annees_disponibles(self) -> list:
        """Années scolaires accessibles à l'utilisateur courant."""
        from academics.models import AnneeScolaire
        inst = self.institution
        if not inst:
            return []
        return list(
            AnneeScolaire.objects
            .filter(institution=inst)
            .order_by('-date_debut', '-id')
            .values('id', 'annee_format_classique', 'est_active')
        )

    def annee_payload(self) -> dict:
        """Bloc JSON standardisé pour l'année scolaire retourné dans chaque dashboard."""
        a = self.annee
        return {
            'id':         a.id if a else None,
            'label':      getattr(a, 'annee_format_classique', None) or 'Toutes années',
            'est_active': getattr(a, 'est_active', False),
        }

    def __repr__(self) -> str:
        return (
            f"DashboardContext(user={self.user.pk}, role={self.role_name}, "
            f"institution={getattr(self.institution, 'nom', None)}, "
            f"annee={getattr(self.annee, 'annee_format_classique', None)})"
        )
