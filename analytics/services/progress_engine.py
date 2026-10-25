# analytics/services/progress_engine.py
# ============================================================================
# MOTEUR DE PROGRESSION MULTI-NIVEAUX (Phase 3)
#
# Calcule la progression SÉPARÉMENT à chaque niveau :
#   Cours → Module → Séquence → Bloc
# avec des dimensions DISTINCTES :
#   - complétion (blocs/séquences terminés)
#   - temps réalisé vs estimé
#   - évaluation (score quiz)
#   - maîtrise (SkillMasteryScore)
#
# S'appuie sur l'existant : BlocProgress, *AnalyticsSummary, SkillMasteryScore.
# Calcule aussi le snapshot global `LearnerLearningState`.
# ============================================================================
import logging
from datetime import timedelta

from django.db.models import Avg, Count, Max, Q, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _enrolled_cours_ids(apprenant):
    from courses.models import InscriptionCours
    return list(
        InscriptionCours.objects.filter(apprenant=apprenant)
        .values_list('cours_id', flat=True).distinct()
    )


def _bloc_duree_estimee_sec(bloc) -> int:
    return int((getattr(bloc, 'duree_estimee_minutes', 0) or 0) * 60)


def _pct(part, total) -> int:
    return round((part / total) * 100) if total else 0


# ── Niveau BLOC ─────────────────────────────────────────────────────────────

def compute_block_progress(apprenant, bloc) -> dict:
    from courses.models import BlocProgress
    from analytics.models import BlocAnalyticsSummary

    termine = BlocProgress.objects.filter(
        apprenant=apprenant, bloc=bloc, est_termine=True,
    ).exists()
    summ = BlocAnalyticsSummary.objects.filter(apprenant=apprenant, bloc=bloc).first()
    est = _bloc_duree_estimee_sec(bloc)
    temps = summ.duree_totale_sec if summ else 0
    return {
        'bloc_id': bloc.pk,
        'titre': getattr(bloc, 'titre', ''),
        'termine': termine,
        'completion_pct': 100 if termine else 0,
        'temps_realise_sec': temps,
        'temps_estime_sec': est,
        'temps_pct': _pct(temps, est),
        'nb_ouvertures': summ.nb_ouvertures if summ else 0,
        'scroll_max_pct': summ.scroll_max_pct if summ else 0,
        'derniere_activite': summ.derniere_ouverture.isoformat() if summ and summ.derniere_ouverture else None,
    }


# ── Niveau SÉQUENCE ─────────────────────────────────────────────────────────

def compute_sequence_progress(apprenant, sequence) -> dict:
    from courses.models import BlocContenu, BlocProgress
    from analytics.models import SequenceAnalyticsSummary, SkillMasteryScore, KnowledgeGap

    total = BlocContenu.objects.filter(sequence=sequence).count()
    done = BlocProgress.objects.filter(
        apprenant=apprenant, bloc__sequence=sequence, est_termine=True,
    ).count()

    summ = SequenceAnalyticsSummary.objects.filter(apprenant=apprenant, sequence=sequence).first()
    temps_realise = summ.duree_totale_sec if summ else 0
    temps_estime = (summ.duree_estimee_sec if summ else 0) or sum(
        _bloc_duree_estimee_sec(b) for b in BlocContenu.objects.filter(sequence=sequence)
    )
    mastery = SkillMasteryScore.objects.filter(apprenant=apprenant, sequence=sequence).first()

    return {
        'sequence_id': sequence.pk,
        'titre': getattr(sequence, 'titre', ''),
        'cours_id': getattr(getattr(sequence, 'module', None), 'cours_id', None),
        'module_id': getattr(sequence, 'module_id', None),
        'blocs_total': total,
        'blocs_termines': done,
        'completion_pct': _pct(done, total),
        'temps_realise_sec': temps_realise,
        'temps_estime_sec': temps_estime,
        'temps_pct': _pct(temps_realise, temps_estime),
        'quiz_score': float(summ.score_moyen_quiz) if summ else 0,
        'mastery_score': float(mastery.score) if mastery else None,
        'mastery_niveau': mastery.niveau if mastery else None,
        'termine': bool(summ and summ.completee_le),
        'a_lacune': KnowledgeGap.objects.filter(
            apprenant=apprenant, sequence=sequence, statut__in=['detectee', 'en_cours'],
        ).exists(),
        'derniere_activite': summ.derniere_activite.isoformat() if summ and summ.derniere_activite else None,
    }


# ── Niveau MODULE ───────────────────────────────────────────────────────────

def compute_module_progress(apprenant, module) -> dict:
    from courses.models import Sequence, BlocContenu, BlocProgress
    from analytics.models import SequenceAnalyticsSummary, ModuleAnalyticsSummary

    seq_ids = list(Sequence.objects.filter(module=module).values_list('pk', flat=True))
    total_blocs = BlocContenu.objects.filter(sequence_id__in=seq_ids).count()
    done_blocs = BlocProgress.objects.filter(
        apprenant=apprenant, bloc__sequence_id__in=seq_ids, est_termine=True,
    ).count()

    summ = ModuleAnalyticsSummary.objects.filter(apprenant=apprenant, module=module).first()
    temps_realise = summ.duree_totale_sec if summ else 0
    temps_estime = (summ.duree_estimee_sec if summ else 0) or sum(
        _bloc_duree_estimee_sec(b) for b in BlocContenu.objects.filter(sequence_id__in=seq_ids)
    )
    seq_done = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, sequence_id__in=seq_ids, completee_le__isnull=False,
    ).count()

    return {
        'module_id': module.pk,
        'titre': getattr(module, 'titre', ''),
        'cours_id': getattr(module, 'cours_id', None),
        'sequences_total': len(seq_ids),
        'sequences_terminees': seq_done,
        'blocs_total': total_blocs,
        'blocs_termines': done_blocs,
        'completion_pct': _pct(done_blocs, total_blocs),
        'temps_realise_sec': temps_realise,
        'temps_estime_sec': temps_estime,
        'temps_pct': _pct(temps_realise, temps_estime),
        'quiz_score': float(summ.score_moyen_quiz) if summ else 0,
        'termine': bool(summ and summ.complete_le),
    }


# ── Niveau COURS ────────────────────────────────────────────────────────────

def compute_cours_progress(apprenant, cours) -> dict:
    from courses.models import Module, BlocContenu, BlocProgress
    from analytics.models import SequenceAnalyticsSummary

    mod_ids = list(Module.objects.filter(cours=cours).values_list('pk', flat=True))
    total_blocs = BlocContenu.objects.filter(sequence__module_id__in=mod_ids).count()
    done_blocs = BlocProgress.objects.filter(
        apprenant=apprenant, bloc__sequence__module_id__in=mod_ids, est_termine=True,
    ).count()
    # Temps via les summaries de séquences du cours
    agg = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, sequence__module_id__in=mod_ids,
    ).aggregate(
        temps=Sum('duree_totale_sec'),
        temps_estime=Sum('duree_estimee_sec'),
        quiz=Avg('score_moyen_quiz'),
        seq_done=Count('id', filter=Q(completee_le__isnull=False)),
    )
    temps_realise = agg['temps'] or 0
    temps_estime = (agg['temps_estime'] or 0) or sum(
        _bloc_duree_estimee_sec(b)
        for b in BlocContenu.objects.filter(sequence__module_id__in=mod_ids)
    )
    return {
        'cours_id': cours.pk,
        'titre': getattr(cours, 'titre', ''),
        'modules_total': len(mod_ids),
        'blocs_total': total_blocs,
        'blocs_termines': done_blocs,
        'completion_pct': _pct(done_blocs, total_blocs),
        'sequences_terminees': agg['seq_done'] or 0,
        'temps_realise_sec': temps_realise,
        'temps_estime_sec': temps_estime,
        'temps_pct': _pct(temps_realise, temps_estime),
        'quiz_score': float(agg['quiz'] or 0),
    }


# ── ÉTAT GLOBAL ─────────────────────────────────────────────────────────────

def compute_learning_state(apprenant) -> dict:
    """Agrège l'état d'apprentissage global (progressions + quiz + maîtrise)."""
    from courses.models import Cours, Module, BlocContenu, BlocProgress
    from analytics.models import (
        BlocAnalyticsSummary, SequenceAnalyticsSummary, SkillMasteryScore, KnowledgeGap,
    )

    cours_ids = _enrolled_cours_ids(apprenant)
    now = timezone.now()

    if not cours_ids:
        return {
            'global_progress_pct': 0, 'total_time_sec': 0, 'last_activity': None,
            'activity_days_30': 0, 'cours_count': 0, 'modules_done': 0,
            'modules_in_progress': 0, 'sequences_done': 0, 'sequences_blocked': 0,
            'avg_quiz_score': 0, 'avg_mastery': 0, 'details': {'cours': []},
        }

    total_blocs = BlocContenu.objects.filter(sequence__module__cours_id__in=cours_ids).count()
    done_blocs = BlocProgress.objects.filter(
        apprenant=apprenant, bloc__sequence__module__cours_id__in=cours_ids, est_termine=True,
    ).count()

    bas = BlocAnalyticsSummary.objects.filter(apprenant=apprenant, cours_id__in=cours_ids)
    agg = bas.aggregate(
        temps=Sum('duree_totale_sec'),
        dernier=Max('derniere_ouverture'),
    )
    total_time = agg['temps'] or 0
    last_activity = agg['dernier']

    # Jours actifs sur 30 j (distinct dates)
    since30 = now - timedelta(days=30)
    activity_days = (
        bas.filter(derniere_ouverture__gte=since30)
        .dates('derniere_ouverture', 'day').count()
    )

    # Modules terminés / en cours (blocs terminés vs total)
    mod_ids = list(Module.objects.filter(cours_id__in=cours_ids).values_list('pk', flat=True))
    total_by_mod = {
        r['sequence__module_id']: r['n']
        for r in BlocContenu.objects.filter(sequence__module_id__in=mod_ids)
        .values('sequence__module_id').annotate(n=Count('id'))
    }
    done_by_mod = {
        r['bloc__sequence__module_id']: r['n']
        for r in BlocProgress.objects.filter(
            apprenant=apprenant, bloc__sequence__module_id__in=mod_ids, est_termine=True,
        ).values('bloc__sequence__module_id').annotate(n=Count('id'))
    }
    modules_done = sum(1 for m in mod_ids if total_by_mod.get(m, 0) and done_by_mod.get(m, 0) == total_by_mod.get(m))
    modules_in_progress = sum(1 for m in mod_ids if 0 < done_by_mod.get(m, 0) < total_by_mod.get(m, 1))

    seq_done = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, cours_id__in=cours_ids, completee_le__isnull=False,
    ).count()
    seq_blocked = KnowledgeGap.objects.filter(
        apprenant=apprenant, statut__in=['detectee', 'en_cours'],
        sequence__module__cours_id__in=cours_ids,
    ).values('sequence_id').distinct().count()

    avg_quiz = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, cours_id__in=cours_ids,
    ).aggregate(v=Avg('score_moyen_quiz'))['v'] or 0
    avg_mastery = SkillMasteryScore.objects.filter(
        apprenant=apprenant, sequence__isnull=False, sequence__module__cours_id__in=cours_ids,
    ).aggregate(v=Avg('score'))['v'] or 0

    # Détail par cours
    details = []
    for cours in Cours.objects.filter(pk__in=cours_ids):
        details.append(compute_cours_progress(apprenant, cours))

    return {
        'global_progress_pct': _pct(done_blocs, total_blocs),
        'total_time_sec': total_time,
        'last_activity': last_activity,
        'activity_days_30': activity_days,
        'cours_count': len(cours_ids),
        'modules_done': modules_done,
        'modules_in_progress': modules_in_progress,
        'sequences_done': seq_done,
        'sequences_blocked': seq_blocked,
        'avg_quiz_score': round(float(avg_quiz), 1),
        'avg_mastery': round(float(avg_mastery), 1),
        'details': {'cours': details},
    }


def refresh_learning_state(apprenant, save: bool = True):
    """Recalcule et persiste le `LearnerLearningState` (tendance incluse)."""
    from analytics.models import LearnerLearningState

    state = compute_learning_state(apprenant)
    obj, _ = LearnerLearningState.objects.get_or_create(apprenant=apprenant)

    # Tendance vs valeur précédente (±5 pts)
    prev = obj.global_progress_pct
    new = state['global_progress_pct']
    if prev is None:
        trend = 'stable'
    elif new - prev >= 5:
        trend = 'hausse'
    elif new - prev <= -5:
        trend = 'baisse'
    else:
        trend = obj.trend or 'stable'

    obj.global_progress_pct = new
    obj.total_time_sec      = state['total_time_sec']
    obj.last_activity       = state['last_activity']
    obj.activity_days_30    = state['activity_days_30']
    obj.cours_count         = state['cours_count']
    obj.modules_done        = state['modules_done']
    obj.modules_in_progress = state['modules_in_progress']
    obj.sequences_done      = state['sequences_done']
    obj.sequences_blocked   = state['sequences_blocked']
    obj.avg_quiz_score      = state['avg_quiz_score']
    obj.avg_mastery         = state['avg_mastery']
    # Niveau de maîtrise global (Phase 6)
    m = obj.avg_mastery or 0
    obj.mastery_level = 'faible' if m < 40 else ('moyen' if m < 70 else 'eleve')
    obj.trend               = trend
    obj.details             = state['details']

    # Niveau d'engagement (phase 4) et de risque (phase 9), si déjà calculés
    try:
        from analytics.models import LearnerEngagementState, LearnerRiskState
        eng = LearnerEngagementState.objects.filter(apprenant=apprenant).first()
        if eng and eng.niveau:
            obj.engagement_level = eng.niveau
        risk = LearnerRiskState.objects.filter(apprenant=apprenant).first()
        if risk and risk.risk_level:
            obj.risk_level = risk.risk_level
    except Exception:
        pass

    if save:
        obj.save()
    return obj

