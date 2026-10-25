# analytics/services/engagement_engine.py
# ============================================================================
# MOTEUR D'ENGAGEMENT (Phase 4)
#
# Mesure la FRÉQUENCE et la RÉGULARITÉ d'interaction (≠ progression ≠ maîtrise) :
#   - sessions (30j), durée moyenne, temps hebdo, jours actifs, régularité
#   - dernière activité, interruptions, reprises
#   - score composite 0-100, niveau (faible/moyen/élevé), tendance
#
# S'appuie sur l'existant : BlocAnalytics (sessions) + BlocAnalyticsSummary.
# ============================================================================
import logging
from datetime import timedelta

from django.db.models import Max, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def _score_regularity(active_days_30: int) -> float:
    # 20 jours actifs sur 30 = 100
    return round(min(100.0, active_days_30 * (100.0 / 20)), 1)


def _score_frequency(sessions_30d: int) -> float:
    # 20 sessions sur 30j = 100
    return round(min(100.0, sessions_30d * 5.0), 1)


def _score_recency(last_activity) -> float:
    if not last_activity:
        return 0.0
    jours = (timezone.now() - last_activity).days
    if jours <= 2:  return 100.0
    if jours <= 7:  return 70.0
    if jours <= 14: return 40.0
    if jours <= 30: return 15.0
    return 5.0


def _trend_from_evolution(weekly: int, prev_weekly: int) -> str:
    if prev_weekly <= 0 and weekly <= 0:
        return 'stable'
    if prev_weekly <= 0:
        return 'hausse' if weekly > 0 else 'stable'
    delta = (weekly - prev_weekly) / prev_weekly
    if delta >= 0.2:  return 'hausse'
    if delta <= -0.2: return 'baisse'
    return 'stable'


def compute_engagement(apprenant) -> dict:
    from analytics.models import BlocAnalytics, BlocAnalyticsSummary

    now = timezone.now()
    since30 = now - timedelta(days=30)
    since7  = now - timedelta(days=7)
    prev7   = now - timedelta(days=14)

    closed = BlocAnalytics.objects.filter(apprenant=apprenant, ferme_le__isnull=False)

    sessions_30d = closed.filter(ouvert_le__gte=since30).count()
    durees = list(closed.filter(ouvert_le__gte=since30).values_list('duree_secondes', flat=True))
    avg_session = int(sum(durees) / len(durees)) if durees else 0

    weekly = closed.filter(ouvert_le__gte=since7).aggregate(t=Sum('duree_secondes'))['t'] or 0
    prev_weekly = closed.filter(
        ouvert_le__gte=prev7, ouvert_le__lt=since7,
    ).aggregate(t=Sum('duree_secondes'))['t'] or 0

    active_days = (
        BlocAnalytics.objects.filter(apprenant=apprenant, ouvert_le__gte=since30)
        .dates('ouvert_le', 'day').count()
    )
    last = BlocAnalytics.objects.filter(apprenant=apprenant).aggregate(m=Max('ouvert_le'))['m']

    # Interruptions : sessions récentes non terminées.
    interruptions = closed.filter(ouvert_le__gte=since30, complete_en_session=False).count()
    # Reprises : blocs rouverts plusieurs fois.
    resumes = BlocAnalyticsSummary.objects.filter(apprenant=apprenant, nb_ouvertures__gt=1).count()

    reg   = _score_regularity(active_days)
    freq  = _score_frequency(sessions_30d)
    rec   = _score_recency(last)
    trend = _trend_from_evolution(weekly, prev_weekly)
    evo   = {'hausse': 100.0, 'stable': 70.0, 'baisse': 40.0}[trend]

    score = round(reg * 0.30 + freq * 0.30 + rec * 0.20 + evo * 0.20, 1)

    if score >= 67:   niveau = 'eleve'
    elif score >= 34: niveau = 'moyen'
    else:             niveau = 'faible'

    # Signaux associés
    signals = []
    if last:
        jours = (now - last).days
        if jours >= 7:
            signals.append({'type': 'inactivite_prolongee', 'valeur': jours, 'unite': 'jours'})
    else:
        signals.append({'type': 'aucune_activite', 'valeur': 0, 'unite': 'jours'})
    if trend == 'baisse':
        signals.append({'type': 'baisse_engagement', 'valeur': round((weekly - prev_weekly) / 86400, 1), 'unite': 'min'})
    if interruptions >= 3:
        signals.append({'type': 'sessions_interrompues', 'valeur': interruptions})

    return {
        'score': score,
        'niveau': niveau,
        'tendance': trend,
        'sessions_30d': sessions_30d,
        'avg_session_sec': avg_session,
        'weekly_time_sec': weekly,
        'prev_weekly_sec': prev_weekly,
        'active_days_30': active_days,
        'regularity_pct': reg,
        'last_activity': last,
        'interruptions': interruptions,
        'resumes': resumes,
        'signals': signals,
    }


def refresh_engagement_state(apprenant, save: bool = True, computed: dict = None):
    """Recalcule et persiste le `LearnerEngagementState` (états précalculés OK)."""
    from analytics.models import LearnerEngagementState

    e = computed if computed is not None else compute_engagement(apprenant)
    obj, _ = LearnerEngagementState.objects.get_or_create(apprenant=apprenant)
    obj.score = e['score']
    obj.niveau = e['niveau']
    obj.tendance = e['tendance']
    obj.sessions_30d = e['sessions_30d']
    obj.avg_session_sec = e['avg_session_sec']
    obj.weekly_time_sec = e['weekly_time_sec']
    obj.prev_weekly_sec = e['prev_weekly_sec']
    obj.active_days_30 = e['active_days_30']
    obj.regularity_pct = e['regularity_pct']
    obj.last_activity = e['last_activity']
    obj.interruptions = e['interruptions']
    obj.resumes = e['resumes']
    obj.signals = e['signals']
    if save:
        obj.save()
    return obj
