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
    RecommandationPedagogique,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HELPER — résolution de l'apprenant (BUG 2)
# ══════════════════════════════════════════════════════════════════════════════

def _get_apprenant(request, apprenant_id=None):
    """
    Résout l'objet Apprenant en respectant les règles d'accès (anti-IDOR).
    Un utilisateur ne peut cibler qu'un apprenant qu'il est en droit de voir
    (lui-même, ses enfants, ou — selon le rôle — ceux de son institution).
    """
    # ✅ SÉCURITÉ : délègue au contrôle d'accès centralisé.
    from users.access_control import resolve_apprenant
    return resolve_apprenant(request, apprenant_id)


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
    # ✅ SÉCURITÉ : endpoint de diagnostic réservé aux administrateurs.
    permission_classes = [permissions.IsAdminUser]

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
                'username':         getattr(user, 'email', None),
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
    """Lance le traitement IA dans un thread (et marque l'échec éventuel)."""
    def _worker():
        try:
            req = AIAnalysisRequest.objects.get(pk=ai_request_id)
            from .services.ai_claude_service import traiter_demande_ai
            traiter_demande_ai(req)
            _creer_contenu_genere(req)
        except Exception as e:
            logger.error('[ai] Erreur thread : %s', e)
            try:
                req = AIAnalysisRequest.objects.get(pk=ai_request_id)
                if req.status == 'pending':
                    req.status = 'error'
                    req.error_message = str(e)[:500]
                    req.completed_at = timezone.now()
                    req.save(update_fields=['status', 'error_message', 'completed_at'])
            except Exception:
                pass
    threading.Thread(target=_worker, daemon=True).start()


def _html_list(items):
    """Rend une liste de valeurs (str ou dict) en <ul><li>…</li></ul>."""
    parts = []
    for x in items or []:
        if x is None:
            continue
        if isinstance(x, dict):
            x = (x.get('titre') or x.get('title') or x.get('label')
                 or x.get('nom') or x.get('description') or '')
        x = str(x).strip()
        if x:
            parts.append(f'<li>{x}</li>')
    return f'<ul>{"".join(parts)}</ul>' if parts else ''


def _html_from_sequence(data: dict) -> str:
    """Convertit le JSON d'une séquence adaptative en HTML lisible."""
    parts = []
    if data.get('description'):
        parts.append(f"<p>{data['description']}</p>")
    if data.get('duree_minutes'):
        parts.append(f"<p><em>Durée estimée : {data['duree_minutes']} min</em></p>")
    if data.get('objectifs'):
        parts.append('<h3>Objectifs</h3>' + _html_list(data['objectifs']))
    etapes = data.get('etapes') or []
    if etapes:
        parts.append('<h3>Étapes</h3>')
        for e in etapes:
            if isinstance(e, dict):
                titre = e.get('titre') or e.get('title') or ''
                meta = ' · '.join(str(x) for x in (
                    e.get('type'),
                    (f"{e.get('duree_minutes')} min" if e.get('duree_minutes') else None),
                ) if x)
                parts.append(f'<h4>{titre}</h4>')
                if meta:
                    parts.append(f'<p><em>{meta}</em></p>')
                instr = e.get('instructions') or e.get('description')
                if instr:
                    parts.append(f'<p>{instr}</p>')
            else:
                parts.append(f'<p>{e}</p>')
    # ✅ Filtre les ressources bidon (liens "example")
    ressources = [
        r for r in (data.get('ressources_alternatives') or [])
        if r and 'example' not in str(r).lower()
    ]
    if ressources:
        parts.append('<h3>Ressources</h3>' + _html_list(ressources))
    return ''.join(parts)


def _html_from_module(data: dict) -> str:
    """Convertit le JSON d'un module de révision / parcours de reprise en HTML."""
    parts = []
    if data.get('resume'):
        parts.append(f"<p>{data['resume']}</p>")
    if data.get('competences_cibles'):
        parts.append('<h3>Compétences visées</h3>' + _html_list(data['competences_cibles']))
    for b in data.get('bloc_contents') or []:
        if isinstance(b, dict):
            parts.append(f"<h4>{b.get('titre', '')}</h4>")
            if b.get('contenu_html'):
                parts.append(str(b['contenu_html']))
            elif b.get('contenu'):
                parts.append(f"<p>{b['contenu']}</p>")
            if b.get('objectifs'):
                parts.append(_html_list(b['objectifs']))
        else:
            parts.append(f'<p>{b}</p>')
    return ''.join(parts)


def _rattacher_contenu_recos(ai_request, contenu):
    """Rattache un ContenuGenere aux recommandations ouvertes de la même séquence."""
    if contenu is None or ai_request.sequence_id is None:
        return
    RecommandationPedagogique.objects.filter(
        apprenant=ai_request.apprenant,
        sequence_cible_id=ai_request.sequence_id,
        contenu_genere__isnull=True,
        est_suivie=False,
        est_ignoree=False,
    ).update(contenu_genere=contenu)


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

    # ✅ Ne jamais persister/afficher la sortie de repli « mock » ni un contenu vide.
    if not data or data.get('type_generation') == 'indisponible' \
            or data.get('titre') == 'Contenu temporairement indisponible':
        ai_request.status = 'skipped'
        ai_request.error_message = 'Sortie de repli (mock) ignorée'
        ai_request.save(update_fields=['status', 'error_message'])
        return
    if ai_request.trigger == 'quiz_rate' and not data.get('questions'):
        ai_request.status = 'skipped'
        ai_request.error_message = 'Quiz vide (aucune question)'
        ai_request.save(update_fields=['status', 'error_message'])
        return

    if ai_request.trigger in ('temps_long', 'multi_reouverture'):
        contenu = ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='bloc_simplifie' if ai_request.trigger == 'temps_long' else 'bloc_alternatif',
            titre=data.get('titre', 'Explication simplifiée'),
            contenu_html=data.get('contenu_html', ''),
            contenu_json=data,
            bloc_source=ai_request.bloc,
            concepts_cibles=data.get('concepts_cibles', []),
        )
        _rattacher_contenu_recos(ai_request, contenu)
    elif ai_request.trigger in ('sequence_complexe',):
        # ✅ Explication pédagogique (définition + exemples) et non un simple plan.
        contenu = ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='bloc_simplifie',
            titre=data.get('titre', 'Explication du cours'),
            description=data.get('description', ''),
            contenu_html=data.get('contenu_html') or _html_from_sequence(data),
            contenu_json=data,
            sequence_source=ai_request.sequence,
            concepts_cibles=data.get('concepts_cibles', []),
            niveau_difficulte=data.get('sequence_niveau', 'intermediaire'),
        )
        _rattacher_contenu_recos(ai_request, contenu)
    elif ai_request.trigger == 'module_difficile':
        ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='module_revision',
            titre=data.get('titre', 'Module de révision'),
            description=data.get('resume', ''),
            contenu_html=_html_from_module(data),
            contenu_json=data,
            module_source=ai_request.module,
            concepts_cibles=data.get('competences_cibles', []),
            niveau_difficulte=data.get('sequence_niveau', 'intermediaire'),
        )
    elif ai_request.trigger == 'cours_abandonne':
        contenu = ContenuGenere.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            type_contenu='module_revision',
            titre=data.get('titre', 'Parcours de reprise'),
            description=data.get('resume', ''),
            contenu_html=_html_from_module(data),
            contenu_json=data,
            concepts_cibles=data.get('competences_cibles', []),
            niveau_difficulte=data.get('sequence_niveau', 'debutant'),
        )
        # Recommandation associée, visible et suivable par l'apprenant.
        if not RecommandationPedagogique.objects.filter(
            apprenant=ai_request.apprenant,
            cours=ai_request.cours,
            type_recommandation='module_revision',
            est_ignoree=False,
        ).exists():
            RecommandationPedagogique.objects.create(
                apprenant=ai_request.apprenant,
                cours=ai_request.cours,
                contenu_genere=contenu,
                type_recommandation='module_revision',
                message=(
                    f"Reprenez « {ai_request.cours.titre} » avec un parcours adapté !"
                    if ai_request.cours else
                    "Un parcours de reprise est disponible pour vous !"
                ),
                priorite=1,
            )

    elif ai_request.trigger == 'quiz_rate':
        quiz_genere = QuizGenereClaude.objects.create(
            ai_request=ai_request,
            apprenant=ai_request.apprenant,
            quiz_source=ai_request.quiz,
            titre=data.get('titre', 'Quiz de remédiation'),
            consigne=data.get('consigne', ''),
            questions=data.get('questions', []),
            concepts_rates=data.get('concepts_rates', []),
        )
        # ✅ Rattaché aux recommandations ouvertes de la séquence (bouton « Passer le quiz »).
        if ai_request.sequence_id:
            RecommandationPedagogique.objects.filter(
                apprenant=ai_request.apprenant,
                sequence_cible_id=ai_request.sequence_id,
                quiz_genere__isnull=True,
                est_suivie=False, est_ignoree=False,
            ).update(quiz_genere=quiz_genere)

    # ✅ Phase 11 : rattacher le contenu/quiz à l'intervention d'origine.
    if getattr(ai_request, 'intervention_id', None):
        from .models import LearningIntervention
        iv = LearningIntervention.objects.filter(pk=ai_request.intervention_id).first()
        if iv:
            cg = ContenuGenere.objects.filter(ai_request=ai_request).first()
            qg = QuizGenereClaude.objects.filter(ai_request=ai_request).first()
            fields = []
            if cg:
                iv.contenu_genere = cg; fields.append('contenu_genere')
            if qg:
                iv.quiz_genere = qg; fields.append('quiz_genere')
            if fields:
                iv.save(update_fields=fields)


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
              | "sequence_complexe" | "module_difficile" | "cours_abandonne",
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

      // Pour cours_abandonne :
      "cours_id": 7,
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request, request.data.get('apprenant_id'))
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        # ✅ Anti-flood : une seule génération à la fois par apprenant
        #    (les `pending` périmés > 10 min — thread tué — sont ignorés).
        from datetime import timedelta as _td
        cutoff_pending = timezone.now() - _td(minutes=10)
        if AIAnalysisRequest.objects.filter(
            apprenant=apprenant, status='pending', created_at__gte=cutoff_pending,
        ).exists():
            return Response({
                'request_id': None,
                'status': 'busy',
                'message': 'Une génération est déjà en cours pour vous. Merci de patienter.',
            }, status=200)

        trigger = request.data.get('trigger')
        valid_triggers = ('temps_long', 'multi_reouverture', 'quiz_rate',
                        'sequence_complexe', 'module_difficile', 'cours_abandonne')
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
                # Repli : générer pour le premier quiz de la séquence (demande depuis le panneau Reco)
                seq_id = request.data.get('sequence_id')
                if seq_id:
                    try:
                        from evaluations.models import Quiz
                        quiz_id = Quiz.objects.filter(sequence_id=seq_id).values_list('pk', flat=True).first()
                    except Exception:  # noqa: BLE001
                        quiz_id = None
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

            # Questions ratées : fournies par le client, sinon déduites du dernier passage.
            try:
                from analytics.services.quiz_missed import questions_ratees as _questions_ratees
                q_ratees = request.data.get('questions_ratees') or _questions_ratees(apprenant, quiz)
            except Exception:  # noqa: BLE001
                q_ratees = request.data.get('questions_ratees', [])

            context = {
                'quiz_titre': quiz.titre,
                'quiz_description': getattr(quiz, 'description', '') or '',
                'score_obtenu': int(request.data.get('score_obtenu', 0)),
                'nb_tentatives': int(request.data.get('nb_tentatives', 1)),
                'questions_ratees': q_ratees,
                'cours_titre': crs.titre if crs else '',
                'sequence_titre': seq.titre if seq else '',
            }

            # Recommandation visible, basée sur les questions ratées.
            if seq is not None:
                try:
                    deja = RecommandationPedagogique.objects.filter(
                        apprenant=apprenant,
                        sequence_cible_id=seq.id,
                        est_ignoree=False,
                    ).exists()
                    if not deja:
                        extraits = ' ; '.join(
                            (q.get('question') or '')[:70] for q in (q_ratees or [])[:2]
                        )
                        message = (
                            f"Quiz « {quiz.titre} » à retravailler. "
                            + (f"Points à revoir : {extraits}. " if extraits else "")
                            + "Un contenu de remédiation ciblé est proposé."
                        )
                        RecommandationPedagogique.objects.create(
                            apprenant=apprenant,
                            cours=crs,
                            sequence_cible=seq,
                            type_recommandation='quiz_supplementaire',
                            message=message,
                            priorite=1,
                        )
                except Exception:  # noqa: BLE001
                    pass

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

        # ── Cours abandonné ───────────────────────────────────────────
        elif trigger == 'cours_abandonne':
            cours_id = request.data.get('cours_id')
            if not cours_id:
                return Response({'error': 'cours_id requis'}, status=400)
            try:
                from courses.models import Cours
                crs = Cours.objects.get(pk=cours_id)
            except Exception:
                return Response({'error': f'Cours {cours_id} introuvable'}, status=404)

            if _recently_generated(apprenant, trigger, cours_id=cours_id, hours=24):
                return Response({
                    'request_id': None,
                    'status': 'skipped',
                    'message': 'Parcours de reprise déjà généré.',
                }, status=200)

            from .recommendation_engine import build_cours_abandonne_context
            context = build_cours_abandonne_context(apprenant, crs)

            ai_req = AIAnalysisRequest.objects.create(
                apprenant=apprenant,
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
        from .services.event_service import record_event
        record_event(apprenant, 'AI_CONTENT_VIEWED',
                     sequence=contenu.sequence_source, bloc=contenu.bloc_source,
                     metadata={'contenu_id': contenu.pk, 'type': contenu.type_contenu})
        # Phase 12 : mesure d'efficacité si ce contenu provient d'une intervention
        from .models import LearningIntervention
        from .services.outcome_engine import on_intervention_activity
        for iv in LearningIntervention.objects.filter(contenu_genere=contenu):
            on_intervention_activity(iv, 'content')
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

class QuizGenereClaudeDetailView(APIView):
    """GET /api/v1/analytics/quiz-genere/<pk>/ — quiz de remédiation IA complet."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        apprenant = _get_apprenant(request)
        quiz = get_object_or_404(QuizGenereClaude, pk=pk, apprenant=apprenant)
        return Response(_quiz_genere_dict(quiz))


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
        from .services.event_service import record_event
        record_event(apprenant, 'AI_QUIZ_COMPLETED',
                     sequence=getattr(quiz.quiz_source, 'sequence', None) if quiz.quiz_source else None,
                     metadata={'quiz_genere_id': quiz.pk, 'score': int(score)})
        # Phase 12 : mesure d'efficacité si ce quiz provient d'une intervention
        from .models import LearningIntervention
        from .services.outcome_engine import on_intervention_activity
        for iv in LearningIntervention.objects.filter(quiz_genere=quiz):
            on_intervention_activity(iv, 'quiz')
        return Response({
            'status': 'ok',
            'remediation_reussie': quiz.remediation_reussie,
            'score': quiz.score_remediation,
        })


# ══════════════════════════════════════════════════════════════════════════════
# RECOMMANDATIONS — liste + suivi
#   GET   /api/v1/analytics/recommendations/<apprenant_id>/
#   PATCH /api/v1/analytics/recommendations/<pk>/vue/
#   PATCH /api/v1/analytics/recommendations/<pk>/suivie/
# ══════════════════════════════════════════════════════════════════════════════

def _reco_dict(r):
    return {
        'id':                  r.pk,
        'type_recommandation': r.type_recommandation,
        'message':             r.message,
        'priorite':            r.priorite,
        'est_vue':             r.est_vue,
        'est_suivie':          r.est_suivie,
        'est_ignoree':         r.est_ignoree,
        'contenu_genere':      r.contenu_genere_id,
        'quiz_genere':         r.quiz_genere_id,
        'intervention':        r.intervention_id,
        'cours_id':            r.cours_id,
        'bloc_cible_id':       r.bloc_cible_id,
        'sequence_cible_id':   r.sequence_cible_id,
        'date_creation':       _dt(r.date_creation),
        'date_expiration':     _dt(r.date_expiration),
    }


class RecommandationsListView(APIView):
    """
    GET /api/v1/analytics/recommendations/<apprenant_id>/
    Paramètres optionnels : ?cours_id=<int>&all=1 (inclure les suivies)
    Génère (si nécessaire) puis retourne les recommandations de l'apprenant.
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
                cours = None

        # Génération à la demande (dédupliquée côté moteur).
        from .services.recommendation_engine import RecommendationEngine
        try:
            RecommendationEngine(apprenant, cours=cours).analyser_et_recommander()
        except Exception as e:  # noqa: BLE001
            logger.warning('[reco] génération impossible : %s', e)

        qs = RecommandationPedagogique.objects.filter(apprenant=apprenant)
        if cours:
            # ✅ Matche aussi les recos dont le cours n'est pas renseigné mais dont
            #    la séquence appartient au cours courant.
            qs = qs.filter(
                Q(cours=cours) | Q(cours__isnull=True, sequence_cible__module__cours=cours)
            )
        if request.query_params.get('all') not in ('1', 'true', 'True'):
            qs = qs.filter(est_suivie=False, est_ignoree=False)

        # ✅ Uniquement les séquences réellement travaillées par l'apprenant
        #    (les recos sans séquence — ex. cours abandonné — restent visibles).
        from .models import BlocAnalytics
        active_seq_ids = list(
            BlocAnalytics.objects.filter(
                apprenant=apprenant, sequence__isnull=False,
            ).values_list('sequence_id', flat=True)
        )
        qs = qs.filter(Q(sequence_cible_id__in=active_seq_ids) | Q(sequence_cible__isnull=True))

        qs = qs.select_related('cours', 'bloc_cible', 'sequence_cible')
        recos_list = list(qs)

        # ✅ Rattacher un contenu IA existant non encore lié à la reco
        from .models import ContenuGenere
        seq_ids = {
            r.sequence_cible_id for r in recos_list
            if r.contenu_genere_id is None and r.sequence_cible_id
        }
        if seq_ids:
            latest = {}
            for cg in ContenuGenere.objects.filter(
                apprenant=apprenant, sequence_source_id__in=seq_ids,
            ).order_by('created_at'):
                latest[cg.sequence_source_id] = cg
            for r in recos_list:
                if r.contenu_genere_id is None and r.sequence_cible_id in latest:
                    r.contenu_genere = latest[r.sequence_cible_id]
                    r.save(update_fields=['contenu_genere'])

        # ✅ Rattacher un quiz IA existant non encore lié à la reco
        from .models import QuizGenereClaude
        quiz_seq_ids = {
            r.sequence_cible_id for r in recos_list
            if r.quiz_genere_id is None and r.sequence_cible_id
        }
        if quiz_seq_ids:
            latest_q = {}
            for qg in QuizGenereClaude.objects.filter(
                apprenant=apprenant, quiz_source__sequence_id__in=quiz_seq_ids,
            ).select_related('quiz_source').order_by('created_at'):
                latest_q[qg.quiz_source.sequence_id] = qg
            for r in recos_list:
                if r.quiz_genere_id is None and r.sequence_cible_id in latest_q:
                    r.quiz_genere = latest_q[r.sequence_cible_id]
                    r.save(update_fields=['quiz_genere'])

        # ✅ Séquences DÉJÀ VALIDÉES : on solde les recos correspondantes
        #    (est_suivie) et on ne les propose plus, même si une lacune subsiste.
        try:
            from courses.parcours_engine import sequence_est_validee_pour
            recos_kept = []
            for r in recos_list:
                if r.sequence_cible_id and r.sequence_cible \
                        and sequence_est_validee_pour(apprenant, r.sequence_cible):
                    if not r.est_suivie:
                        r.est_suivie = True
                        r.save(update_fields=['est_suivie'])
                    continue
                recos_kept.append(r)
            recos_list = recos_kept
        except Exception as e:  # noqa: BLE001
            logger.warning('[reco] filtrage séquences validées impossible : %s', e)

        # ✅ La recommandation est la CONSÉQUENCE du diagnostic : on ne garde que
        #    les recos adossées à un diagnostic actif, ou déjà dotées d'un
        #    contenu / quiz / intervention (décision déjà prise).
        from .services.diagnosis_engine import refresh_diagnoses
        from .services.refresh_guard import fresh_or_run
        from .models import LearningDiagnosis
        try:
            fresh_or_run(apprenant, 'diagnoses', lambda: refresh_diagnoses(apprenant))
            diag_seq_ids = set(
                LearningDiagnosis.objects.filter(
                    apprenant=apprenant, statut='actif', sequence__isnull=False,
                ).values_list('sequence_id', flat=True)
            )
            recos_list = [
                r for r in recos_list
                if (r.sequence_cible_id in diag_seq_ids)
                or r.contenu_genere_id or r.quiz_genere_id or r.intervention_id
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning('[reco] filtrage diagnostic impossible : %s', e)

        recos = [_reco_dict(r) for r in recos_list]
        return Response({'recommendations': recos, 'total': len(recos)})


class RecommandationVueView(APIView):
    """PATCH /api/v1/analytics/recommendations/<pk>/vue/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        reco = get_object_or_404(RecommandationPedagogique, pk=pk, apprenant=apprenant)
        reco.marquer_vue()
        from .services.event_service import record_event
        record_event(apprenant, 'RECOMMENDATION_VIEWED',
                     cours=reco.cours, sequence=reco.sequence_cible,
                     metadata={'recommandation_id': reco.pk})
        return Response({'status': 'ok', 'est_vue': reco.est_vue})


class RecommandationSuivieView(APIView):
    """PATCH /api/v1/analytics/recommendations/<pk>/suivie/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        reco = get_object_or_404(RecommandationPedagogique, pk=pk, apprenant=apprenant)
        reco.marquer_suivie()
        from .services.event_service import record_event
        record_event(apprenant, 'RECOMMENDATION_ACCEPTED',
                     cours=reco.cours, sequence=reco.sequence_cible,
                     metadata={'recommandation_id': reco.pk})
        return Response({'status': 'ok', 'est_suivie': reco.est_suivie})


class RecommandationIgnoreeView(APIView):
    """PATCH /api/v1/analytics/recommendations/<pk>/ignoree/ — rejet définitif."""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        apprenant = _get_apprenant(request)
        reco = get_object_or_404(RecommandationPedagogique, pk=pk, apprenant=apprenant)
        reco.marquer_ignoree()
        from .services.event_service import record_event
        record_event(apprenant, 'RECOMMENDATION_IGNORED',
                     cours=reco.cours, sequence=reco.sequence_cible,
                     metadata={'recommandation_id': reco.pk})
        return Response({'status': 'ok', 'est_ignoree': reco.est_ignoree})