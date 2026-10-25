# analytics/services/performance_engine.py
# ============================================================================
# MOTEUR DE PERFORMANCE (Phase 5)
#
# Agrège les résultats pédagogiques (quiz + évaluations) :
#   moyenne, dernier/meilleur/pire, tentatives, taux d'erreur, erreurs répétées,
#   évolution (récent vs précédent).
# Détecte : échec ponctuel, difficulté répétée, amélioration, stagnation,
#           régression.
# ============================================================================
import logging
from datetime import timedelta
from statistics import mean

from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)


def _eval_pct(note, bareme) -> float:
    try:
        b = float(bareme or 20) or 20.0
        return round((float(note) / b) * 100, 1)
    except Exception:
        return 0.0


def _detect_status(vals, recent_avg, previous_avg, trend, attempts_30d, repeated_errors, worst):
    low_recent = sum(1 for v in vals[-5:] if v < 50)

    if repeated_errors >= 2 or (attempts_30d >= 2 and low_recent >= 2):
        return 'difficulte_repetee'
    if (trend == 'hausse' and recent_avg is not None and previous_avg is not None
            and recent_avg > previous_avg + 10):
        return 'amelioration'
    if (trend == 'baisse' and recent_avg is not None and previous_avg is not None
            and recent_avg < previous_avg - 10):
        return 'regression'
    if attempts_30d >= 3 and (recent_avg or 0) < 50:
        return 'stagnation'
    if worst is not None and worst < 50:
        return 'echec_ponctuel'
    return 'none'


def compute_performance(apprenant) -> dict:
    from evaluations.models import PassageQuiz, PassageEvaluation, ReponseQuiz

    now = timezone.now()
    since30 = now - timedelta(days=30)

    # ── Scores quiz (0-100) ────────────────────────────────────────────────
    quiz_scores = []
    for p in PassageQuiz.objects.filter(apprenant=apprenant, termine=True).order_by('date_passage'):
        if p.score is None:
            continue
        quiz_scores.append((p.date_passage, round(float(p.score), 1), 'quiz', p.quiz_id))

    # ── Scores évaluations (normalisés 0-100) ──────────────────────────────
    eval_scores = []
    for p in PassageEvaluation.objects.filter(apprenant=apprenant, note__isnull=False) \
            .select_related('evaluation'):
        d = p.date_soumission or p.date_debut
        bareme = getattr(p.evaluation, 'bareme', 20)
        eval_scores.append((d, _eval_pct(p.note, bareme), 'evaluation', p.evaluation_id))

    all_scores = sorted(
        [x for x in (quiz_scores + eval_scores) if x[0] is not None],
        key=lambda x: x[0],
    )
    vals = [v for _, v, _, _ in all_scores]

    avg = round(mean(vals), 1) if vals else 0.0
    last = vals[-1] if vals else None
    best = max(vals) if vals else None
    worst = min(vals) if vals else None

    recent = [v for d, v, _, _ in all_scores if d and d >= since30]
    previous = [v for d, v, _, _ in all_scores if d and d < since30]
    recent_avg = round(mean(recent), 1) if recent else None
    previous_avg = round(mean(previous), 1) if previous else None

    # Fallback : si pas de comparatif temporel, couper en deux.
    if recent_avg is None and previous_avg is None and len(vals) >= 2:
        mid = len(vals) // 2
        previous_avg = round(mean(vals[:mid]), 1)
        recent_avg = round(mean(vals[mid:]), 1)

    if recent_avg is None or previous_avg is None:
        trend = 'stable'
    elif recent_avg - previous_avg >= 8:
        trend = 'hausse'
    elif recent_avg - previous_avg <= -8:
        trend = 'baisse'
    else:
        trend = 'stable'

    attempts_30d = sum(1 for d, _, _, _ in all_scores if d and d >= since30)

    # ── Erreurs répétées + taux d'erreur ───────────────────────────────────
    resp = ReponseQuiz.objects.filter(passage_quiz__apprenant=apprenant)
    total_resp = resp.count()
    wrong = resp.filter(points_obtenus=0).count()
    error_rate = round((wrong / total_resp) * 100, 1) if total_resp else 0.0

    repeated_errors = (
        resp.filter(points_obtenus=0)
        .values('question_id').annotate(n=Count('id')).filter(n__gte=2).count()
    )

    status = _detect_status(
        vals, recent_avg, previous_avg, trend, attempts_30d, repeated_errors, worst,
    )

    details = {
        'recent_scores': [v for _, v, _, _ in all_scores[-8:]],
        'by_type': {
            'quiz': len(quiz_scores),
            'evaluation': len(eval_scores),
        },
    }

    return {
        'avg_score': avg,
        'last_score': last,
        'best_score': best,
        'worst_score': worst,
        'recent_avg': recent_avg,
        'previous_avg': previous_avg,
        'attempts_total': len(vals),
        'attempts_30d': attempts_30d,
        'quiz_count': len(quiz_scores),
        'evaluation_count': len(eval_scores),
        'error_rate': error_rate,
        'repeated_errors': repeated_errors,
        'trend': trend,
        'status': status,
        'details': details,
    }


def refresh_performance_state(apprenant, save: bool = True, computed: dict = None):
    """Recalcule et persiste le `LearnerPerformanceState` (états précalculés OK)."""
    from analytics.models import LearnerPerformanceState

    p = computed if computed is not None else compute_performance(apprenant)
    obj, _ = LearnerPerformanceState.objects.get_or_create(apprenant=apprenant)
    for field in (
        'avg_score', 'last_score', 'best_score', 'worst_score', 'recent_avg',
        'previous_avg', 'attempts_total', 'attempts_30d', 'quiz_count',
        'evaluation_count', 'error_rate', 'repeated_errors', 'trend', 'status', 'details',
    ):
        setattr(obj, field, p[field])
    if save:
        obj.save()
    return obj
