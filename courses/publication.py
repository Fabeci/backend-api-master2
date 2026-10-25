# courses/publication.py
# ============================================================================
# Publication progressive — règle de DISPONIBILITÉ (séparée de l'AUTORISATION).
#
#  - Autorisation  : RBAC + périmètre (qui a le droit de gérer/consulter).
#  - Disponibilité : l'élément est-il « publié » ET sa date atteinte, ET tous
#                    ses parents disponibles ?
#
# La disponibilité ne s'applique JAMAIS à l'encadrement (formateur/responsable/
# admin) : ils prévisualisent et gèrent leurs contenus, brouillons compris.
# ============================================================================
from django.db.models import Q
from django.utils import timezone


def date_atteinte(obj) -> bool:
    """La date programmée (si définie) est-elle dépassée ? (fuseau du projet)"""
    d = getattr(obj, "date_publication_programmee", None)
    if d is None:
        return True
    return timezone.now() >= d


def element_publie(obj) -> bool:
    """Brouillon / dépublié → non ; publié + date atteinte → oui ; programmé → selon la date."""
    etat = getattr(obj, "etat_publication", "publie")
    if etat not in ("publie", "programme"):
        return False          # brouillon, depublie, archive…
    if etat == "programme" and not date_atteinte(obj):
        return False          # programmé mais date non atteinte
    return date_atteinte(obj)


def module_disponible(m) -> bool:
    return bool(m) and element_publie(m)


def sequence_disponible(s) -> bool:
    if not s:
        return False
    return element_publie(s) and module_disponible(s.module)


def bloc_disponible(b) -> bool:
    if not b:
        return False
    # est_visible = visibilité manuelle (le formateur peut masquer un bloc)
    if not getattr(b, "est_visible", True):
        return False
    return element_publie(b) and sequence_disponible(b.sequence)


def session_disponible(s) -> bool:
    """Une séance n'est accessible à l'apprenant qu'À PARTIR de sa date de début
    et si elle n'est pas annulée."""
    if not s:
        return False
    if getattr(s, "statut", None) == "annulee":
        return False
    debut = getattr(s, "date_debut", None)
    if debut is None:
        return True
    return timezone.now() >= debut


def cours_commence(cours) -> bool:
    """Un cours est accessible aux apprenants à partir de sa date de début.

    - cours annulé → jamais accessible ;
    - pas de date de début → accessible ;
    - sinon, accessible dès `date_debut` (jour inclus).
    """
    if not cours:
        return False
    if getattr(cours, "statut", None) == "annule":
        return False
    debut = getattr(cours, "date_debut", None)
    if debut is None:
        return True
    return timezone.localdate() >= debut


def cours_disponible(cours) -> bool:
    return cours_commence(cours)


# ── Filtrage de queryset (usage : profils APPRENANT / PARENT uniquement) ─────

def _q_date(prefix: str = "") -> Q:
    return (Q(**{f"{prefix}date_publication_programmee__isnull": True})
            | Q(**{f"{prefix}date_publication_programmee__lte": timezone.now()}))


def filter_disponibles(queryset, model_name: str):
    """Restreint un queryset aux éléments DISPONIBLES (cascade parents incluse)."""
    if model_name == "Module":
        return queryset.filter(etat_publication="publie").filter(_q_date())
    if model_name == "Sequence":
        return (queryset.filter(etat_publication="publie", module__etat_publication="publie")
                .filter(_q_date()).filter(_q_date("module__")))
    if model_name == "BlocContenu":
        return (queryset.filter(etat_publication="publie", est_visible=True,
                                sequence__etat_publication="publie",
                                sequence__module__etat_publication="publie")
                .filter(_q_date()).filter(_q_date("sequence__")).filter(_q_date("sequence__module__")))
    if model_name == "Session":
        return (queryset.exclude(statut="annulee")
                .filter(Q(date_debut__isnull=True) | Q(date_debut__lte=timezone.now())))
    return queryset


# ── Cascade d'ÉTAT (action du formateur) ────────────────────────────────────
#  Une action sur le module (publier / programmer / brouillon / dépublier) se
#  répercute sur ses séquences puis sur leurs blocs. Les séquences/blocs peuvent
#  ensuite être ajustés individuellement (brouillon / programmé), mais on ne peut
#  pas PUBLIER une séquence si son module n'est pas publié, ni un bloc si sa
#  séquence (et son module) n'est pas publiée.

def appliquer_etat_module(module) -> None:
    """Aligne l'état des séquences (et blocs) sur celui du module."""
    from .models import BlocContenu, Sequence
    etat = module.etat_publication
    date = module.date_publication_programmee
    now = timezone.now()

    seqs = Sequence.objects.filter(module=module)
    blocs = BlocContenu.objects.filter(sequence__module=module)

    if etat == "publie":
        seqs.update(etat_publication="publie", date_publication_programmee=None,
                    date_publication_effective=now)
        blocs.update(etat_publication="publie", date_publication_programmee=None,
                     date_publication_effective=now)
    elif etat == "programme":
        seqs.update(etat_publication="programme", date_publication_programmee=date,
                    date_publication_effective=None)
        blocs.update(etat_publication="programme", date_publication_programmee=date,
                     date_publication_effective=None)
    else:  # brouillon / depublie
        seqs.update(etat_publication=etat, date_publication_programmee=None,
                    date_publication_effective=None)
        blocs.update(etat_publication=etat, date_publication_programmee=None,
                     date_publication_effective=None)


def appliquer_etat_sequence(sequence) -> None:
    """Aligne l'état des blocs d'une séquence sur celui de la séquence."""
    from .models import BlocContenu
    etat = sequence.etat_publication
    date = sequence.date_publication_programmee
    now = timezone.now()
    blocs = BlocContenu.objects.filter(sequence=sequence)

    if etat == "publie":
        blocs.update(etat_publication="publie", date_publication_programmee=None,
                     date_publication_effective=now)
    elif etat == "programme":
        blocs.update(etat_publication="programme", date_publication_programmee=date,
                     date_publication_effective=None)
    else:  # brouillon / depublie
        blocs.update(etat_publication=etat, date_publication_programmee=None,
                     date_publication_effective=None)


def peut_publier_sequence(seq) -> bool:
    """Une séquence ne peut être publiée que si son module est publié."""
    return bool(seq and seq.module_id and getattr(seq.module, "etat_publication", None) == "publie")


def peut_publier_bloc(bloc) -> bool:
    """Un bloc ne peut être publié que si sa séquence (et son module) est publiée."""
    if not bloc or not bloc.sequence_id:
        return False
    seq = bloc.sequence
    return (getattr(seq, "etat_publication", None) == "publie"
            and getattr(seq.module, "etat_publication", None) == "publie")
