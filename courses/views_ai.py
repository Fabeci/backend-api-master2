# courses/views_ai.py
# ============================================================================
# VUES IA — Endpoints pour la génération de contenu adaptatif via ChatGPT
#
# Endpoints :
#   POST /api/ai/analyze/              → analyse + génération en tâche de fond
#   GET  /api/ai/suggestions/<appr_id>/  → récupère suggestions non consultées
#   PATCH /api/ai/bloc-genere/<pk>/consulte/  → marque comme consulté
#   PATCH /api/ai/bloc-genere/<pk>/feedback/  → enregistre le feedback
#   PATCH /api/ai/quiz-genere/<pk>/consulte/  → marque comme consulté
#   POST  /api/ai/quiz-genere/<pk>/score/     → soumet le score de remédiation
# ============================================================================

import logging
import threading
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from analytics.views import _get_apprenant

from .models_ai import AIAnalysisRequest, BlocGenere, QuizGenere
from .ai_service import traiter_demande_ai

# Import helpers depuis views_analytics pour réutiliser _get_apprenant

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_bloc_contenu_texte(bloc) -> str:
    """Extrait le texte brut d'un BlocContenu pour le passer à GPT."""
    if not bloc:
        return ''
    parts = []
    for field in ('contenu_html', 'contenu_texte', 'contenu_markdown', 'code_source'):
        val = getattr(bloc, field, None)
        if val:
            # Retirer les balises HTML basiques
            import re
            clean = re.sub(r'<[^>]+>', ' ', str(val))
            parts.append(clean.strip())
    return '\n'.join(parts)[:3000]


def _run_in_thread(ai_request_id: int):
    """Lance le traitement GPT dans un thread pour ne pas bloquer la réponse HTTP."""
    def _worker():
        try:
            req = AIAnalysisRequest.objects.get(pk=ai_request_id)
            traiter_demande_ai(req)
        except Exception as e:
            logger.error('[views_ai] Erreur thread AI : %s', e)
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def _recently_generated(apprenant, trigger: str, bloc=None, quiz=None, hours: int = 2) -> bool:
    """
    Retourne True si une génération identique a déjà été faite récemment.
    Évite de spammer GPT si l'apprenant reste longtemps sur le même bloc.
    """
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=hours)
    qs = AIAnalysisRequest.objects.filter(
        apprenant=apprenant,
        trigger=trigger,
        status__in=['pending', 'success'],
        created_at__gte=cutoff,
    )
    if bloc:
        qs = qs.filter(bloc=bloc)
    if quiz:
        qs = qs.filter(quiz=quiz)
    return qs.exists()


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/ai/analyze/
# Déclenché par le frontend quand un trigger est détecté.
# ══════════════════════════════════════════════════════════════════════════════

class AIAnalyzeView(APIView):
    """
    POST /api/ai/analyze/

    Body :
    {
      "trigger": "temps_long" | "quiz_rate",
      "apprenant_id": 42,            // optionnel, déduit du token sinon

      // Pour trigger = temps_long :
      "bloc_id": 15,
      "duree_passee_sec": 720,
      "duree_estimee_sec": 300,
      "scroll_max_pct": 45,
      "nb_ouvertures": 3,

      // Pour trigger = quiz_rate :
      "quiz_id": 8,
      "score_obtenu": 35,
      "nb_tentatives": 2,
      "questions_ratees": [
        {
          "question": "Qu'est-ce que X ?",
          "bonne_reponse": "Y",
          "reponse_apprenant": "Z",
          "explication": "..."
        }
      ]
    }

    Retourne :
    { "request_id": 123, "status": "pending", "message": "Génération en cours..." }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        trigger = request.data.get('trigger')
        if trigger not in ('temps_long', 'quiz_rate'):
            return Response({'error': f'Trigger invalide : {trigger}'}, status=400)

        # ── Trigger : temps_long ──────────────────────────────────────────
        if trigger == 'temps_long':
            bloc_id = request.data.get('bloc_id')
            if not bloc_id:
                return Response({'error': 'bloc_id requis'}, status=400)

            try:
                from .models import BlocContenu
                bloc = BlocContenu.objects.select_related('sequence__module__cours').get(pk=bloc_id)
            except BlocContenu.DoesNotExist:
                return Response({'error': f'BlocContenu {bloc_id} introuvable'}, status=404)
            except Exception as e:
                return Response({'error': f'Erreur BlocContenu: {e}'}, status=404)

            # Anti-doublon : pas de re-génération dans les 2h
            if _recently_generated(apprenant, 'temps_long', bloc=bloc):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
                    'message': 'Une suggestion a déjà été générée récemment pour ce bloc.',
                }, status=200)

            duree_passee_sec  = int(request.data.get('duree_passee_sec', 0))
            duree_estimee_sec = int(request.data.get('duree_estimee_sec', 0)) or getattr(bloc, 'duree_estimee_minutes', 0) * 60 or 300

            seq  = getattr(bloc, 'sequence', None)
            mod  = getattr(seq, 'module', None) if seq else None
            crs  = getattr(mod, 'cours',  None) if mod else None

            context = {
                'bloc_titre':        bloc.titre,
                'bloc_contenu':      _get_bloc_contenu_texte(bloc),
                'duree_estimee_min': round(duree_estimee_sec / 60, 1),
                'duree_passee_min':  round(duree_passee_sec  / 60, 1),
                'ratio_pct':         round((duree_passee_sec / duree_estimee_sec) * 100) if duree_estimee_sec else 0,
                'nb_ouvertures':     int(request.data.get('nb_ouvertures', 1)),
                'scroll_max_pct':    int(request.data.get('scroll_max_pct', 0)),
                'cours_titre':       crs.titre   if crs else '',
                'sequence_titre':    seq.titre   if seq else '',
            }

            ai_req = AIAnalysisRequest.objects.create(
                apprenant      = apprenant,
                bloc           = bloc,
                sequence       = seq,
                cours          = crs,
                trigger        = 'temps_long',
                prompt_context = context,
            )

        # ── Trigger : quiz_rate ───────────────────────────────────────────
        elif trigger == 'quiz_rate':
            quiz_id = request.data.get('quiz_id')
            if not quiz_id:
                return Response({'error': 'quiz_id requis'}, status=400)

            try:
                from django.apps import apps
                # Cherche le modèle Quiz dans toutes les apps installées
                Quiz = None
                for app_label in ('evaluations', 'courses', 'quizz'):
                    try:
                        Quiz = apps.get_model(app_label, 'Quiz')
                        break
                    except LookupError:
                        continue
                if Quiz is None:
                    raise Exception('Modèle Quiz introuvable dans les apps installées')
                quiz = Quiz.objects.select_related('sequence__module__cours').get(pk=quiz_id)
            except Quiz.DoesNotExist:
                return Response({'error': f'Quiz {quiz_id} introuvable'}, status=404)
            except Exception as e:
                logger.error('[ai/analyze] Erreur quiz lookup: %s', e)
                return Response({'error': f'Quiz {quiz_id} introuvable ({e})'}, status=404)

            if _recently_generated(apprenant, 'quiz_rate', quiz=quiz, hours=4):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
                    'message': 'Un quiz de remédiation a déjà été généré récemment.',
                }, status=200)

            seq = getattr(quiz, 'sequence', None)
            mod = getattr(seq, 'module', None) if seq else None
            crs = getattr(mod, 'cours',  None) if mod else None

            context = {
                'quiz_titre':      quiz.titre,
                'quiz_description':getattr(quiz, 'description', '') or '',
                'score_obtenu':    int(request.data.get('score_obtenu', 0)),
                'nb_tentatives':   int(request.data.get('nb_tentatives', 1)),
                'questions_ratees':request.data.get('questions_ratees', []),
                'cours_titre':     crs.titre if crs else '',
                'sequence_titre':  seq.titre if seq else '',
            }

            ai_req = AIAnalysisRequest.objects.create(
                apprenant      = apprenant,
                quiz           = quiz,
                sequence       = seq,
                cours          = crs,
                trigger        = 'quiz_rate',
                prompt_context = context,
            )

        # Lancer la génération en arrière-plan (ne bloque pas la réponse HTTP)
        _run_in_thread(ai_req.pk)

        logger.info('[ai/analyze] trigger=%s apprenant=%s request_id=%s', trigger, apprenant.pk, ai_req.pk)

        return Response({
            'request_id': ai_req.pk,
            'status':     'pending',
            'message':    'Génération en cours, votre contenu personnalisé sera disponible dans quelques secondes.',
        }, status=202)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/ai/suggestions/<apprenant_id>/
# Récupère toutes les suggestions IA disponibles pour un apprenant.
# ══════════════════════════════════════════════════════════════════════════════

class AISuggestionsView(APIView):
    """
    GET /api/ai/suggestions/<int:apprenant_id>/
    Optionnel : ?bloc_id=15 ou ?quiz_id=8 pour filtrer

    Retourne :
    {
      "blocs_generes": [...],
      "quiz_generes": [...],
      "pending_count": 2     // requêtes en cours de génération
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        bloc_id = request.query_params.get('bloc_id')
        quiz_id = request.query_params.get('quiz_id')

        # Blocs générés
        blocs_qs = BlocGenere.objects.filter(apprenant=apprenant).select_related('bloc_source')
        if bloc_id:
            blocs_qs = blocs_qs.filter(bloc_source_id=bloc_id)

        # Quiz générés
        quiz_qs = QuizGenere.objects.filter(apprenant=apprenant).select_related('quiz_source')
        if quiz_id:
            quiz_qs = quiz_qs.filter(quiz_source_id=quiz_id)

        # Requêtes en cours
        pending = AIAnalysisRequest.objects.filter(apprenant=apprenant, status='pending').count()

        return Response({
            'blocs_generes': [_bloc_genere_dict(b) for b in blocs_qs],
            'quiz_generes':  [_quiz_genere_dict(q) for q in quiz_qs],
            'pending_count': pending,
        })


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /api/ai/bloc-genere/<pk>/consulte/
# PATCH /api/ai/bloc-genere/<pk>/feedback/
# ══════════════════════════════════════════════════════════════════════════════

class BlocGenereConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        bloc = get_object_or_404(BlocGenere, pk=pk, apprenant=apprenant)
        bloc.marquer_consulte()
        return Response({'status': 'ok'})


class BlocGenereFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        bloc = get_object_or_404(BlocGenere, pk=pk, apprenant=apprenant)
        a_aide = request.data.get('a_aide')
        if a_aide is None:
            return Response({'error': 'a_aide requis (true/false)'}, status=400)
        bloc.soumettre_feedback(bool(a_aide))
        return Response({'status': 'ok'})


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /api/ai/quiz-genere/<pk>/consulte/
# POST  /api/ai/quiz-genere/<pk>/score/
# ══════════════════════════════════════════════════════════════════════════════

class QuizGenereConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        quiz = get_object_or_404(QuizGenere, pk=pk, apprenant=apprenant)
        quiz.marquer_consulte()
        return Response({'status': 'ok'})


class QuizGenereScoreView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        apprenant = _get_apprenant(request)
        quiz = get_object_or_404(QuizGenere, pk=pk, apprenant=apprenant)
        score = request.data.get('score')
        if score is None:
            return Response({'error': 'score requis (0-100)'}, status=400)
        quiz.soumettre_score(int(score))
        return Response({
            'status':               'ok',
            'remediation_reussie':  quiz.remediation_reussie,
            'score':                quiz.score_remediation,
        })


# ══════════════════════════════════════════════════════════════════════════════
# SÉRIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _dt(v):
    return v.isoformat() if v else None


def _bloc_genere_dict(b: BlocGenere) -> dict:
    return {
        'id':               b.pk,
        'bloc_source_id':   b.bloc_source_id,
        'type_generation':  b.type_generation,
        'titre':            b.titre,
        'contenu_html':     b.contenu_html,
        'concepts_cibles':  b.concepts_cibles,
        'a_aide':           b.a_aide,
        'a_ete_consulte':   b.a_ete_consulte,
        'created_at':       _dt(b.created_at),
    }


def _quiz_genere_dict(q: QuizGenere) -> dict:
    return {
        'id':                   q.pk,
        'quiz_source_id':       q.quiz_source_id,
        'titre':                q.titre,
        'consigne':             q.consigne,
        'concepts_rates':       q.concepts_rates,
        'questions':            q.questions,
        'score_remediation':    q.score_remediation,
        'remediation_reussie':  q.remediation_reussie,
        'a_ete_consulte':       q.a_ete_consulte,
        'created_at':           _dt(q.created_at),
    }