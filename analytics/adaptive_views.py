# analytics/adaptive_views.py
# ============================================================================
# ADAPTIVE LEARNING API — Mastery, Gaps, Alerts, Profile, Risk
# ============================================================================
import logging
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SkillMasteryScore, KnowledgeGap, DropoutAlert, LearnerProfile, LearningEvent
from .views import _get_apprenant

logger = logging.getLogger(__name__)

# Seuil « temps passé / temps estimé » (%) au-delà duquel on demande à
# l'apprenant s'il est bloqué AVANT de lui proposer un contenu.
SEUIL_AIDE = 120


# ── Helpers sérialisation ─────────────────────────────────────────────────────

def _fmt_mastery(s: SkillMasteryScore) -> dict:
    return {
        'id':               s.pk,
        'score':            s.score,
        'niveau':           s.niveau,
        'score_quiz':       s.score_quiz,
        'score_completion': s.score_completion,
        'score_temps':      s.score_temps,
        'tendance':         s.tendance,
        'score_precedent':  s.score_precedent,
        'cours_id':         s.cours_id,
        'module_id':        s.module_id,
        'sequence_id':      s.sequence_id,
        'updated_at':       s.updated_at.isoformat(),
    }


def _fmt_gap(g: KnowledgeGap) -> dict:
    seq = g.sequence
    mod = getattr(seq, 'module', None)
    crs = getattr(mod, 'cours', None) if mod else None
    return {
        'id':             g.pk,
        'sequence_id':    g.sequence_id,
        'sequence_titre': seq.titre,
        'module_titre':   mod.titre if mod else '',
        'cours_titre':    crs.titre if crs else '',
        'severity':       g.severity,
        'statut':         g.statut,
        'description':    g.description,
        'evidence':       g.evidence,
        'detected_at':    g.detected_at.isoformat(),
        'resolved_at':    g.resolved_at.isoformat() if g.resolved_at else None,
    }


def _fmt_alert(a: DropoutAlert) -> dict:
    return {
        'id':           a.pk,
        'alert_type':   a.alert_type,
        'score_risque': a.score_risque,
        'message':      a.message,
        'statut':       a.statut,
        'cours_id':     a.cours_id,
        'created_at':   a.created_at.isoformat(),
    }


# ── Views ─────────────────────────────────────────────────────────────────────

class MasteryView(APIView):
    """
    GET /api/analytics/mastery/<apprenant_id>/
    Paramètres optionnels : ?cours_id=&module_id=&sequence_id=
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        qs = SkillMasteryScore.objects.filter(apprenant=apprenant)
        for param, field in [
            ('cours_id',    'cours_id'),
            ('module_id',   'module_id'),
            ('sequence_id', 'sequence_id'),
        ]:
            val = request.query_params.get(param)
            if val:
                qs = qs.filter(**{field: val})

        return Response({'mastery': [_fmt_mastery(s) for s in qs]})


class MasteryRefreshView(APIView):
    """
    POST /api/analytics/mastery/<apprenant_id>/refresh/
    Body: { "sequence_id": <int> }
    Recalcule mastery → module → cours et détecte les lacunes.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        seq_id = request.data.get('sequence_id')
        if not seq_id:
            return Response({'error': 'sequence_id requis'}, status=400)

        try:
            from courses.models import Sequence
            seq = Sequence.objects.select_related('module__cours').get(pk=seq_id)
        except Exception:
            return Response({'error': f'Séquence {seq_id} introuvable'}, status=404)

        from .mastery_engine import compute_sequence_mastery, compute_module_mastery, compute_cours_mastery
        from .gap_engine     import detect_and_update_gap

        mastery = compute_sequence_mastery(apprenant, seq)
        if seq.module:
            compute_module_mastery(apprenant, seq.module)
            if seq.module.cours:
                compute_cours_mastery(apprenant, seq.module.cours)

        gap = detect_and_update_gap(apprenant, seq) if mastery else None

        return Response({
            'status':  'ok',
            'score':   mastery.score if mastery else 0,
            'niveau':  mastery.niveau if mastery else 'non_acquis',
            'gap':     _fmt_gap(gap) if gap else None,
        })


class KnowledgeGapListView(APIView):
    """
    GET /api/analytics/gaps/<apprenant_id>/
    Paramètre optionnel : ?statut=detectee|en_cours|resolue|all
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        qs = KnowledgeGap.objects.filter(apprenant=apprenant).select_related(
            'sequence__module__cours'
        ).order_by('-detected_at')

        statut = request.query_params.get('statut', 'active')
        if statut == 'active':
            qs = qs.filter(statut__in=['detectee', 'en_cours'])
        elif statut != 'all':
            qs = qs.filter(statut=statut)

        return Response({'gaps': [_fmt_gap(g) for g in qs]})


class KnowledgeGapAckView(APIView):
    """PATCH /api/analytics/gaps/<pk>/ack/ — Passe en 'en_cours'"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        gap = get_object_or_404(KnowledgeGap, pk=pk, apprenant=apprenant)
        if gap.statut == 'detectee':
            gap.statut = 'en_cours'
            gap.save(update_fields=['statut'])
        return Response({'status': 'ok', 'statut': gap.statut})


class DropoutAlertListView(APIView):
    """
    GET /api/analytics/alerts/<apprenant_id>/
    Paramètre optionnel : ?statut=active|vue|resolue|all
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        qs = DropoutAlert.objects.filter(apprenant=apprenant).order_by('-created_at')
        statut = request.query_params.get('statut', 'active')
        if statut != 'all':
            qs = qs.filter(statut=statut)

        return Response({'alerts': [_fmt_alert(a) for a in qs]})


class DropoutAlertAckView(APIView):
    """PATCH /api/analytics/alerts/<pk>/ack/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        alert = get_object_or_404(DropoutAlert, pk=pk, apprenant=apprenant)
        alert.statut = 'vue'
        alert.save(update_fields=['statut'])
        return Response({'status': 'ok'})


class LearnerProfileView(APIView):
    """GET /api/analytics/profil/<apprenant_id>/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        profile, _ = LearnerProfile.objects.get_or_create(apprenant=apprenant)

        # Stats agrégées pour enrichir la réponse
        from .models import SkillMasteryScore, KnowledgeGap
        mastery_scores = list(
            SkillMasteryScore.objects.filter(apprenant=apprenant, sequence__isnull=False)
            .values_list('score', flat=True)
        )
        avg_mastery = round(sum(mastery_scores) / len(mastery_scores), 1) if mastery_scores else 0

        gaps_count  = KnowledgeGap.objects.filter(
            apprenant=apprenant, statut__in=['detectee', 'en_cours']
        ).count()

        return Response({
            'score_engagement':        profile.score_engagement,
            'score_regularite':        profile.score_regularite,
            'score_risque_decrochage': profile.score_risque_decrochage,
            'profil_type':             profile.profil_type,
            'type_contenu_prefere':    profile.type_contenu_prefere,
            'updated_at':              profile.updated_at.isoformat(),
            'avg_mastery':             avg_mastery,
            'nb_gaps_actifs':          gaps_count,
            'nb_sequences_evaluees':   len(mastery_scores),
        })


class BulkLearningEventsView(APIView):
    """
    POST /api/analytics/events/bulk/
    Body: liste d'événements xAPI-like
    [{event_type, session_id, ts, payload}, ...]
    Accepté en JSON ou Beacon API (content-type: application/json).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request)
        raw = request.data
        if not isinstance(raw, list):
            raw = []

        from .services.event_service import build_event

        events = []
        for item in raw[:200]:  # limite anti-abus
            if not isinstance(item, dict):
                continue
            if not (item.get('event_type') or item.get('type')):
                continue
            try:
                events.append(build_event(apprenant, item))
            except Exception as exc:  # noqa: BLE001
                logger.warning('[events/bulk] item ignoré : %s', exc)

        if events:
            LearningEvent.objects.bulk_create(events, ignore_conflicts=True)

        return Response({'created': len(events)}, status=status.HTTP_201_CREATED)


class RiskScoreView(APIView):
    """
    GET /api/analytics/risk/<apprenant_id>/
    Paramètre optionnel : ?cours_id=<int>
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        cours = None
        cours_id = request.query_params.get('cours_id')
        if cours_id:
            try:
                from courses.models import Cours
                cours = Cours.objects.get(pk=cours_id)
            except Exception:
                pass

        from .services.risk_engine import refresh_risk_state
        s = refresh_risk_state(apprenant)

        payload = {
            # Champs historiques (compatibilité frontend) :
            'score_risque': s.risk_score,
            'niveau':       s.risk_level,
            # Champs enrichis (Phase 9) :
            'risk_score':   s.risk_score,
            'risk_level':   s.risk_level,
            'reasons':      s.reasons,
            'breakdown':    s.breakdown,
            'trend':        s.trend,
            'updated_at':   s.updated_at.isoformat(),
        }
        # Risque spécifique à un cours (si demandé), sans casser l'existant.
        if cours is not None:
            from .dropout_engine import compute_dropout_risk
            payload['score_risque_cours'] = compute_dropout_risk(apprenant, cours)
        return Response(payload)


class LearnerLearningStateView(APIView):
    """
    GET /api/v1/analytics/learning-state/<apprenant_id>/
    Recalcule puis renvoie l'état d'apprentissage agrégé (snapshot).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.progress_engine import refresh_learning_state
        from .services.refresh_guard import fresh_or_run
        from .models import LearnerLearningState
        fresh_or_run(apprenant, 'learning_state', lambda: refresh_learning_state(apprenant))
        s = LearnerLearningState.objects.filter(apprenant=apprenant).first() or refresh_learning_state(apprenant)
        return Response({
            'global_progress_pct': s.global_progress_pct,
            'total_time_sec':      s.total_time_sec,
            'last_activity':       s.last_activity.isoformat() if s.last_activity else None,
            'activity_days_30':    s.activity_days_30,
            'cours_count':         s.cours_count,
            'modules_done':        s.modules_done,
            'modules_in_progress': s.modules_in_progress,
            'sequences_done':      s.sequences_done,
            'sequences_blocked':   s.sequences_blocked,
            'avg_quiz_score':      s.avg_quiz_score,
            'avg_mastery':         s.avg_mastery,
            'trend':               s.trend,
            'engagement_level':    s.engagement_level,
            'risk_level':          s.risk_level,
            'mastery_level':       s.mastery_level,
            'details':             s.details,
            'updated_at':          s.updated_at.isoformat(),
        })


class LearnerProgressView(APIView):
    """
    GET /api/v1/analytics/progress/<apprenant_id>/
    Progressions séparées par niveau. ?cours_id=<int> pour le détail
    modules/séquences d'un cours.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from courses.models import Cours, Module, Sequence
        from .services.progress_engine import (
            compute_learning_state, compute_cours_progress,
            compute_module_progress, compute_sequence_progress,
        )

        state = compute_learning_state(apprenant)
        details_cours = state['details']['cours']

        cours_id = request.query_params.get('cours_id')
        if cours_id:
            crs = Cours.objects.filter(pk=cours_id).first()
            if crs:
                modules = [compute_module_progress(apprenant, m)
                           for m in Module.objects.filter(cours=crs).order_by('ordre')]
                sequences = [compute_sequence_progress(apprenant, s)
                             for s in Sequence.objects.filter(module__cours=crs).order_by('ordre')]
                return Response({
                    'cours': compute_cours_progress(apprenant, crs),
                    'modules': modules,
                    'sequences': sequences,
                })

        state_serializable = {k: v for k, v in state.items() if k != 'details'}
        state_serializable['last_activity'] = (
            state['last_activity'].isoformat() if state['last_activity'] else None
        )
        # Tendance : depuis le snapshot stocké (calculée par refresh_learning_state)
        from .models import LearnerLearningState
        ls = LearnerLearningState.objects.filter(apprenant=apprenant).first()
        state_serializable['trend'] = ls.trend if ls else 'stable'
        return Response({'global': state_serializable, 'cours': details_cours})


class LearnerEngagementView(APIView):
    """
    GET /api/v1/analytics/engagement/<apprenant_id>/
    Recalcule puis renvoie l'état d'engagement.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.engagement_engine import refresh_engagement_state
        from .services.refresh_guard import fresh_or_run
        from .models import LearnerEngagementState
        fresh_or_run(apprenant, 'engagement', lambda: refresh_engagement_state(apprenant))
        e = LearnerEngagementState.objects.filter(apprenant=apprenant).first() or refresh_engagement_state(apprenant)
        return Response({
            'score':            e.score,
            'niveau':           e.niveau,
            'tendance':         e.tendance,
            'sessions_30d':     e.sessions_30d,
            'avg_session_sec':  e.avg_session_sec,
            'weekly_time_sec':  e.weekly_time_sec,
            'prev_weekly_sec':  e.prev_weekly_sec,
            'active_days_30':   e.active_days_30,
            'regularity_pct':   e.regularity_pct,
            'last_activity':    e.last_activity.isoformat() if e.last_activity else None,
            'interruptions':    e.interruptions,
            'resumes':          e.resumes,
            'signals':          e.signals,
            'updated_at':       e.updated_at.isoformat(),
        })


class LearnerPerformanceView(APIView):
    """
    GET /api/v1/analytics/performance/<apprenant_id>/
    Recalcule puis renvoie l'état de performance (quiz + évaluations).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.performance_engine import refresh_performance_state
        from .services.refresh_guard import fresh_or_run
        from .models import LearnerPerformanceState
        fresh_or_run(apprenant, 'performance', lambda: refresh_performance_state(apprenant))
        p = LearnerPerformanceState.objects.filter(apprenant=apprenant).first() or refresh_performance_state(apprenant)
        return Response({
            'avg_score':       p.avg_score,
            'last_score':      p.last_score,
            'best_score':      p.best_score,
            'worst_score':     p.worst_score,
            'recent_avg':      p.recent_avg,
            'previous_avg':    p.previous_avg,
            'attempts_total':  p.attempts_total,
            'attempts_30d':    p.attempts_30d,
            'quiz_count':      p.quiz_count,
            'evaluation_count': p.evaluation_count,
            'error_rate':      p.error_rate,
            'repeated_errors': p.repeated_errors,
            'trend':           p.trend,
            'status':          p.status,
            'details':         p.details,
            'updated_at':      p.updated_at.isoformat(),
        })


class LearnerCompetencesView(APIView):
    """
    GET /api/v1/analytics/competences/<apprenant_id>/
    Recalcule et renvoie la maîtrise par compétence (+confiance), et le
    résumé {fortes, à renforcer}.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.competence_engine import refresh_all_competences, competences_summary
        from .services.refresh_guard import fresh_or_run
        fresh_or_run(apprenant, 'competences', lambda: refresh_all_competences(apprenant))
        return Response(competences_summary(apprenant))


class LearnerSignalsView(APIView):
    """
    GET /api/v1/analytics/signals/<apprenant_id>/
    Recalcule puis renvoie les signaux pédagogiques actifs.
    Paramètre optionnel : ?all=1 pour inclure les signaux résolus.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.signal_engine import refresh_signals
        from .services.refresh_guard import fresh_or_run
        from .models import LearningSignal

        fresh_or_run(apprenant, 'signals', lambda: refresh_signals(apprenant))
        qs = LearningSignal.objects.filter(apprenant=apprenant)
        if request.query_params.get('all') not in ('1', 'true', 'True'):
            qs = qs.filter(statut='actif')
        qs = qs[:100]

        def fmt(s):
            return {
                'id': s.pk,
                'signal_type': s.signal_type,
                'severity': s.severity,
                'valeur': s.valeur,
                'reference': s.reference,
                'preuves': s.preuves,
                'statut': s.statut,
                'cours_id': s.cours_id,
                'module_id': s.module_id,
                'sequence_id': s.sequence_id,
                'bloc_id': s.bloc_id,
                'competence_id': s.competence_id,
                'competence': s.competence.libelle if s.competence else None,
                'detected_at': s.detected_at.isoformat(),
                'updated_at': s.updated_at.isoformat(),
            }

        sigs = [fmt(s) for s in qs.select_related('competence')]
        return Response({'signals': sigs, 'total': len(sigs)})


class LearnerDiagnosticsView(APIView):
    """
    GET /api/v1/analytics/diagnostics/<apprenant_id>/
    Recalcule puis renvoie les diagnostics pédagogiques (agrégation des signaux).
    Paramètre optionnel : ?all=1 pour inclure les diagnostics résolus.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.diagnosis_engine import refresh_diagnoses
        from .services.refresh_guard import fresh_or_run
        from .models import LearningDiagnosis

        fresh_or_run(apprenant, 'diagnoses', lambda: refresh_diagnoses(apprenant))
        qs = LearningDiagnosis.objects.filter(apprenant=apprenant).select_related('competence')
        if request.query_params.get('all') not in ('1', 'true', 'True'):
            qs = qs.filter(statut='actif')
        qs = qs[:100]

        def fmt(d):
            return {
                'id': d.pk,
                'diagnosis_type': d.diagnosis_type,
                'severity': d.severity,
                'priority': d.priority,
                'confidence': d.confidence,
                'signal_types': d.signal_types,
                'evidence': d.evidence,
                'reason': d.reason,
                'statut': d.statut,
                'cours_id': d.cours_id,
                'module_id': d.module_id,
                'sequence_id': d.sequence_id,
                'bloc_id': d.bloc_id,
                'competence_id': d.competence_id,
                'competence': d.competence.libelle if d.competence else None,
                'detected_at': d.detected_at.isoformat(),
                'updated_at': d.updated_at.isoformat(),
            }

        diags = [fmt(d) for d in qs]
        return Response({'diagnostics': diags, 'total': len(diags)})


class LearnerOutcomesView(APIView):
    """
    GET /api/v1/analytics/outcomes/<apprenant_id>/
    Renvoie l'efficacité mesurée des interventions (avant/après).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.outcome_engine import refresh_outcomes
        from .services.refresh_guard import fresh_or_run
        from .models import InterventionOutcome

        fresh_or_run(apprenant, 'outcomes', lambda: refresh_outcomes(apprenant))
        qs = InterventionOutcome.objects.filter(apprenant=apprenant).select_related('intervention')[:100]

        def fmt(o):
            return {
                'id': o.pk,
                'intervention_id': o.intervention_id,
                'intervention_type': o.intervention.intervention_type if o.intervention else None,
                'score_before': o.score_before,
                'score_after': o.score_after,
                'mastery_before': o.mastery_before,
                'mastery_after': o.mastery_after,
                'completion': o.completion,
                'improvement': o.improvement,
                'effectiveness': o.effectiveness,
                'measured_at': o.measured_at.isoformat() if o.measured_at else None,
            }

        items = [fmt(o) for o in qs]
        return Response({'outcomes': items, 'total': len(items)})


class InterventionGenerateView(APIView):
    """
    POST /api/v1/analytics/interventions/<pk>/generer/
    Déclenche la génération IA de l'intervention (garde-fous inclus).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        from .models import LearningIntervention
        from users.access_control import user_can_access_apprenant

        iv = get_object_or_404(LearningIntervention, pk=pk)
        if not user_can_access_apprenant(request.user, iv.apprenant):
            return Response({'error': 'Accès refusé'}, status=403)

        from .services.ai_intervention_service import request_intervention_generation
        req, reason = request_intervention_generation(iv)
        if not req:
            return Response({'status': reason, 'request_id': None}, status=200)

        from .views import _run_in_thread
        _run_in_thread(req.pk)
        return Response({'status': 'pending', 'request_id': req.pk}, status=202)


class LearnerInterventionsView(APIView):
    """
    GET /api/v1/analytics/interventions/<apprenant_id>/
    Recalcule puis renvoie les interventions issues des diagnostics.
    Paramètre optionnel : ?all=1 pour inclure les terminées/ignorées.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .services.intervention_engine import refresh_interventions
        from .services.refresh_guard import fresh_or_run
        from .models import LearningIntervention

        fresh_or_run(apprenant, 'interventions', lambda: refresh_interventions(apprenant))
        qs = LearningIntervention.objects.filter(apprenant=apprenant) \
            .select_related('competence', 'diagnosis')
        if request.query_params.get('all') not in ('1', 'true', 'True'):
            qs = qs.filter(status__in=['proposee', 'acceptee', 'en_cours'])
        qs = qs[:100]

        def fmt(i):
            return {
                'id': i.pk,
                'intervention_type': i.intervention_type,
                'priority': i.priority,
                'status': i.status,
                'message': i.message,
                'reason': i.reason,
                'diagnosis_id': i.diagnosis_id,
                'diagnosis_type': i.diagnosis.diagnosis_type if i.diagnosis else None,
                'cours_id': i.cours_id,
                'module_id': i.module_id,
                'sequence_id': i.sequence_id,
                'bloc_id': i.bloc_id,
                'competence_id': i.competence_id,
                'competence': i.competence.libelle if i.competence else None,
                'contenu_genere': i.contenu_genere_id,
                'quiz_genere': i.quiz_genere_id,
                'expires_at': i.expires_at.isoformat() if i.expires_at else None,
                'created_at': i.created_at.isoformat(),
            }

        items = [fmt(i) for i in qs]
        return Response({'interventions': items, 'total': len(items)})


class CohortOverviewView(APIView):
    """
    GET /api/v1/analytics/cohort/  (?cours_id=)
    Vue agrégée du périmètre de l'utilisateur (formateur/responsable/admin) :
    maîtrise, engagement, risque, difficultés principales, apprenants à surveiller.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.db.models import Count
        from users.models import Apprenant
        from users.access_control import accessible_apprenants
        from analytics.models import (
            LearnerLearningState, LearnerEngagementState,
            LearnerRiskState, LearningDiagnosis,
        )

        allowed = accessible_apprenants(request.user)
        appr_qs = Apprenant.objects.filter(is_active=True) if allowed is None else allowed.filter(is_active=True)

        cours_id = request.query_params.get('cours_id')
        ids = list(appr_qs.values_list('pk', flat=True))
        if cours_id:
            from courses.models import InscriptionCours
            ids = list(
                InscriptionCours.objects.filter(cours_id=cours_id, apprenant_id__in=ids)
                .values_list('apprenant_id', flat=True).distinct()
            )

        total = len(ids)
        ls = LearnerLearningState.objects.filter(apprenant_id__in=ids)
        en = LearnerEngagementState.objects.filter(apprenant_id__in=ids)
        rk = LearnerRiskState.objects.filter(apprenant_id__in=ids)
        diags = LearningDiagnosis.objects.filter(apprenant_id__in=ids, statut='actif')

        mastery = {
            'faible': ls.filter(mastery_level='faible').count(),
            'moyen':  ls.filter(mastery_level='moyen').count(),
            'eleve':  ls.filter(mastery_level='eleve').count(),
        }
        engagement = {
            'faible': en.filter(niveau='faible').count(),
            'moyen':  en.filter(niveau='moyen').count(),
            'eleve':  en.filter(niveau='eleve').count(),
        }
        risk = {
            'faible': rk.filter(risk_level='faible').count(),
            'moyen':  rk.filter(risk_level='moyen').count(),
            'eleve':  rk.filter(risk_level='eleve').count(),
        }

        # Difficultés principales (compétence ou type de diagnostic)
        top_diag = list(
            diags.values('competence__libelle', 'diagnosis_type')
            .annotate(n=Count('id')).order_by('-n')[:6]
        )
        # Libellés français : le code technique (MASTERY_GAP, …) ne doit
        # jamais être affiché à l'utilisateur.
        diag_labels = dict(LearningDiagnosis.TYPE_CHOICES)
        difficultes = [
            {
                'label': d['competence__libelle'] or diag_labels.get(
                    d['diagnosis_type'], d['diagnosis_type']
                ),
                'n': d['n'],
            }
            for d in top_diag
        ]

        # Apprenants à surveiller (risque élevé ou diagnostic P1)
        p1_ids = set(diags.filter(priority=1).values_list('apprenant_id', flat=True))
        eleve_ids = set(rk.filter(risk_level='eleve').values_list('apprenant_id', flat=True))
        surveiller_ids = list(p1_ids | eleve_ids)[:50]
        surveiller = []
        for aid in surveiller_ids:
            st = ls.filter(apprenant_id=aid).first()
            r = rk.filter(apprenant_id=aid).first()
            e = en.filter(apprenant_id=aid).first()
            appr = appr_qs.filter(pk=aid).first()
            if appr:
                surveiller.append({
                    'apprenant_id': aid,
                    'nom': f"{getattr(appr, 'prenom', '')} {getattr(appr, 'nom', '')}".strip(),
                    'progress_pct': st.global_progress_pct if st else 0,
                    'mastery': st.avg_mastery if st else 0,
                    'eng_level': e.niveau if e else None,
                    'risk_level': r.risk_level if r else None,
                    'risk_score': r.risk_score if r else None,
                })

        return Response({
            'total_apprenants': total,
            'mastery': mastery,
            'engagement': engagement,
            'risk': risk,
            'difficultes': difficultes,
            'apprenants_a_surveiller': surveiller,
        })


class BlocAideView(APIView):
    """
    GET /api/v1/analytics/blocs/<bloc_id>/aide/
    Aide pédagogique CONTEXTUELLE du bloc, accessible à tout moment.

    Règles :
      - Un contenu DÉJÀ proposé et NON consommé → on le propose (« Voir le contenu »).
      - Un contenu déjà CONSOMMÉ → on ne le re-propose pas ; si la difficulté
        persiste, on peut générer une NOUVELLE version (même bloc).
      - Pas de contenu → « Générer une aide ».
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, bloc_id):
        from courses.models import BlocContenu
        from .models import (
            ContenuGenere, QuizGenereClaude, KnowledgeGap, SkillMasteryScore,
            AIAnalysisRequest,
        )
        from django.utils import timezone
        from datetime import timedelta

        apprenant = _get_apprenant(request)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        bloc = get_object_or_404(
            BlocContenu.objects.select_related('sequence__module__cours'), pk=bloc_id,
        )
        seq = bloc.sequence

        contenus_bloc = list(
            ContenuGenere.objects.filter(apprenant=apprenant, bloc_source=bloc)
            .order_by('-created_at')
        )
        contenus_seq = list(
            ContenuGenere.objects.filter(apprenant=apprenant, sequence_source=seq)
            .order_by('-created_at')
        )
        contenus = contenus_bloc or contenus_seq

        quiz = (
            QuizGenereClaude.objects.filter(apprenant=apprenant, quiz_source__sequence=seq)
            .order_by('-created_at').first()
        )

        difficulte_brute = (
            KnowledgeGap.objects.filter(
                apprenant=apprenant, sequence=seq, statut__in=['detectee', 'en_cours'],
            ).exists()
            or SkillMasteryScore.objects.filter(
                apprenant=apprenant, sequence=seq, niveau='fragile',
            ).exists()
        )

        # ✅ Un bloc TERMINÉ (explicitement) ne fait plus l'objet d'une aide.
        from courses.parcours_engine import bloc_termine_pour
        bloc_valide = bloc_termine_pour(apprenant, bloc)

        # ── Condition TEMPS : temps passé / temps estimé ─────────────────────
        from .models import BlocAnalyticsSummary
        summ = BlocAnalyticsSummary.objects.filter(apprenant=apprenant, bloc=bloc).first()
        est_sec = (bloc.duree_estimee_minutes or 0) * 60
        duree_sec = (summ.duree_totale_sec if summ else 0) or 0
        ratio_pct = round((duree_sec / est_sec) * 100) if est_sec else 0
        seuil_depasse = (ratio_pct >= SEUIL_AIDE) and not bloc_valide

        reponse = summ.aide_check_reponse if summ else None

        # Avant de proposer quoi que ce soit : poser LA question d'auto-évaluation.
        question = None
        if seuil_depasse and reponse is None:
            question = {
                'texte': (
                    "Avez-vous besoin d'aide sur cette partie ? "
                    "Êtes-vous bloqué(e), ou ne comprenez-vous pas ce contenu ?"
                ),
                'reponse': None,
            }

        # On ne propose/génère un contenu QUE si l'apprenant a répondu « oui »,
        # ou si le seuil de temps n'est pas encore atteint (demande manuelle).
        consentement_ok = (reponse is True)
        autorise = (not seuil_depasse) or consentement_ok
        difficulte = difficulte_brute and autorise and not bloc_valide

        # État de génération : une demande récente est-elle en cours / en erreur ?
        en_cours = AIAnalysisRequest.objects.filter(
            apprenant=apprenant, bloc=bloc, status='pending',
            created_at__gte=timezone.now() - timedelta(minutes=10),
        ).exists()
        derniere = (
            AIAnalysisRequest.objects.filter(apprenant=apprenant, bloc=bloc)
            .order_by('-created_at').first()
        )
        derniere_erreur = (
            derniere.error_message
            if (derniere and derniere.status == 'error') else None
        )

        a_contenu = bool(contenus)
        # Le contenu reste ACCESSIBLE à tout moment ; on ne fait que marquer le plus
        # récent comme « nouveau » (badge) tant qu'il n'a pas été ouvert.
        non_consulte = next((c for c in contenus if not c.a_ete_consulte), None)
        # Nouvelle version autorisée si consentement + (difficulté ou aucune aide).
        peut_generer = autorise and (difficulte or not a_contenu) and not en_cours and not bloc_valide
        contenus_payload = [
            {
                'id': c.pk,
                'titre': c.titre,
                'type': c.type_contenu,
                'consulte': c.a_ete_consulte,
                'nouveau': (non_consulte is not None and c.pk == non_consulte.pk),
            }
            for c in contenus[:10]
        ]

        quiz_payload = None
        if quiz and not quiz.passe_le:
            quiz_payload = {'id': quiz.pk, 'titre': quiz.titre,
                            'consulte': quiz.a_ete_consulte, 'passe': bool(quiz.passe_le)}

        return Response({
            'bloc_id':      bloc.pk,
            'sequence_id':  seq.pk,
            'cours_id':     bloc.sequence.module.cours_id,
            'bloc_titre':   bloc.titre,
            'type_bloc':    bloc.type_bloc,
            'difficulte':   difficulte,
            'bloc_valide':  bloc_valide,
            'deja_propose': a_contenu,
            'contenus':     contenus_payload,
            # Compat : plus récent non consommé (bouton « Voir le contenu » mis en avant)
            'contenu':     (contenus_payload[0] if contenus_payload else None),
            'quiz':         quiz_payload,
            'peut_generer': peut_generer,
            'generation_en_cours': en_cours,
            'derniere_erreur': derniere_erreur,
            'question':     question,
            'reponse_aide': reponse,
            'ratio_pct':    ratio_pct,
            'seuil_aide':   SEUIL_AIDE,
            'seuil_depasse': seuil_depasse,
        })


class BlocGenererView(APIView):
    """
    POST /api/v1/analytics/blocs/<bloc_id>/generer/
    Génère une aide pour ce bloc (anti-doublon + nouvelle version si difficulté).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, bloc_id):
        from courses.models import BlocContenu
        from .models import ContenuGenere

        apprenant = _get_apprenant(request)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        bloc = get_object_or_404(
            BlocContenu.objects.select_related('sequence__module__cours'), pk=bloc_id,
        )

        # ✅ Bloc déjà terminé (explicitement) → plus de proposition d'aide.
        from courses.parcours_engine import bloc_termine_pour
        if bloc_termine_pour(apprenant, bloc):
            return Response(
                {'status': 'termine', 'message': 'Ce bloc est terminé — plus d’aide nécessaire.'},
                status=200,
            )

        # Anti-doublon : un contenu non consommé existe → on ne régénère pas.
        dernier = (
            ContenuGenere.objects.filter(apprenant=apprenant, bloc_source=bloc)
            .order_by('-created_at').first()
        )
        if dernier and not dernier.a_ete_consulte:
            return Response({'status': 'deja_propose', 'contenu_id': dernier.pk}, status=200)

        # Contexte du bloc (réutilise l'extraction de texte de views)
        from .views import _get_bloc_texte
        from .models import AIAnalysisRequest
        from django.utils import timezone
        from datetime import timedelta

        # Une génération est déjà en cours → on ne double pas (Ollama = 1 slot).
        if AIAnalysisRequest.objects.filter(
            apprenant=apprenant, status='pending',
            created_at__gte=timezone.now() - timedelta(minutes=10),
        ).exists():
            return Response(
                {'status': 'en_cours', 'message': 'Une génération est déjà en cours…'},
                status=200,
            )

        seq = bloc.sequence
        mod = getattr(seq, 'module', None)
        crs = getattr(mod, 'cours', None) if mod else None
        variante = ContenuGenere.objects.filter(apprenant=apprenant, bloc_source=bloc).count()
        context = {
            'bloc_titre':        bloc.titre,
            'bloc_contenu':      _get_bloc_texte(bloc),
            'duree_estimee_min': (bloc.duree_estimee_minutes or 0),
            'duree_passee_min':  0,
            'ratio_pct':         0,
            'nb_ouvertures':     variante + 1,
            'scroll_max_pct':    0,
            'cours_titre':       crs.titre if crs else '',
            'sequence_titre':    seq.titre,
            'variation':         variante,  # 0 = première aide ; >0 = proposer un autre angle
        }

        from .signals import _creer_requete_ia
        req = _creer_requete_ia(
            apprenant, 'multi_reouverture', force=True,
            prompt_context=context,
            bloc=bloc, sequence=seq, module=mod, cours=crs,
        )
        if req is None:
            return Response(
                {'status': 'doublon', 'message': 'Une aide a déjà été demandée récemment.'},
                status=200,
            )
        return Response(
            {'status': 'pending', 'request_id': req.pk, 'message': 'Génération en cours…'},
            status=202,
        )


class BlocAideReponseView(APIView):
    """
    POST /api/v1/analytics/blocs/<bloc_id>/reponse-aide/
    Enregistre la réponse à « Êtes-vous bloqué ? » :
      - bloque=true  → enregistre « oui » puis lance la génération d'aide ;
      - bloque=false → enregistre « non » (on ne proposera plus de contenu).
    Body : { "bloque": true|false }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, bloc_id):
        from courses.models import BlocContenu
        from .models import BlocAnalyticsSummary
        from django.utils import timezone

        apprenant = _get_apprenant(request)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        bloc = get_object_or_404(
            BlocContenu.objects.select_related('sequence__module__cours'), pk=bloc_id,
        )

        bloque = request.data.get('bloque')
        if bloque is None:
            return Response({'error': 'champ "bloque" requis'}, status=400)
        bloque = bool(bloque)

        summ, _ = BlocAnalyticsSummary.objects.get_or_create(
            apprenant=apprenant, bloc=bloc,
            defaults={
                'sequence': bloc.sequence,
                'module':   bloc.sequence.module,
                'cours':    bloc.sequence.module.cours,
            },
        )
        summ.aide_check_reponse = bloque
        summ.aide_check_le = timezone.now()
        summ.save(update_fields=['aide_check_reponse', 'aide_check_le'])

        if not bloque:
            return Response({'status': 'ok', 'reponse': False,
                             'message': "D'accord, aucune aide ne sera proposée."})

        # « Oui » → on délègue à la génération (mêmes garde-fous : bloc terminé,
        # anti-doublon, anti-flood).
        return BlocGenererView().post(request, bloc_id)


class RecommendationsView(APIView):
    """
    GET /api/analytics/recommendations/<apprenant_id>/
    Paramètres optionnels : ?cours_id=<int>&max=<int>
    Retourne la liste ordonnée des séquences recommandées à retravailler.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        cours = None
        cours_id = request.query_params.get('cours_id')
        if cours_id:
            try:
                from courses.models import Cours
                cours = Cours.objects.get(pk=cours_id)
            except Exception:
                pass

        max_results = min(int(request.query_params.get('max', 5)), 20)

        from .recommendation_engine import get_recommendations
        recs = get_recommendations(apprenant, cours=cours, max_results=max_results)
        return Response({'recommendations': recs, 'total': len(recs)})
