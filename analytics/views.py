# courses/views_analytics.py
# ============================================================================
# ANALYTICS VIEWS — 5 bugs corrigés (tables restaient vides)
#
# BUG 1 — URLs jamais enregistrées (étaient en commentaire)
#          → Voir courses/urls_analytics.py livré avec ce fichier
#
# BUG 2 — _get_apprenant() retournait None pour presque tous les projets
#          getattr(request.user, 'apprenant', None) suppose un related_name
#          exact. Fix : on essaie 5 chemins différents.
#
# BUG 3 — AttributeError silencieux sur sequence.module (peut être None)
#          → transaction rollback invisible, rien sauvé en base
#
# BUG 4 — Boucles Python N+1 dans _sync_*_summary → remplacées par agrégats SQL
#
# BUG 5 — Aucun log ni endpoint debug → impossible à diagnostiquer
#          → GET /api/analytics/debug/ ajouté (désactiver en prod)
# ============================================================================

import logging
import threading
from django.utils import timezone
from django.db.models import Sum, Count, Max, Min, Q
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from courses.models import BlocContenu, Sequence

from .models import (
    BlocAnalytics, BlocAnalyticsSummary,
    SequenceAnalyticsSummary, ModuleAnalyticsSummary,
    AIAnalysisRequest, ContenuGenere, QuizGenereClaude,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HELPER — résolution de l'apprenant (BUG 2)
# ══════════════════════════════════════════════════════════════════════════════

def _get_apprenant(request, apprenant_id=None):
    """
    Résout l'objet Apprenant en testant plusieurs chemins dans l'ordre.
    Appeler GET /api/analytics/debug/ pour voir quel chemin fonctionne
    dans votre projet.
    """
    # Chemin 0 : id explicite passé dans le body du POST
    if apprenant_id:
        try:
            from users.models import Apprenant
            obj = Apprenant.objects.filter(pk=apprenant_id).first()
            if obj:
                return obj
        except Exception:
            pass

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return None

    # Chemins 1-4 : attributs directs sur user
    for attr in ('apprenant', 'profil', 'apprenant_profil', 'apprenant_account'):
        obj = getattr(user, attr, None)
        if obj is not None:
            return obj

    # Chemin 5 : requête inverse générique
    try:
        from users.models import Apprenant
        return Apprenant.objects.filter(user=user).first()
    except Exception:
        pass

    return None


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — synchronisation cascade (BUG 3 & 4)
# ══════════════════════════════════════════════════════════════════════════════

def _sync_sequence_summary(apprenant, sequence):
    if sequence is None:
        return None

    module = getattr(sequence, 'module', None)        # BUG 3 : sécurisé
    cours  = getattr(module, 'cours', None) if module else None

    blocs = BlocContenu.objects.filter(sequence=sequence)

    # BUG 4 : agrégat SQL unique au lieu d'une boucle Python
    agg = BlocAnalyticsSummary.objects.filter(
        apprenant=apprenant, sequence=sequence
    ).aggregate(
        nb_consultes = Count('id'),
        nb_completes = Count('id', filter=Q(nb_completions__gt=0)),
        duree_totale = Sum('duree_totale_sec'),
        prem_ouv     = Min('premiere_ouverture'),
        dern_ouv     = Max('derniere_ouverture'),
    )

    duree_estimee = sum((getattr(b, 'duree_estimee_minutes', 0) or 0) * 60 for b in blocs)
    duree_totale  = agg['duree_totale'] or 0
    ratio = round((duree_totale / duree_estimee) * 100) if duree_estimee else 0

    obj, _ = SequenceAnalyticsSummary.objects.get_or_create(
        apprenant=apprenant, sequence=sequence,
        defaults={'module': module, 'cours': cours},
    )
    obj.nb_blocs_total     = blocs.count()
    obj.nb_blocs_consultes = agg['nb_consultes'] or 0
    obj.nb_blocs_completes = agg['nb_completes'] or 0
    obj.duree_totale_sec   = duree_totale
    obj.duree_estimee_sec  = duree_estimee
    obj.ratio_temps_pct    = ratio
    if agg['prem_ouv']: obj.premiere_activite = agg['prem_ouv']
    if agg['dern_ouv']: obj.derniere_activite  = agg['dern_ouv']
    obj.save()
    return obj


def _sync_module_summary(apprenant, module):
    if module is None:
        return None

    cours = getattr(module, 'cours', None)

    agg = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, module=module
    ).aggregate(
        nb_consultees      = Count('id'),
        nb_completes       = Count('id', filter=Q(completee_le__isnull=False)),
        nb_blocs_total     = Sum('nb_blocs_total'),
        nb_blocs_completes = Sum('nb_blocs_completes'),
        duree_totale       = Sum('duree_totale_sec'),
        duree_estimee      = Sum('duree_estimee_sec'),
        prem_act           = Min('premiere_activite'),
        dern_act           = Max('derniere_activite'),
    )

    duree_totale  = agg['duree_totale']  or 0
    duree_estimee = agg['duree_estimee'] or 0
    ratio = round((duree_totale / duree_estimee) * 100) if duree_estimee else 0

    obj, _ = ModuleAnalyticsSummary.objects.get_or_create(
        apprenant=apprenant, module=module,
        defaults={'cours': cours},
    )
    obj.nb_sequences_total      = Sequence.objects.filter(module=module).count()
    obj.nb_sequences_consultees = agg['nb_consultees']      or 0
    obj.nb_sequences_completes  = agg['nb_completes']       or 0
    obj.nb_blocs_total          = agg['nb_blocs_total']     or 0
    obj.nb_blocs_completes      = agg['nb_blocs_completes'] or 0
    obj.duree_totale_sec        = duree_totale
    obj.duree_estimee_sec       = duree_estimee
    obj.ratio_temps_pct         = ratio
    if agg['prem_act']: obj.premiere_activite = agg['prem_act']
    if agg['dern_act']: obj.derniere_activite  = agg['dern_act']
    obj.save()
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — sérialisation
# ══════════════════════════════════════════════════════════════════════════════

def _dt(v):
    return v.isoformat() if v else None


def _bloc_summary_dict(s):
    return {
        'bloc_id':            s.bloc_id,
        'nb_ouvertures':      s.nb_ouvertures,
        'nb_completions':     s.nb_completions,
        'duree_totale_sec':   s.duree_totale_sec,
        'duree_moy_sec':      s.duree_moy_sec,
        'ratio_temps_pct':    s.ratio_temps_pct,
        'scroll_max_pct':     s.scroll_max_pct,
        'premiere_ouverture': _dt(s.premiere_ouverture),
        'derniere_ouverture': _dt(s.derniere_ouverture),
        'date_completion':    _dt(s.date_completion),
    }


def _seq_summary_dict(s):
    return {
        'sequence_id':        s.sequence_id,
        'nb_blocs_consultes': s.nb_blocs_consultes,
        'nb_blocs_total':     s.nb_blocs_total,
        'nb_blocs_completes': s.nb_blocs_completes,
        'duree_totale_sec':   s.duree_totale_sec,
        'duree_estimee_sec':  s.duree_estimee_sec,
        'ratio_temps_pct':    s.ratio_temps_pct,
        'nb_quiz_passes':     s.nb_quiz_passes,
        'score_moyen_quiz':   s.score_moyen_quiz,
        'premiere_activite':  _dt(s.premiere_activite),
        'derniere_activite':  _dt(s.derniere_activite),
        'completee_le':       _dt(s.completee_le),
    }


def _mod_summary_dict(s):
    return {
        'module_id':                s.module_id,
        'nb_sequences_consultees':  s.nb_sequences_consultees,
        'nb_sequences_total':       s.nb_sequences_total,
        'nb_sequences_completes':   s.nb_sequences_completes,
        'nb_blocs_total':           s.nb_blocs_total,
        'nb_blocs_completes':       s.nb_blocs_completes,
        'duree_totale_sec':         s.duree_totale_sec,
        'duree_estimee_sec':        s.duree_estimee_sec,
        'ratio_temps_pct':          s.ratio_temps_pct,
        'score_moyen_quiz':         s.score_moyen_quiz,
        'premiere_activite':        _dt(s.premiere_activite),
        'derniere_activite':        _dt(s.derniere_activite),
        'complete_le':              _dt(s.complete_le),
    }


# ══════════════════════════════════════════════════════════════════════════════
# VUE DIAGNOSTIC — BUG 5 corrigé
# GET /api/analytics/debug/  →  à désactiver en production
# ══════════════════════════════════════════════════════════════════════════════

class AnalyticsDebugView(APIView):
    """
    GET /api/analytics/debug/
    Ouvrir dans le navigateur (user connecté) pour voir pourquoi les tables
    sont vides. La clé 'apprenant_resolu' doit être non-null.
    Si elle est null, regarder 'chemins_testes' pour trouver le bon attribut
    et adapter _get_apprenant() en conséquence.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        apprenant = _get_apprenant(request)

        chemins = {}
        for attr in ('apprenant', 'profil', 'apprenant_profil', 'apprenant_account'):
            obj = getattr(user, attr, None)
            chemins[f'user.{attr}'] = repr(obj)

        try:
            from users.models import Apprenant
            qs = Apprenant.objects.filter(user=user)
            chemins['Apprenant.objects.filter(user=user)'] = (
                f'{qs.count()} résultat(s) — premier: {repr(qs.first())}'
            )
            total = Apprenant.objects.count()
        except Exception as e:
            chemins['Apprenant.objects.filter(user=user)'] = f'ERREUR: {e}'
            total = 'erreur'

        return Response({
            'user': {
                'pk':               user.pk,
                'username':         user.username,
                'is_authenticated': user.is_authenticated,
                'class':            type(user).__name__,
            },
            '⚠️ apprenant_resolu': repr(apprenant),
            'chemins_testes':       chemins,
            'total_apprenants_db':  total,
            'compteurs_tables': {
                'BlocAnalytics (sessions brutes)':      BlocAnalytics.objects.count(),
                'BlocAnalyticsSummary (résumés blocs)': BlocAnalyticsSummary.objects.count(),
                'SequenceAnalyticsSummary':             SequenceAnalyticsSummary.objects.count(),
                'ModuleAnalyticsSummary':               ModuleAnalyticsSummary.objects.count(),
            },
            'action_si_apprenant_null': (
                'Adapter _get_apprenant() dans views_analytics.py : '
                'remplacer le chemin qui retourne null par celui qui fonctionne '
                '(voir chemins_testes ci-dessus).'
            ),
        })


# ══════════════════════════════════════════════════════════════════════════════
# VUE OPEN
# POST /api/analytics/bloc/<int:bloc_id>/open/
# ══════════════════════════════════════════════════════════════════════════════

class BlocAnalyticsOpenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, bloc_id):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))

        if not apprenant:
            logger.warning(
                '[analytics/open] 403 apprenant introuvable — user=%s pk=%s — '
                'voir GET /api/analytics/debug/',
                getattr(request.user, 'username', '?'),
                getattr(request.user, 'pk', '?'),
            )
            return Response(
                {'error': 'Apprenant introuvable — voir GET /api/analytics/debug/'},
                status=status.HTTP_403_FORBIDDEN,
            )

        bloc = get_object_or_404(BlocContenu, pk=bloc_id)
        seq  = getattr(bloc, 'sequence', None)
        mod  = getattr(seq,  'module',   None) if seq  else None
        crs  = getattr(mod,  'cours',    None) if mod  else None

        session = BlocAnalytics.objects.create(
            apprenant=apprenant, bloc=bloc,
            sequence=seq, module=mod, cours=crs,
        )
        logger.info('[analytics/open] session %s — apprenant=%s bloc=%s', session.pk, apprenant.pk, bloc_id)
        return Response({'session_id': session.pk}, status=status.HTTP_201_CREATED)


# ══════════════════════════════════════════════════════════════════════════════
# VUE CLOSE
# PATCH /api/analytics/bloc/session/<int:session_id>/close/
# ══════════════════════════════════════════════════════════════════════════════

class BlocAnalyticsCloseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, session_id):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))

        if not apprenant:
            logger.warning('[analytics/close] 403 apprenant introuvable — user=%s', request.user)
            return Response(
                {'error': 'Apprenant introuvable — voir GET /api/analytics/debug/'},
                status=status.HTTP_403_FORBIDDEN,
            )

        session = get_object_or_404(BlocAnalytics, pk=session_id, apprenant=apprenant)

        session.clore(
            duree_sec  = int(request.data.get('duree_secondes', 0) or 0),
            scroll_pct = int(request.data.get('scroll_max_pct',  0) or 0),
            complete   = bool(request.data.get('complete', False)),
        )

        summary, _ = BlocAnalyticsSummary.objects.get_or_create(
            apprenant=apprenant, bloc=session.bloc,
            defaults={
                'sequence': session.sequence,
                'module':   session.module,
                'cours':    session.cours,
            },
        )
        summary.recalculer()

        if session.sequence:
            _sync_sequence_summary(apprenant, session.sequence)
        if session.module:
            _sync_module_summary(apprenant, session.module)

        logger.info(
            '[analytics/close] session %s clôturée — bloc=%s duree=%ss scroll=%s%% complete=%s',
            session_id, session.bloc_id,
            request.data.get('duree_secondes'),
            request.data.get('scroll_max_pct'),
            request.data.get('complete'),
        )
        return Response(_bloc_summary_dict(summary))


# ══════════════════════════════════════════════════════════════════════════════
# VUE BULK
# POST /api/analytics/bulk-summary/
# ══════════════════════════════════════════════════════════════════════════════

class BulkAnalyticsSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))

        if not apprenant:
            return Response({'blocs': [], 'sequences': [], 'modules': []})

        def safe_ids(key):
            return [int(x) for x in (request.data.get(key) or []) if str(x).strip().isdigit()]

        bloc_ids     = safe_ids('bloc_ids')
        sequence_ids = safe_ids('sequence_ids')
        module_ids   = safe_ids('module_ids')

        return Response({
            'blocs': [
                _bloc_summary_dict(s)
                for s in BlocAnalyticsSummary.objects.filter(
                    apprenant=apprenant, bloc_id__in=bloc_ids
                )
            ] if bloc_ids else [],
            'sequences': [
                _seq_summary_dict(s)
                for s in SequenceAnalyticsSummary.objects.filter(
                    apprenant=apprenant, sequence_id__in=sequence_ids
                )
            ] if sequence_ids else [],
            'modules': [
                _mod_summary_dict(s)
                for s in ModuleAnalyticsSummary.objects.filter(
                    apprenant=apprenant, module_id__in=module_ids
                )
            ] if module_ids else [],
        })


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS IA
# ══════════════════════════════════════════════════════════════════════════════

def _run_in_thread(ai_request_id: int):
    """Lance le traitement Claude dans un thread."""
    def _worker():
        try:
            req = AIAnalysisRequest.objects.get(pk=ai_request_id)
            from .services.ai_claude_service import traiter_demande_ai
            traiter_demande_ai(req)
            _creer_contenu_genere(req)
        except Exception as e:
            logger.error('[ai] Erreur thread : %s', e)
    threading.Thread(target=_worker, daemon=True).start()


def _creer_contenu_genere(ai_request):
    """Crée un ContenuGenere ou QuizGenereClaude après succès Claude."""
    from .models import ContenuGenere, QuizGenereClaude
    if ai_request.status != 'success':
        return

    try:
        import json
        data = json.loads(ai_request.gpt_response or '{}')
    except Exception:
        return

    if ai_request.trigger in ('temps_long', 'multi_reouverture'):
        ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='bloc_simplifie' if ai_request.trigger == 'temps_long' else 'bloc_alternatif',
            titre=data.get('titre', 'Explication simplifiée'),
            contenu_html=data.get('contenu_html', ''),
            contenu_json=data,
            bloc_source=ai_request.bloc,
            concepts_cibles=data.get('concepts_cibles', []),
        )
    elif ai_request.trigger in ('sequence_complexe',):
        ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='sequence_adaptative',
            titre=data.get('titre', 'Séquence adaptative'),
            description=data.get('description', ''),
            contenu_json=data,
            sequence_source=ai_request.sequence,
            concepts_cibles=data.get('etapes', []),
            niveau_difficulte=data.get('sequence_niveau', 'intermediaire'),
        )
    elif ai_request.trigger == 'module_difficile':
        ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='module_revision',
            titre=data.get('titre', 'Module de révision'),
            description=data.get('resume', ''),
            contenu_json=data,
            module_source=ai_request.module,
            concepts_cibles=data.get('competences_cibles', []),
            niveau_difficulte=data.get('sequence_niveau', 'intermediaire'),
        )
    elif ai_request.trigger == 'quiz_rate':
        QuizGenereClaude.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            quiz_source=ai_request.quiz,
            titre=data.get('titre', 'Quiz de remédiation'),
            consigne=data.get('consigne', ''),
            questions=data.get('questions', []),
            concepts_rates=data.get('concepts_rates', []),
        )


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
# HELPERS SÉRIALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _dt(v):
    return v.isoformat() if v else None


def _contenu_genere_dict(c):
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


def _quiz_genere_dict(q):
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


def _get_bloc_texte(bloc) -> str:
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


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/ai/generate-content/ — Génération IA à la demande
# ══════════════════════════════════════════════════════════════════════════════

import threading

class AIGenerateContentView(APIView):
    """
    POST /api/analytics/ai/generate-content/

    Body :
    {
      "trigger": "temps_long" | "multi_reouverture" | "quiz_rate"
              | "sequence_complexe" | "module_difficile",
      "apprenant_id": 42,             // optionnel, déduit du token

      // Pour temps_long / multi_reouverture :
      "bloc_id": 15,
      "duree_passee_sec": 720,
      "duree_estimee_sec": 300,
      "scroll_max_pct": 45,
      "nb_ouvertures": 3,

      // Pour quiz_rate :
      "quiz_id": 8,
      "score_obtenu": 35,
      "nb_tentatives": 2,
      "questions_ratees": [{"question": "...", "bonne_reponse": "..."}]

      // Pour sequence_complexe :
      "sequence_id": 5,

      // Pour module_difficile :
      "module_id": 3,
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        trigger = request.data.get('trigger')
        valid_triggers = ('temps_long', 'multi_reouverture', 'quiz_rate',
                        'sequence_complexe', 'module_difficile')
        if trigger not in valid_triggers:
            return Response({'error': f'Trigger invalide'}, status=400)

        # ── Bloc triggers ──────────────────────────────────────────────
        if trigger in ('temps_long', 'multi_reouverture'):
            bloc_id = request.data.get('bloc_id')
            if not bloc_id:
                return Response({'error': 'bloc_id requis'}, status=400)
            try:
                bloc = BlocContenu.objects.select_related(
                    'sequence__module__cours'
                ).get(pk=bloc_id)
            except BlocContenu.DoesNotExist:
                return Response({'error': f'Bloc {bloc_id} introuvable'}, status=404)

            if _recently_generated(apprenant, trigger, bloc_id=bloc_id):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
                    'message': 'Génération récente déjà faite.',
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
                'bloc_contenu': _get_bloc_texte(bloc),
                'duree_estimee_min': round(duree_estimee_sec / 60, 1),
                'duree_passee_min': round(duree_passee_sec / 60, 1),
                'ratio_pct': round((duree_passee_sec / duree_estimee_sec) * 100) if duree_estimee_sec else 0,
                'nb_ouvertures': int(request.data.get('nb_ouvertures', 1)),
                'scroll_max_pct': int(request.data.get('scroll_max_pct', 0)),
                'cours_titre': crs.titre if crs else '',
                'sequence_titre': seq.titre if seq else '',
            }

            ai_req = AIAnalysisRequest.objects.create(
                apprenant=apprenant,
                bloc=bloc,
                sequence=seq,
                module=mod,
                cours=crs,
                trigger=trigger,
                prompt_context=context,
            )

        # ── Quiz rate ────────────────────────────────────────────────
        elif trigger == 'quiz_rate':
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

            if _recently_generated(apprenant, trigger, quiz_id=quiz_id, hours=4):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
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
                apprenant=apprenant,
                quiz=quiz,
                sequence=seq,
                module=mod,
                cours=crs,
                trigger=trigger,
                prompt_context=context,
            )

        # ── Sequence complexe ──────────────────────────────────────────
        elif trigger == 'sequence_complexe':
            sequence_id = request.data.get('sequence_id')
            if not sequence_id:
                return Response({'error': 'sequence_id requis'}, status=400)
            try:
                seq = Sequence.objects.select_related(
                    'module__cours'
                ).get(pk=sequence_id)
            except Sequence.DoesNotExist:
                return Response({'error': f'Séquence {sequence_id} introuvable'}, status=404)

            if _recently_generated(apprenant, trigger, sequence_id=sequence_id):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
                    'message': 'Séquence déjà générée.',
                }, status=200)

            mod = getattr(seq, 'module', None)
            crs = getattr(mod, 'cours', None) if mod else None
            summary = SequenceAnalyticsSummary.objects.filter(
                apprenant=apprenant, sequence=seq
            ).first()

            context = {
                'sequence_titre': seq.titre,
                'sequence_contenu': seq.titre,
                'module_titre': mod.titre if mod else '',
                'cours_titre': crs.titre if crs else '',
                'ratio_temps_pct': summary.ratio_temps_pct if summary else 0,
                'score_moyen': summary.score_moyen_quiz if summary else 0,
                'concepts_difficiles': [],
            }

            ai_req = AIAnalysisRequest.objects.create(
                apprenant=apprenant,
                sequence=seq,
                module=mod,
                cours=crs,
                trigger=trigger,
                prompt_context=context,
            )

        # ── Module difficile ─────────────────────────────────────────
        elif trigger == 'module_difficile':
            module_id = request.data.get('module_id')
            if not module_id:
                return Response({'error': 'module_id requis'}, status=400)
            try:
                from courses.models import Module
                mod = Module.objects.select_related('cours').get(pk=module_id)
            except Exception:
                return Response({'error': f'Module {module_id} introuvable'}, status=404)

            if _recently_generated(apprenant, trigger, module_id=module_id):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
                    'message': 'Module déjà généré.',
                }, status=200)

            crs = getattr(mod, 'cours', None)
            summary = ModuleAnalyticsSummary.objects.filter(
                apprenant=apprenant, module=mod
            ).first()

            context = {
                'module_titre': mod.titre,
                'module_description': getattr(mod, 'description', '') or '',
                'cours_titre': crs.titre if crs else '',
                'score_moyen': summary.score_moyen_quiz if summary else 0,
                'temps_total_min': round((summary.duree_totale_sec or 0) / 60, 1) if summary else 0,
                'ratio_temps_pct': summary.ratio_temps_pct if summary else 0,
                'concepts_rates': [],
                'prerequis': getattr(mod, 'description', '') or '',
            }

            ai_req = AIAnalysisRequest.objects.create(
                apprenant=apprenant,
                module=mod,
                cours=crs,
                trigger=trigger,
                prompt_context=context,
            )

        _run_in_thread(ai_req.pk)
        logger.info('[ai] trigger=%s apprenant=%s request_id=%s', trigger, apprenant.pk, ai_req.pk)

        return Response({
            'request_id': ai_req.pk,
            'status': 'pending',
            'message': 'Génération en cours...',
        }, status=202)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/ai/suggestions/<appr_id>/ — Récupère suggestions IA
# ══════════════════════════════════════════════════════════════════════════════

class AISuggestionsView(APIView):
    """
    GET /api/analytics/ai/suggestions/<int:apprenant_id>/
    Optionnel : ?type=bloc_simplifie | quiz_remediation
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        type_filter = request.query_params.get('type')

        contenus_qs = ContenuGenere.objects.filter(apprenant=apprenant)
        if type_filter:
            contenus_qs = contenus_qs.filter(type_contenu=type_filter)

        quizs_qs = QuizGenereClaude.objects.filter(apprenant=apprenant)

        pending = AIAnalysisRequest.objects.filter(
            apprenant=apprenant, status='pending'
        ).count()

        return Response({
            'contenus': [_contenu_genere_dict(c) for c in contenus_qs],
            'quizs': [_quiz_genere_dict(q) for q in quizs_qs],
            'pending_count': pending,
        })


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /contenu/<pk>/consulte/ — Marque contenu comme consulté
# ══════════════════════════════════════════════════════════════════════════════

class ContenuGenereConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        contenu = get_object_or_404(ContenuGenere, pk=pk, apprenant=apprenant)
        contenu.marquer_consulte()
        return Response({'status': 'ok'})


class ContenuGenereFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        contenu = get_object_or_404(ContenuGenere, pk=pk, apprenant=apprenant)
        a_aide = request.data.get('a_aide')
        if a_aide is None:
            return Response({'error': 'a_aide requis'}, status=400)
        contenu.soumettre_feedback(bool(a_aide))
        return Response({'status': 'ok'})


class ContenuGenereDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        apprenant = _get_apprenant(request)
        contenu = get_object_or_404(ContenuGenere, pk=pk, apprenant=apprenant)
        return Response(_contenu_genere_dict(contenu))


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /quiz-genere/<pk>/consulte/
# POST  /quiz-genere/<pk>/score/
# ══════════════════════════════════════════════════════════════════════════════

class QuizGenereClaudeConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        quiz = get_object_or_404(QuizGenereClaude, pk=pk, apprenant=apprenant)
        quiz.marquer_consulte()
        return Response({'status': 'ok'})


class QuizGenereClaudeScoreView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        apprenant = _get_apprenant(request)
        quiz = get_object_or_404(QuizGenereClaude, pk=pk, apprenant=apprenant)
        score = request.data.get('score')
        if score is None:
            return Response({'error': 'score requis (0-100)'}, status=400)
        quiz.soumettre_score(int(score))
        return Response({
            'status': 'ok',
            'remediation_reussie': quiz.remediation_reussie,
            'score': quiz.score_remediation,
        })


# ══════════════════════════════════════════════════════════════════════════════
# STUB — Recommandations (à implémenter plus tard)
# ══════════════════════════════════════════════════════════════════════════════

class RecommandationsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, apprenant_id):
        return Response({'recommendations': []})

class RecommandationVueView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def patch(self, request, pk):
        return Response({'status': 'ok'})

class RecommandationSuivieView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def patch(self, request, pk):
        return Response({'status': 'ok'})