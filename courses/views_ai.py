# courses/views_ai.py
# ============================================================================
# VUES IA — Endpoints pour la génération de contenu adaptatif via Claude
# ============================================================================

import logging
import threading
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS — depuis analytics
# ══════════════════════════════════════════════════════════════════════════════

from analytics.views import _get_apprenant
from analytics.models import (
    AIAnalysisRequest,
    ContenuGenere,
    QuizGenereClaude,
)
from analytics.services.ai_claude_service import traiter_demande_ai


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_bloc_contenu_texte(bloc) -> str:
    """Extrait le texte brut d'un BlocContenu."""
    if not bloc:
        return ''
    import re
    parts = []
    for field in ('contenu_html', 'contenu_texte', 'contenu_markdown', 'code_source'):
        val = getattr(bloc, field, None)
        if val:
            clean = re.sub(r'<[^>]+>', ' ', str(val))
            parts.append(clean.strip())
    return '\n'.join(parts)[:3000]


def _run_in_thread(ai_request_id: int):
    """Lance le traitement Claude dans un thread."""
    def _worker():
        try:
            from analytics.views import _creer_contenu_genere
            req = AIAnalysisRequest.objects.get(pk=ai_request_id)
            traiter_demande_ai(req)
            _creer_contenu_genere(req)
        except Exception as e:
            logger.error('[views_ai] Erreur thread AI : %s', e)
    threading.Thread(target=_worker, daemon=True).start()


def _recently_generated(apprenant, trigger: str, hours: int = 2, **filters) -> bool:
    """True si une génération identique récente existe."""
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=hours)
    qs = AIAnalysisRequest.objects.filter(
        apprenant=apprenant, trigger=trigger,
        status__in=['pending', 'success'],
        created_at__gte=cutoff,
        **filters,
    )
    return qs.exists()


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/ai/analyze/
# ══════════════════════════════════════════════════════════════════════════════

class AIAnalyzeView(APIView):
    """
    POST /api/ai/analyze/

    Body :
    {
      "trigger": "temps_long" | "quiz_rate",
      "apprenant_id": 42,

      "bloc_id": 15,
      "duree_passee_sec": 720,
      "duree_estimee_sec": 300,
      "scroll_max_pct": 45,
      "nb_ouvertures": 3,

      "quiz_id": 8,
      "score_obtenu": 35,
      "nb_tentatives": 2,
      "questions_ratees": [...]
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        trigger = request.data.get('trigger')
        if trigger not in ('temps_long', 'quiz_rate'):
            return Response({'error': f'Trigger invalide'}, status=400)

        if trigger == 'temps_long':
            return self._handle_bloc_trigger(request, apprenant)
        elif trigger == 'quiz_rate':
            return self._handle_quiz_trigger(request, apprenant)

    def _handle_bloc_trigger(self, request, apprenant):
        bloc_id = request.data.get('bloc_id')
        if not bloc_id:
            return Response({'error': 'bloc_id requis'}, status=400)
        try:
            from .models import BlocContenu
            bloc = BlocContenu.objects.select_related(
                'sequence__module__cours'
            ).get(pk=bloc_id)
        except Exception:
            return Response({'error': f'Bloc {bloc_id} introuvable'}, status=404)

        if _recently_generated(apprenant, 'temps_long', bloc_id=bloc_id):
            return Response({
                'request_id': None, 'status': 'skipped',
                'message': 'Suggestion récente déjà faite.',
            }, status=200)

        duree_passee_sec = int(request.data.get('duree_passee_sec', 0))
        duree_estimee_sec = int(request.data.get('duree_estimee_sec', 0)) or (
            getattr(bloc, 'duree_estimee_minutes', 0) or 0
        ) * 60 or 300

        seq = getattr(bloc, 'sequence', None)
        mod = getattr(seq, 'module', None) if seq else None
        crs = getattr(mod, 'cours', None) if mod else None

        context = {
            'bloc_titre': bloc.titre,
            'bloc_contenu': _get_bloc_contenu_texte(bloc),
            'duree_estimee_min': round(duree_estimee_sec / 60, 1),
            'duree_passee_min': round(duree_passee_sec / 60, 1),
            'ratio_pct': round((duree_passee_sec / duree_estimee_sec) * 100) if duree_estimee_sec else 0,
            'nb_ouvertures': int(request.data.get('nb_ouvertures', 1)),
            'scroll_max_pct': int(request.data.get('scroll_max_pct', 0)),
            'cours_titre': crs.titre if crs else '',
            'sequence_titre': seq.titre if seq else '',
        }

        ai_req = AIAnalysisRequest.objects.create(
            apprenant=apprenant, bloc=bloc,
            sequence=seq, module=mod, cours=crs,
            trigger='temps_long', prompt_context=context,
        )

        _run_in_thread(ai_req.pk)
        logger.info('[ai] trigger=temps_long apprenant=%s', apprenant.pk)
        return Response({
            'request_id': ai_req.pk, 'status': 'pending',
            'message': 'Génération en cours...',
        }, status=202)

    def _handle_quiz_trigger(self, request, apprenant):
        quiz_id = request.data.get('quiz_id')
        if not quiz_id:
            return Response({'error': 'quiz_id requis'}, status=400)
        try:
            from evaluations.models import Quiz
            quiz = Quiz.objects.select_related(
                'sequence__module__cours'
            ).get(pk=quiz_id)
        except Exception:
            return Response({'error': f'Quiz {quiz_id} introuvable'}, status=404)

        if _recently_generated(apprenant, 'quiz_rate', quiz_id=quiz_id, hours=4):
            return Response({
                'request_id': None, 'status': 'skipped',
                'message': 'Quiz de remédiation déjà généré.',
            }, status=200)

        seq = getattr(quiz, 'sequence', None)
        mod = getattr(seq, 'module', None) if seq else None
        crs = getattr(mod, 'cours', None) if mod else None

        context = {
            'quiz_titre': quiz.titre,
            'quiz_description': getattr(quiz, 'description', '') or '',
            'score_obtenu': int(request.data.get('score_obtenu', 0)),
            'nb_tentatives': int(request.data.get('nb_tentatives', 1)),
            'questions_ratees': request.data.get('questions_ratees', []),
            'cours_titre': crs.titre if crs else '',
            'sequence_titre': seq.titre if seq else '',
        }

        ai_req = AIAnalysisRequest.objects.create(
            apprenant=apprenant, quiz=quiz,
            sequence=seq, module=mod, cours=crs,
            trigger='quiz_rate', prompt_context=context,
        )

        _run_in_thread(ai_req.pk)
        logger.info('[ai] trigger=quiz_rate apprenant=%s', apprenant.pk)
        return Response({
            'request_id': ai_req.pk, 'status': 'pending',
            'message': 'Génération en cours...',
        }, status=202)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/ai/suggestions/<appr_id>/
# ══════════════════════════════════════════════════════════════════════════════

class AISuggestionsView(APIView):
    """
    GET /api/ai/suggestions/<int:apprenant_id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        return Response({
            'contenus': [
                _contenu_dict(c) for c in ContenuGenere.objects.filter(
                    apprenant=apprenant
                ).select_related('bloc_source', 'sequence_source')
            ],
            'quizs': [
                _quiz_dict(q) for q in QuizGenereClaude.objects.filter(
                    apprenant=apprenant
                ).select_related('quiz_source')
            ],
            'pending_count': AIAnalysisRequest.objects.filter(
                apprenant=apprenant, status='pending'
            ).count(),
        })


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /contenu/<pk>/consulte/
# ══════════════════════════════════════════════════════════════════════════════

class BlocGenereConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        obj = get_object_or_404(ContenuGenere, pk=pk, apprenant=apprenant)
        obj.marquer_consulte()
        return Response({'status': 'ok'})


class BlocGenereFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        obj = get_object_or_404(ContenuGenere, pk=pk, apprenant=apprenant)
        a_aide = request.data.get('a_aide')
        if a_aide is None:
            return Response({'error': 'a_aide requis'}, status=400)
        obj.soumettre_feedback(bool(a_aide))
        return Response({'status': 'ok'})


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /quiz-genere/<pk>/consulte/
# POST  /quiz-genere/<pk>/score/
# ══════════════════════════════════════════════════════════════════════════════

class QuizGenereConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        obj = get_object_or_404(QuizGenereClaude, pk=pk, apprenant=apprenant)
        obj.marquer_consulte()
        return Response({'status': 'ok'})


class QuizGenereScoreView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        apprenant = _get_apprenant(request)
        obj = get_object_or_404(QuizGenereClaude, pk=pk, apprenant=apprenant)
        score = request.data.get('score')
        if score is None:
            return Response({'error': 'score requis (0-100)'}, status=400)
        obj.soumettre_score(int(score))
        return Response({
            'status': 'ok',
            'remediation_reussie': obj.remediation_reussie,
            'score': obj.score_remediation,
        })


# ══════════════════════════════════════════════════════════════════════════════
# SÉRIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _dt(v):
    return v.isoformat() if v else None


def _contenu_dict(c):
    return {
        'id': c.pk,
        'type_contenu': c.type_contenu,
        'titre': c.titre,
        'description': c.description,
        'contenu_html': c.contenu_html,
        'contenu_json': c.contenu_json,
        'bloc_source_id': c.bloc_source_id,
        'sequence_source_id': c.sequence_source_id,
        'module_source_id': c.module_source_id,
        'quiz_source_id': c.quiz_source_id,
        'concepts_cibles': c.concepts_cibles,
        'niveau_difficulte': c.niveau_difficulte,
        'a_ete_consulte': c.a_ete_consulte,
        'a_aide': c.a_aide,
        'created_at': _dt(c.created_at),
    }


def _quiz_dict(q):
    return {
        'id': q.pk,
        'quiz_source_id': q.quiz_source_id,
        'titre': q.titre,
        'consigne': q.consigne,
        'questions': q.questions,
        'concepts_rates': q.concepts_rates,
        'score_remediation': q.score_remediation,
        'remediation_reussie': q.remediation_reussie,
        'a_ete_consulte': q.a_ete_consulte,
        'created_at': _dt(q.created_at),
    }