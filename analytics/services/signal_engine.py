# analytics/services/signal_engine.py
# ============================================================================
# MOTEUR DE SIGNAUX (Phase 7)
#
# Dérive des signaux pédagogiques à partir des états calculés (engagement,
# performance, progression, compétences) et de l'existant (lacunes).
# - Upsert des signaux ACTIFS (pas de doublon par type+cible)
# - Résolution automatique des signaux obsolètes (anti-bruit)
#
# Les AI_TRIGGERS existants (temps_long, etc.) restent inchangés.
# ============================================================================
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Clé de cible stable
_TARGET_KEYS = ('cours', 'module', 'sequence', 'bloc', 'competence')


def _target_kwargs(sig: dict) -> dict:
    return {k: sig.get(k) for k in _TARGET_KEYS}


def emit_signal(apprenant, signal_type, severity, *, valeur=0.0, reference='',
                preuves=None, cours=None, module=None, sequence=None, bloc=None, competence=None):
    """Crée ou met à jour le signal ACTIF correspondant (type + cible)."""
    from analytics.models import LearningSignal

    preuves = preuves or []
    existing = LearningSignal.objects.filter(
        apprenant=apprenant, signal_type=signal_type, statut='actif',
        cours=cours, module=module, sequence=sequence, bloc=bloc, competence=competence,
    ).first()

    if existing:
        existing.severity  = severity
        existing.valeur    = valeur
        existing.reference = reference
        existing.preuves   = preuves
        existing.save(update_fields=['severity', 'valeur', 'reference', 'preuves', 'updated_at'])
        return existing

    return LearningSignal.objects.create(
        apprenant=apprenant, signal_type=signal_type, severity=severity,
        valeur=valeur, reference=reference, preuves=preuves,
        cours=cours, module=module, sequence=sequence, bloc=bloc, competence=competence,
    )


def compute_signals(apprenant, eng=None, perf=None, st=None) -> list:
    """Calcule la liste des signaux attendus (états précalculés optionnels)."""
    from .engagement_engine import compute_engagement
    from .performance_engine import compute_performance
    from .progress_engine import compute_learning_state

    from analytics.models import (
        CompetenceMastery, SequenceAnalyticsSummary, KnowledgeGap,
    )

    now = timezone.now()
    out = []

    if eng is None:
        eng = compute_engagement(apprenant)
    if perf is None:
        perf = compute_performance(apprenant)
    if st is None:
        st = compute_learning_state(apprenant)
    from analytics.models import LearnerLearningState
    _ls = LearnerLearningState.objects.filter(apprenant=apprenant).first()
    trend = _ls.trend if _ls else 'stable'

    # ── Engagement ─────────────────────────────────────────────────────────
    if eng['last_activity']:
        jours = (now - eng['last_activity']).days
        if jours >= 7:
            out.append({'signal_type': 'inactivite_prolongee',
                        'severity': 'critique' if jours >= 14 else 'moderee',
                        'valeur': jours, 'reference': '≥ 7 jours',
                        'preuves': [{'derniere_activite': eng['last_activity'].isoformat(), 'jours': jours}]})
    elif eng['sessions_30d'] == 0:
        out.append({'signal_type': 'aucune_activite', 'severity': 'moderee',
                    'valeur': 0, 'reference': 'aucune session (30j)'})

    if eng['tendance'] == 'baisse':
        out.append({'signal_type': 'baisse_engagement', 'severity': 'moderee',
                    'valeur': round((eng['weekly_time_sec'] - eng['prev_weekly_sec']) / 60, 1),
                    'reference': 'temps semaine vs précédente',
                    'preuves': [{'semaine_sec': eng['weekly_time_sec'], 'precedente_sec': eng['prev_weekly_sec']}]})

    # ── Performance ────────────────────────────────────────────────────────
    if perf['attempts_total'] and perf['avg_score'] < 50:
        out.append({'signal_type': 'faible_performance', 'severity': 'moderee',
                    'valeur': perf['avg_score'], 'reference': 'moyenne < 50%',
                    'preuves': [{'avg_score': perf['avg_score'], 'attempts': perf['attempts_total']}]})

    if perf['repeated_errors'] >= 2:
        out.append({'signal_type': 'erreurs_repetitives', 'severity': 'moderee',
                    'valeur': perf['repeated_errors'], 'reference': '≥ 2 questions ratées ≥ 2 fois'})

    if perf['status'] == 'difficulte_repetee':
        out.append({'signal_type': 'difficulte_persistante', 'severity': 'critique',
                    'valeur': perf['avg_score'], 'reference': 'échecs répétés + erreurs répétitives',
                    'preuves': [{'status': perf['status'], 'error_rate': perf['error_rate']}]})
        out.append({'signal_type': 'echec_repete', 'severity': 'moderee',
                    'valeur': perf['avg_score'], 'reference': 'plusieurs échecs'})

    if perf['status'] == 'regression' or (perf['trend'] == 'baisse' and perf['attempts_total'] >= 2):
        out.append({'signal_type': 'regression', 'severity': 'moderee',
                    'valeur': perf['recent_avg'] if perf['recent_avg'] is not None else 0,
                    'reference': 'récent < précédent',
                    'preuves': [{'recent': perf['recent_avg'], 'precedent': perf['previous_avg']}]})

    # ── Progression / maîtrise ─────────────────────────────────────────────
    if trend == 'stable' and st['sequences_blocked'] >= 3:
        out.append({'signal_type': 'progression_stagnante', 'severity': 'moderee',
                    'valeur': st['sequences_blocked'], 'reference': '≥ 3 séquences bloquées'})

    if 0 < st['avg_mastery'] < 30 and st['global_progress_pct'] >= 20:
        out.append({'signal_type': 'progression_trop_lente', 'severity': 'moderee',
                    'valeur': st['avg_mastery'], 'reference': 'maîtrise < 30% avec progression ≥ 20%'})

    # ── Compétences fragiles (preuve suffisante) ───────────────────────────
    for m in CompetenceMastery.objects.filter(
        apprenant=apprenant, niveau__in=['non_acquis', 'fragile'], confidence__gte=0.3,
    ).select_related('competence')[:10]:
        out.append({'signal_type': 'competence_fragile',
                    'severity': 'moderee' if m.niveau == 'fragile' else 'critique',
                    'valeur': m.score, 'reference': 'maîtrise < 70% (confiance ≥ 0.3)',
                    'competence': m.competence,
                    'preuves': [{'score': m.score, 'confidence': m.confidence}]})

    # ── Séquences abandonnées ──────────────────────────────────────────────
    since14 = now - timedelta(days=14)
    aband = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, completee_le__isnull=True,
        derniere_activite__lt=since14, nb_blocs_consultes__gt=0,
    ).select_related('sequence')[:10]
    for s in aband:
        out.append({'signal_type': 'sequence_abandonnee', 'severity': 'moderee',
                    'valeur': (now - s.derniere_activite).days, 'reference': '> 14 j sans activité',
                    'sequence': s.sequence,
                    'preuves': [{'sequence': s.sequence_id, 'ratio_temps_pct': s.ratio_temps_pct}]})

    # ── Lacunes & maîtrise fragile (alimentent le diagnostic MASTERY_GAP) ──
    from analytics.models import KnowledgeGap, SkillMasteryScore, ContenuGenere

    for g in KnowledgeGap.objects.filter(
        apprenant=apprenant, statut__in=['detectee', 'en_cours'],
    ).select_related('sequence')[:15]:
        out.append({
            'signal_type': 'lacune_critique' if g.severity == 'critique' else 'lacune_moderee',
            'severity':    'critique' if g.severity == 'critique' else 'moderee',
            'valeur':      0,
            'reference':   f'lacune {g.severity}',
            'sequence':    g.sequence,
            'preuves':     g.evidence if isinstance(g.evidence, list) else [],
        })

    for m in SkillMasteryScore.objects.filter(
        apprenant=apprenant, sequence__isnull=False, niveau='fragile',
    ).select_related('sequence')[:15]:
        out.append({'signal_type': 'maitrise_fragile', 'severity': 'moderee',
                    'valeur': m.score, 'reference': 'niveau fragile', 'sequence': m.sequence})

    # Remédiation insuffisante : un contenu a été consulté mais la maîtrise reste faible
    for cg in ContenuGenere.objects.filter(
        apprenant=apprenant, sequence_source__isnull=False, a_ete_consulte=True,
    ).select_related('sequence_source')[:10]:
        seq_obj = cg.sequence_source
        m = SkillMasteryScore.objects.filter(apprenant=apprenant, sequence=seq_obj).first()
        if m and m.score < 50:
            out.append({'signal_type': 'remediation_insuffisante', 'severity': 'moderee',
                        'valeur': m.score, 'reference': 'contenu consulté mais maîtrise < 50%',
                        'sequence': seq_obj,
                        'preuves': [{'contenu_id': cg.pk, 'mastery': m.score}]})

    return out


def refresh_signals(apprenant, computed=None) -> list:
    """Recalcule les signaux : upsert des actifs, résolution des obsolètes."""
    from analytics.models import LearningSignal

    if computed is None:
        computed = compute_signals(apprenant)
    keep_ids = []
    for sig in computed:
        obj = emit_signal(
            apprenant, sig['signal_type'], sig['severity'],
            valeur=sig.get('valeur', 0.0),
            reference=sig.get('reference', ''),
            preuves=sig.get('preuves', []),
            **_target_kwargs(sig),
        )
        keep_ids.append(obj.pk)

    # Résoudre les signaux actifs qui ne sont plus pertinents
    LearningSignal.objects.filter(apprenant=apprenant, statut='actif') \
        .exclude(pk__in=keep_ids).update(statut='resolu', resolved_at=timezone.now())

    return list(LearningSignal.objects.filter(pk__in=keep_ids))
