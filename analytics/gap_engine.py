# analytics/gap_engine.py
# ============================================================================
# MOTEUR DE DÉTECTION DES LACUNES
# Se déclenche après chaque recalcul de SkillMasteryScore
# ============================================================================
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

SMS_GAP_THRESHOLD   = 50.0  # score < 50 → lacune potentielle
QUIZ_WEAK_THRESHOLD = 50.0
COMPLETION_MIN      = 60.0


def detect_and_update_gap(apprenant, sequence):
    """
    Analyse le mastery de (apprenant, sequence) et crée/met à jour/résout
    un KnowledgeGap en conséquence.
    Retourne le KnowledgeGap actif, ou None si aucune lacune.
    """
    from .models import SkillMasteryScore, KnowledgeGap

    mastery = SkillMasteryScore.objects.filter(
        apprenant=apprenant, sequence=sequence
    ).first()
    if not mastery:
        return None

    # Score suffisant → résoudre toute lacune existante
    if mastery.score >= SMS_GAP_THRESHOLD:
        KnowledgeGap.objects.filter(
            apprenant=apprenant,
            sequence=sequence,
            statut__in=['detectee', 'en_cours'],
        ).update(statut='resolue', resolved_at=timezone.now())
        return None

    # Construire les preuves
    evidence      = []
    severity_pts  = 0

    if mastery.score_quiz < QUIZ_WEAK_THRESHOLD:
        evidence.append({'type': 'quiz_faible', 'score': round(mastery.score_quiz, 1)})
        severity_pts += (QUIZ_WEAK_THRESHOLD - mastery.score_quiz) * 0.8

    if mastery.score_completion < COMPLETION_MIN:
        evidence.append({'type': 'completion_faible', 'pct': round(mastery.score_completion, 1)})
        severity_pts += 20

    if mastery.score_temps < 30:
        evidence.append({'type': 'temps_insuffisant', 'score': round(mastery.score_temps, 1)})
        severity_pts += 15

    if not evidence:
        return None

    severity = (
        'critique' if severity_pts >= 60 else
        'moderee'  if severity_pts >= 30 else
        'faible'
    )
    description = _build_description(evidence, severity, sequence)

    # Chercher une lacune active existante
    existing = KnowledgeGap.objects.filter(
        apprenant=apprenant,
        sequence=sequence,
        statut__in=['detectee', 'en_cours'],
    ).first()

    if existing:
        existing.severity    = severity
        existing.evidence    = evidence
        existing.description = description
        existing.save(update_fields=['severity', 'evidence', 'description'])
        return existing

    gap = KnowledgeGap.objects.create(
        apprenant=apprenant,
        sequence=sequence,
        severity=severity,
        evidence=evidence,
        description=description,
    )
    logger.info('[gap] Nouvelle lacune: appr=%s seq=%s sev=%s', apprenant.pk, sequence.pk, severity)
    return gap


def _build_description(evidence, severity, sequence) -> str:
    labels = {
        'quiz_faible':       lambda e: f"Score quiz: {e['score']}%",
        'completion_faible': lambda e: f"Complétion: {e['pct']}%",
        'temps_insuffisant': lambda _: "Temps d'étude insuffisant.",
    }
    parts = [f'Lacune {severity} sur « {sequence.titre} ».']
    for e in evidence:
        fn = labels.get(e['type'])
        if fn:
            parts.append(fn(e))
    return ' '.join(parts)
