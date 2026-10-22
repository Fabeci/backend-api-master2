# analytics/services/diagnosis_engine.py
# ============================================================================
# MOTEUR DE DIAGNOSTIC (Phase 8)
#
#   Signaux  →  Agrégation  →  Diagnostic
#
# - Un seul diagnostic par CIBLE (anti-bruit) : plusieurs signaux sur la même
#   cible produisent UN diagnostic.
# - Explicable : type, sévérité, priorité P1-P4, confiance, raison, preuves.
# ============================================================================
import logging
from collections import Counter

from django.utils import timezone

logger = logging.getLogger(__name__)

TARGET_KEYS = ('cours', 'module', 'sequence', 'bloc', 'competence')

SIGNAL_TO_DIAGNOSIS = {
    'lacune_critique':       'MASTERY_GAP',
    'lacune_moderee':        'MASTERY_GAP',
    'maitrise_fragile':      'MASTERY_GAP',
    'remediation_insuffisante': 'DIFFICULTY_PERSISTENT',
    'competence_fragile':    'MASTERY_GAP',
    'progression_trop_lente':'MASTERY_GAP',
    'difficulte_persistante':'DIFFICULTY_PERSISTENT',
    'erreurs_repetitives':   'DIFFICULTY_PERSISTENT',
    'faible_performance':    'PERFORMANCE_DROP',
    'regression':            'PERFORMANCE_DROP',
    'echec_repete':          'PERFORMANCE_DROP',
    'inactivite_prolongee':  'DISENGAGEMENT',
    'baisse_engagement':     'DISENGAGEMENT',
    'aucune_activite':       'DISENGAGEMENT',
    'progression_stagnante': 'STAGNATION',
    'sequence_abandonnee':   'ABANDONMENT',
}

SEVERITY_RANK = {'faible': 0, 'moderee': 1, 'critique': 2}
TYPE_LABEL = {
    'MASTERY_GAP': 'lacune de maîtrise',
    'DIFFICULTY_PERSISTENT': 'difficulté persistante',
    'PERFORMANCE_DROP': 'baisse de performance',
    'DISENGAGEMENT': 'désengagement',
    'STAGNATION': 'stagnation',
    'ABANDONMENT': 'abandon',
}
SIGNAL_LABEL = {
    'lacune_critique': 'lacune critique',
    'lacune_moderee': 'lacune modérée',
    'maitrise_fragile': 'maîtrise fragile',
    'remediation_insuffisante': 'remédiation insuffisante',
    'inactivite_prolongee': 'inactivité prolongée',
    'baisse_engagement': 'baisse d’engagement',
    'aucune_activite': 'absence d’activité',
    'progression_stagnante': 'progression stagnante',
    'progression_trop_lente': 'progression trop lente',
    'erreurs_repetitives': 'erreurs répétitives',
    'competence_fragile': 'compétence fragile',
    'regression': 'régression',
    'echec_repete': 'échec répété',
    'difficulte_persistante': 'difficulté persistante',
    'sequence_abandonnee': 'séquence abandonnée',
    'faible_performance': 'faible performance',
}


def _target_key(sig: dict) -> tuple:
    return tuple((k, (sig.get(k).pk if sig.get(k) is not None else None)) for k in TARGET_KEYS)


def _priority(severity: str, nb: int) -> int:
    if severity == 'critique':
        return 1                       # P1
    if severity == 'moderee' and nb >= 2:
        return 2                       # P2
    if severity == 'moderee':
        return 3                       # P3
    return 4                           # P4


def _reason(diag_type: str, sigs: list) -> str:
    parts = [f"{SIGNAL_LABEL.get(s['signal_type'], s['signal_type'])} ({s.get('reference') or ''} {s.get('valeur')})".strip()
             for s in sigs]
    return f"{TYPE_LABEL.get(diag_type, diag_type).capitalize()} — " + " ; ".join(parts)


def compute_diagnoses(apprenant, signals=None) -> list:
    from .signal_engine import compute_signals

    if signals is None:
        signals = compute_signals(apprenant)
    groups = {}
    for s in signals:
        groups.setdefault(_target_key(s), []).append(s)

    out = []
    for _key, sigs in groups.items():
        severity = max(sigs, key=lambda x: SEVERITY_RANK.get(x['severity'], 0))['severity']
        subtypes = [SIGNAL_TO_DIAGNOSIS.get(s['signal_type'], 'DIFFICULTY_PERSISTENT') for s in sigs]
        dom_type = Counter(subtypes).most_common(1)[0][0]
        nb = len(sigs)
        confidence = round(min(0.95, 0.4 + 0.15 * nb + (0.2 if severity == 'critique' else 0)), 2)

        target = {k: sigs[0].get(k) for k in TARGET_KEYS}
        out.append({
            'diagnosis_type': dom_type,
            'severity': severity,
            'priority': _priority(severity, nb),
            'confidence': confidence,
            'signal_types': [s['signal_type'] for s in sigs],
            'evidence': [{'signal': s['signal_type'], 'severite': s['severity'],
                          'valeur': s.get('valeur'), 'reference': s.get('reference'),
                          'preuves': s.get('preuves', [])} for s in sigs],
            'reason': _reason(dom_type, sigs),
            **target,
        })
    return out


def _upsert(apprenant, d: dict):
    from analytics.models import LearningDiagnosis

    target = {k: d.get(k) for k in TARGET_KEYS}
    existing = LearningDiagnosis.objects.filter(
        apprenant=apprenant, statut='actif', **target,
    ).first()

    if existing:
        existing.diagnosis_type = d['diagnosis_type']
        existing.severity = d['severity']
        existing.priority = d['priority']
        existing.confidence = d['confidence']
        existing.signal_types = d['signal_types']
        existing.evidence = d['evidence']
        existing.reason = d['reason']
        existing.save(update_fields=[
            'diagnosis_type', 'severity', 'priority', 'confidence',
            'signal_types', 'evidence', 'reason', 'updated_at',
        ])
        return existing

    return LearningDiagnosis.objects.create(
        apprenant=apprenant,
        diagnosis_type=d['diagnosis_type'], severity=d['severity'],
        priority=d['priority'], confidence=d['confidence'],
        signal_types=d['signal_types'], evidence=d['evidence'], reason=d['reason'],
        **target,
    )


def refresh_diagnoses(apprenant, diagnoses=None) -> list:
    """Recalcule les diagnostics : upsert + résolution des obsolètes."""
    from analytics.models import LearningDiagnosis

    if diagnoses is None:
        diagnoses = compute_diagnoses(apprenant)
    keep = []
    for d in diagnoses:
        obj = _upsert(apprenant, d)
        keep.append(obj.pk)

    LearningDiagnosis.objects.filter(apprenant=apprenant, statut='actif') \
        .exclude(pk__in=keep).update(statut='resolu', resolved_at=timezone.now())

    return list(LearningDiagnosis.objects.filter(pk__in=keep).select_related('competence'))
