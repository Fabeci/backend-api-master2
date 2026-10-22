# parametres/services.py
# ============================================================================
# Accès centralisé aux paramètres EFFECTIFS.
#
# Priorité de résolution :
#   1. surcharge établissement (ParametresInstitution, si non nulle)
#   2. paramètre global (ParametresPlateforme)
#   3. valeur par défaut passée en argument
#
# Aucune autre partie du code ne doit lire ParametresPlateforme /
# ParametresInstitution directement : passer par ces helpers garantit une
# source unique de vérité et la priorité globale/établissement.
# ============================================================================

from .models import ParametresPlateforme, ParametresInstitution


def get_global() -> ParametresPlateforme:
    """Paramètres globaux (singleton)."""
    return ParametresPlateforme.get_instance()


def get_institution(institution):
    """Surcharge de l'établissement, ou None."""
    if not institution:
        return None
    inst_id = getattr(institution, "id", institution)
    return ParametresInstitution.objects.filter(institution_id=inst_id).first()


def effective(field: str, institution=None, default=None):
    """Valeur effective d'un paramètre : institution > global > défaut."""
    if institution is not None:
        inst = get_institution(institution)
        if inst is not None:
            v = getattr(inst, field, None)
            if v is not None:
                return v
    g = get_global()
    v = getattr(g, field, None)
    return v if v is not None else default


# ── Raccourcis typés (les plus utilisés) ─────────────────────────────────────

def evaluation_note_passage_pct(institution=None, default: int = 60) -> int:
    return effective("evaluation_note_passage_pct", institution, default)


def evaluation_tentatives_max(institution=None, default: int = 3) -> int:
    return effective("evaluation_tentatives_max", institution, default)


def evaluation_afficher_correction(institution=None, default: bool = True) -> bool:
    return effective("evaluation_afficher_correction", institution, default)


def progression_seuil_completion_pct(institution=None, default: int = 80) -> int:
    return effective("progression_seuil_completion_pct", institution, default)


def progression_retention_jours(institution=None, default: int = 7) -> int:
    return int(effective("progression_retention_jours", institution, default) or default)


# ── Sécurité ─────────────────────────────────────────────────────────────────

def securite_mdp_longueur_min(institution=None, default: int = 8) -> int:
    return int(effective("securite_mdp_longueur_min", institution, default) or default)


def securite_mdp_complexite(institution=None, default: bool = True) -> bool:
    return bool(effective("securite_mdp_complexite", institution, default))


def securite_tentatives_login_max(institution=None, default: int = 5) -> int:
    return int(effective("securite_tentatives_login_max", institution, default) or default)


def securite_session_expiration_h(institution=None, default: int = 24) -> int:
    return int(effective("securite_session_expiration_h", institution, default) or default)


def langue_defaut(institution=None, default: str = 'fr') -> str:
    return effective("langue_defaut", institution, default) or default


def fuseau_horaire(institution=None, default: str = 'Africa/Ndjamena') -> str:
    return effective("fuseau_horaire", institution, default) or default


# ── Évaluations (compléments) ────────────────────────────────────────────────

def evaluation_duree_defaut_min(institution=None, default: int = 30) -> int:
    return int(effective("evaluation_duree_defaut_min", institution, default) or default)


def evaluation_shuffle_questions(institution=None, default: bool = False) -> bool:
    return bool(effective("evaluation_shuffle_questions", institution, default))


# ── Notifications (règles) ───────────────────────────────────────────────────

def _notif(cle: str, institution=None, default: bool = True) -> bool:
    return bool(effective(cle, institution, default))


def notif_email_actif(institution=None, default: bool = False) -> bool:
    return _notif("notif_email_actif", institution, default)


def notif_rappel_seance(institution=None, default: bool = True) -> bool:
    return _notif("notif_rappel_seance", institution, default)


def notif_absence(institution=None, default: bool = True) -> bool:
    return _notif("notif_absence", institution, default)


def notif_publication_evaluation(institution=None, default: bool = True) -> bool:
    return _notif("notif_publication_evaluation", institution, default)


def notif_correction_disponible(institution=None, default: bool = True) -> bool:
    return _notif("notif_correction_disponible", institution, default)


def notif_rappel_echeance(institution=None, default: bool = True) -> bool:
    return _notif("notif_rappel_echeance", institution, default)


def notif_rappel_seance_heures(institution=None, default: int = 24) -> int:
    return int(effective("notif_rappel_seance_heures", institution, default) or default)
