# users/access_control.py
"""
Contrôle d'accès centralisé pour les ressources liées à un apprenant.

Empêche les IDOR : un utilisateur ne peut lire/modifier que les données des
apprenants qu'il est légitime de consulter :

- lui-même (Apprenant) ;
- ses enfants (Parent, via Apprenant.tuteur) ;
- ceux de son institution (Admin / Responsable / Formateur) ;
- tout le monde (superuser / SuperAdmin).

Ces helpers sont volontairement sans dépendance aux vues pour éviter les
imports circulaires.
"""

from users.models import Apprenant


def role_key(user) -> str | None:
    """Normalise le nom du rôle ('Responsable Académique' → 'responsableacademique')."""
    role = getattr(user, "role", None)
    name = getattr(role, "name", None)
    if not name:
        return None
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


def is_global_reader(user) -> bool:
    """True si l'utilisateur peut accéder aux données de tous les apprenants."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_superuser", False)) or role_key(user) == "superadmin"


def get_own_apprenant(user):
    """Retourne le profil Apprenant de l'utilisateur courant, sinon None."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    # MTI : la relation inverse 'apprenant' existe pour un utilisateur apprenant.
    apprenant = getattr(user, "apprenant", None)
    if apprenant is not None:
        return apprenant
    return Apprenant.objects.filter(pk=user.pk).first()


def _institution_ids_for(user) -> set:
    """Institutions rattachées à un utilisateur (FK, département, M2M)."""
    ids = set()
    if getattr(user, "institution_id", None):
        ids.add(user.institution_id)
    dep = getattr(user, "departement", None)
    if dep is not None and getattr(dep, "institution_id", None):
        ids.add(dep.institution_id)
    rel = getattr(user, "institutions", None)
    if rel is not None:
        try:
            ids.update(rel.values_list("pk", flat=True))
        except Exception:
            pass
    return ids


def _apprenants_in_institutions(institution_ids):
    """Apprenants liés à une institution (direct, inscription scolaire, cours)."""
    from django.db.models import Q
    return Apprenant.objects.filter(
        Q(institution_id__in=institution_ids)
        | Q(inscription_scolaire__institution_id__in=institution_ids)
        | Q(inscriptions_cours__institution_id__in=institution_ids)
    ).distinct()


def _apprenants_of_formateur(user):
    """Apprenants inscrits à un cours enseigné par ce formateur."""
    from courses.models import InscriptionCours
    return Apprenant.objects.filter(
        inscriptions_cours__cours__enseignant_id=user.pk
    ).distinct()


def accessible_apprenants(user):
    """
    QuerySet des Apprenant que `user` est autorisé à consulter.
    Retourne None si l'accès est global (superuser / superadmin).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Apprenant.objects.none()
    if is_global_reader(user):
        return None

    key = role_key(user)
    own = get_own_apprenant(user)

    if key == "parent":
        parent = getattr(user, "parent", None)
        if parent is None:
            return Apprenant.objects.none()
        return Apprenant.objects.filter(tuteur=parent)

    if key in ("admin", "responsable", "responsableacademique"):
        institution_ids = _institution_ids_for(user)
        if not institution_ids:
            return Apprenant.objects.none()
        return _apprenants_in_institutions(institution_ids)

    if key == "formateur":
        # ✅ PÉRIMÈTRE PÉDAGOGIQUE : un formateur n'accède qu'aux apprenants
        #    inscrits à SES cours (directement ou via ses groupes), et non à
        #    l'ensemble de l'établissement.
        return _apprenants_of_formateur(user)

    if own is not None:
        return Apprenant.objects.filter(pk=own.pk)

    return Apprenant.objects.none()


def user_can_access_apprenant(user, apprenant) -> bool:
    """True si `user` peut accéder aux données de `apprenant`."""
    if apprenant is None:
        return False
    if is_global_reader(user):
        return True
    allowed = accessible_apprenants(user)
    if allowed is None:
        return True
    return allowed.filter(pk=apprenant.pk).exists()


def resolve_apprenant(request, apprenant_id=None):
    """
    Retourne l'Apprenant demandé SI l'accès est autorisé, sinon None.
    - apprenant_id absent → l'apprenant de l'utilisateur courant.
    """
    user = getattr(request, "user", None)
    own = get_own_apprenant(user)

    if apprenant_id in (None, ""):
        return own

    if own is not None and str(own.pk) == str(apprenant_id):
        return own

    try:
        target = Apprenant.objects.filter(pk=apprenant_id).first()
    except (ValueError, TypeError):
        return None

    if target is not None and user_can_access_apprenant(user, target):
        return target
    return None
