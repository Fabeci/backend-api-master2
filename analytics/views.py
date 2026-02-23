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
from django.utils import timezone
from django.db.models import Sum, Count, Max, Min, Q
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from courses.models import BlocContenu, Sequence

# from .models import Module, Cours
from .models import (
    BlocAnalytics, BlocAnalyticsSummary,
    SequenceAnalyticsSummary, ModuleAnalyticsSummary,
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
# VUES STUB — Recommandations & Contenu généré
# Retournent 200 pour ne pas casser le frontend.
# À compléter quand les modèles existent.
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

class ContenuGenereDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, pk):
        return Response({'error': 'non implémenté'}, status=404)

class ContenuGenereConsulteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def patch(self, request, pk):
        return Response({'status': 'ok'})

class ContenuGenereFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def patch(self, request, pk):
        return Response({'status': 'ok'})