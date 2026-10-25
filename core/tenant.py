# core/tenant.py
# =============================================================================
# MONO-ÉTABLISSEMENT
# Une seule institution de référence (institution 27 par défaut) ; le
# multi-tenant est désactivé. Les colonnes `institution` restent en base pour
# la compatibilité et l'historique, mais elles ne servent plus à choisir un
# périmètre.
# =============================================================================
from django.conf import settings


def default_institution_id():
    return getattr(settings, "DEFAULT_INSTITUTION_ID", None)


def default_institution():
    from academics.models import Institution

    iid = default_institution_id()
    if not iid:
        return None
    return Institution.objects.filter(pk=iid).first()


def default_annee_scolaire():
    from academics.models import AnneeScolaire

    iid = default_institution_id()
    if not iid:
        return None
    qs = AnneeScolaire.objects.filter(institution_id=iid)
    return (
        qs.filter(est_active=True).order_by("-date_debut").first()
        or qs.order_by("-date_debut").first()
    )


def default_annee_scolaire_id():
    annee = default_annee_scolaire()
    return getattr(annee, "id", None)
