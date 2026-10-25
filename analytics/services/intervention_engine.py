# analytics/services/intervention_engine.py
# ============================================================================
# MOTEUR D'INTERVENTIONS (Phase 10)
#
#   Diagnostic  →  Intervention (type choisi selon nature/gravité)
#
# - Upsert d'une intervention active par (apprenant, diagnostic).
# - Projection en `RecommandationPedagogique` pour les interventions destinées
#   à l'apprenant (le frontend conserve « Voir le contenu / Passer le quiz »).
# - Les diagnostics critiques (P1) génèrent en plus une alerte formateur.
# ============================================================================
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

DIAG_TO_INTERVENTION = {
    'MASTERY_GAP':           'AI_CONTENT',
    'DIFFICULTY_PERSISTENT': 'RETAKE_QUIZ',
    'PERFORMANCE_DROP':      'PRACTICE',
    'STAGNATION':            'REVIEW_SEQUENCE',
    'ABANDONMENT':           'REVIEW_SEQUENCE',
    'DISENGAGEMENT':         'TRAINER_ALERT',
}

# Projection vers le type de recommandation frontend
INTERVENTION_TO_RECO = {
    'AI_CONTENT':             'changement_approche',
    'AI_QUIZ':                'quiz_supplementaire',
    'REVIEW_SEQUENCE':        'bloc_revoir',
    'REVIEW_BLOCK':           'bloc_revoir',
    'RETAKE_QUIZ':            'quiz_supplementaire',
    'PRACTICE':               'changement_approche',
    'RESOURCE_RECOMMENDATION':'contenu_alternatif',
    'TRAINER_ALERT':          None,   # non affichée à l'apprenant
}

TARGET_KEYS = ('cours', 'module', 'sequence', 'bloc', 'competence')

_DIAG_MESSAGE = {
    'MASTERY_GAP':           "Une notion semble fragile. Une explication adaptée peut vous aider.",
    'DIFFICULTY_PERSISTENT': "Plusieurs tentatives montrent une difficulté persistante. Refaisons le point par un quiz ciblé.",
    'PERFORMANCE_DROP':      "Vos résultats récents baissent. Des exercices de pratique sont proposés.",
    'STAGNATION':            "Votre progression ralentit. Revoir cette séquence peut vous débloquer.",
    'ABANDONMENT':           "Vous avez mis cette séquence de côté. Reprenons-la ensemble.",
    'DISENGAGEMENT':         "Votre activité a chuté récemment. Un accompagnement peut être utile.",
}


def _target(diag) -> dict:
    return {k: getattr(diag, k) for k in TARGET_KEYS}


def _active_intervention(apprenant, diagnosis, itype):
    from analytics.models import LearningIntervention
    return LearningIntervention.objects.filter(
        apprenant=apprenant, diagnosis=diagnosis, intervention_type=itype,
        status__in=['proposee', 'acceptee', 'en_cours'],
    ).first()


def refresh_interventions(apprenant, diagnoses=None) -> list:
    """Crée/met à jour les interventions des diagnostics actifs (+ projections)."""
    from .diagnosis_engine import refresh_diagnoses
    from analytics.models import (
        LearningDiagnosis, LearningIntervention, RecommandationPedagogique,
    )

    if diagnoses is None:
        refresh_diagnoses(apprenant)
        active = list(LearningDiagnosis.objects.filter(apprenant=apprenant, statut='actif'))
    else:
        active = [d for d in diagnoses if getattr(d, 'statut', 'actif') == 'actif']

    now = timezone.now()
    out = []

    for diag in active:
        itype = DIAG_TO_INTERVENTION.get(diag.diagnosis_type, 'PRACTICE')
        target = _target(diag)

        iv = _active_intervention(apprenant, diag, itype)
        if iv is None:
            iv = LearningIntervention.objects.create(
                apprenant=apprenant, diagnosis=diag, intervention_type=itype,
                priority=diag.priority, reason=diag.reason,
                message=_DIAG_MESSAGE.get(diag.diagnosis_type, diag.reason),
                expires_at=now + timedelta(days=7),
                **target,
            )

        # Alerte formateur pour les diagnostics critiques
        if diag.priority == 1 and itype != 'TRAINER_ALERT':
            if _active_intervention(apprenant, diag, 'TRAINER_ALERT') is None:
                LearningIntervention.objects.create(
                    apprenant=apprenant, diagnosis=diag, intervention_type='TRAINER_ALERT',
                    priority=1, reason=diag.reason,
                    message=f"Intervention formateur requise : {diag.get_diagnosis_type_display()}.",
                    expires_at=now + timedelta(days=7), **target,
                )

        # Projection frontend (uniquement si cible séquence, pour éviter le bruit)
        reco_type = INTERVENTION_TO_RECO.get(itype)
        if reco_type and diag.sequence_id:
            reco = RecommandationPedagogique.objects.filter(
                apprenant=apprenant, sequence_cible_id=diag.sequence_id,
                est_suivie=False, est_ignoree=False,
            ).first()
            if reco:
                if reco.intervention_id is None:
                    reco.intervention = iv
                    reco.save(update_fields=['intervention'])
            else:
                # ✅ Toujours renseigner le cours (sinon masqué par le filtre cours du panneau)
                crs = diag.cours or (
                    getattr(getattr(diag.sequence, 'module', None), 'cours', None)
                    if diag.sequence_id else None
                )
                RecommandationPedagogique.objects.create(
                    apprenant=apprenant, cours=crs, bloc_cible=diag.bloc,
                    sequence_cible=diag.sequence, intervention=iv,
                    type_recommandation=reco_type,
                    message=iv.message, priorite=min(3, diag.priority),
                )

        out.append(iv)

    return out
