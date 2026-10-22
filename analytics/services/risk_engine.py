# analytics/services/risk_engine.py
# ============================================================================
# MOTEUR DE RISQUE DE DÉCROCHAGE (Phase 9)
#
# Combine :
#   - le risque de base (dropout_engine : inactivité, maîtrise, sessions, lacunes)
#   - l'engagement (niveau, tendance, inactivité)
#   - la performance (difficulté répétée, régression, faiblesse)
#   - les diagnostics actifs (priorité)
#   - les interventions ignorées
# Produit un score 0-100, un niveau, des RAISONS explicables et une tendance.
# ============================================================================
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def compute_risk(apprenant) -> dict:
    from ..dropout_engine import compute_dropout_risk
    from analytics.models import (
        LearnerEngagementState, LearnerPerformanceState,
        LearningDiagnosis, RecommandationPedagogique,
    )

    now = timezone.now()
    base = compute_dropout_risk(apprenant)  # 0-100
    score = float(base)
    reasons = []
    breakdown = {'base': base}

    # ── Engagement ─────────────────────────────────────────────────────────
    eng = LearnerEngagementState.objects.filter(apprenant=apprenant).first()
    if eng:
        if eng.niveau == 'faible':
            score += 10; reasons.append('Engagement faible')
        if eng.tendance == 'baisse':
            score += 8; reasons.append('Engagement en baisse')
        if eng.last_activity and (now - eng.last_activity).days >= 14:
            score += 10; reasons.append('Inactivité > 14 jours')
        breakdown['engagement'] = {'niveau': eng.niveau, 'tendance': eng.tendance, 'score': eng.score}

    # ── Performance ────────────────────────────────────────────────────────
    perf = LearnerPerformanceState.objects.filter(apprenant=apprenant).first()
    if perf:
        if perf.status in ('difficulte_repetee', 'regression'):
            score += 12; reasons.append(f'Performance : {perf.get_status_display()}')
        if (perf.avg_score or 0) and perf.avg_score < 40:
            score += 8; reasons.append('Performance moyenne faible')
        breakdown['performance'] = {'avg': perf.avg_score, 'status': perf.status}

    # ── Diagnostics actifs ─────────────────────────────────────────────────
    diags = LearningDiagnosis.objects.filter(apprenant=apprenant, statut='actif')
    p1 = diags.filter(priority=1).count()
    p2 = diags.filter(priority=2).count()
    if p1:
        score += min(16, p1 * 8); reasons.append(f'{p1} diagnostic(s) critique(s) (P1)')
    if p2:
        score += min(8, p2 * 4); reasons.append(f'{p2} diagnostic(s) important(s) (P2)')
    breakdown['diagnostics'] = {'p1': p1, 'p2': p2, 'total': diags.count()}

    # ── Interventions ignorées ─────────────────────────────────────────────
    ignored = RecommandationPedagogique.objects.filter(apprenant=apprenant, est_ignoree=True).count()
    suivies = RecommandationPedagogique.objects.filter(apprenant=apprenant, est_suivie=True).count()
    if ignored >= 3:
        score += 6; reasons.append('Plusieurs interventions ignorées')
    breakdown['interventions'] = {'ignorees': ignored, 'suivies': suivies}

    score = round(min(100.0, score), 1)
    level = 'eleve' if score >= 70 else ('moyen' if score >= 40 else 'faible')

    return {
        'risk_score': score,
        'risk_level': level,
        'reasons': reasons,
        'breakdown': breakdown,
    }


def refresh_risk_state(apprenant, save: bool = True):
    from analytics.models import LearnerRiskState

    r = compute_risk(apprenant)
    obj, _ = LearnerRiskState.objects.get_or_create(apprenant=apprenant)
    prev = obj.risk_score
    obj.risk_score = r['risk_score']
    obj.risk_level = r['risk_level']
    obj.reasons = r['reasons']
    obj.breakdown = r['breakdown']
    if prev is None:
        obj.trend = 'stable'
    elif r['risk_score'] - prev >= 8:
        obj.trend = 'hausse'
    elif r['risk_score'] - prev <= -8:
        obj.trend = 'baisse'
    else:
        obj.trend = obj.trend or 'stable'
    if save:
        obj.save()
    return obj
