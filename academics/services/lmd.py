# academics/services/lmd.py
# ============================================================================
# MOTEUR LMD — Sup'Info
#
# Règles (validées) :
#   - Moyenne EC   = Σ(note20 × coef évaluation) / Σ(coef)
#   - Moyenne UE   = Σ(moyenne EC × coef EC) / Σ(coef EC)
#   - UE validée   ⇔ moyenne UE ≥ seuil (10/20)  → tous ses crédits acquis
#   - Semestre OK  ⇔ TOUTES les UE validées (option stricte)
#   - Année OK     ⇔ les 2 semestres validés
#   - Rattrapage   : par EC, MEILLEURE note entre session normale et rattrapage
#   - Assiduité    : aucune influence sur les notes
#   - Mention      : uniquement sur la moyenne ANNUELLE
# ============================================================================
from __future__ import annotations

from courses.models import Cours
from evaluations.models import Evaluation, PassageEvaluation

SEUIL_DEFAUT = 10.0


def _arrondi(v):
    return round(float(v), 2) if v is not None else None


def _cours_du_candidat(apprenant, matiere=None, annee_scolaire=None):
    qs = Cours.objects.filter(inscriptions__apprenant=apprenant)
    if matiere is not None:
        qs = qs.filter(matiere=matiere)
    if annee_scolaire is not None:
        qs = qs.filter(annee_scolaire=annee_scolaire)
    return qs.distinct()


def _note_sur_20(passage: PassageEvaluation) -> float | None:
    if passage.note is None:
        return None
    bareme = float(getattr(passage.evaluation, "bareme", 20) or 20)
    return float(passage.note) / bareme * 20.0 if bareme else float(passage.note)


def meilleure_note(apprenant, evaluation) -> float | None:
    """Meilleure note /20 entre session normale et rattrapage."""
    passages = PassageEvaluation.objects.filter(
        apprenant=apprenant, evaluation=evaluation,
        statut__in=["soumis", "corrige"], note__isnull=False,
    ).select_related("evaluation")
    notes = [n for n in (_note_sur_20(p) for p in passages) if n is not None]
    return _arrondi(max(notes)) if notes else None


def moyenne_ec(apprenant, matiere, annee_scolaire=None) -> dict:
    """Moyenne de l'EC (matière) + détail des évaluations."""
    cours = _cours_du_candidat(apprenant, matiere, annee_scolaire)
    evaluations = Evaluation.objects.filter(cours__in=cours, est_publiee=True)

    total, coef_total, detail = 0.0, 0.0, []
    for ev in evaluations:
        note = meilleure_note(apprenant, ev)
        if note is None:
            continue
        coef = float(ev.coefficient or 1)
        total += note * coef
        coef_total += coef
        detail.append({
            "evaluation": ev.id,
            "titre": ev.titre,
            "categorie": ev.categorie,
            "coefficient": coef,
            "note": note,
            "bareme": ev.bareme,
        })

    moyenne = _arrondi(total / coef_total) if coef_total else None
    return {
        "matiere": matiere.id,
        "code": getattr(matiere, "nom", None),
        "credits": getattr(matiere, "credits", 0) or 0,
        "coefficient": float(getattr(matiere, "coefficient", 1) or 1),
        "moyenne": moyenne,
        "detail": detail,
    }


def moyenne_ue(apprenant, ue, annee_scolaire=None) -> dict:
    ecs = list(ue.matieres.filter(est_actif=True))
    details, total, coef_total = [], 0.0, 0.0

    for ec in ecs:
        r = moyenne_ec(apprenant, ec, annee_scolaire)
        details.append(r)
        if r["moyenne"] is not None:
            c = float(ec.coefficient or 1)
            total += r["moyenne"] * c
            coef_total += c

    moyenne = _arrondi(total / coef_total) if coef_total else None
    seuil = float(ue.seuil_validation or SEUIL_DEFAUT)
    valide = moyenne is not None and moyenne >= seuil

    return {
        "ue": ue.id,
        "code": ue.code,
        "libelle": ue.libelle,
        "credits": ue.credits,
        "coefficient": float(ue.coefficient or 1),
        "seuil": seuil,
        "moyenne": moyenne,
        "valide": valide,
        "credits_acquis": ue.credits if valide else 0,
        "ecs": details,
    }


def moyenne_semestre(apprenant, semestre, annee_scolaire=None) -> dict:
    ues = list(semestre.ues.filter(est_active=True))
    details = [moyenne_ue(apprenant, ue, annee_scolaire) for ue in ues]

    # Option A (stricte) : toutes les UE doivent être validées.
    valide = bool(details) and all(u["valide"] for u in details)
    credits = sum(u["credits_acquis"] for u in details)

    total, coef_total = 0.0, 0.0
    for u, d in zip(ues, details):
        if d["moyenne"] is not None:
            c = float(u.coefficient or 1)
            total += d["moyenne"] * c
            coef_total += c
    moyenne = _arrondi(total / coef_total) if coef_total else None

    return {
        "semestre": semestre.id,
        "numero": semestre.numero,
        "libelle": str(semestre),
        "moyenne": moyenne,
        "valide": valide,
        "credits_acquis": credits,
        "credits_requis": 30,
        "ues": details,
    }


def mention(moyenne) -> str | None:
    if moyenne is None:
        return None
    if moyenne >= 18: return "Excellent"
    if moyenne >= 16: return "Très bien"
    if moyenne >= 14: return "Bien"
    if moyenne >= 12: return "Assez bien"
    if moyenne >= 10: return "Passable"
    return "Ajourné"


def bulletin(apprenant, semestres, annee_scolaire=None) -> dict:
    """Bulletin complet : semestres → UE → EC, décisions, crédits, mention."""
    semestres = list(semestres)
    details = [moyenne_semestre(apprenant, s, annee_scolaire) for s in semestres]

    valide_annee = bool(details) and all(s["valide"] for s in details)
    credits = sum(s["credits_acquis"] for s in details)

    moyennes = [s["moyenne"] for s in details if s["moyenne"] is not None]
    moyenne_annee = _arrondi(sum(moyennes) / len(moyennes)) if moyennes else None

    return {
        "apprenant": apprenant.id,
        "semestres": details,
        "moyenne_annee": moyenne_annee,
        "valide_annee": valide_annee,
        "credits_acquis": credits,
        "credits_annee": 60,
        "mention": mention(moyenne_annee) if valide_annee else "Ajourné",
    }
