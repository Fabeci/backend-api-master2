# gamification/views.py
import logging
from datetime import timedelta
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _get_apprenant(request, apprenant_id=None):
    # ✅ SÉCURITÉ : résolution de l'apprenant + contrôle d'accès (anti-IDOR).
    # Un utilisateur ne peut cibler qu'un apprenant qu'il est en droit de voir.
    from users.access_control import resolve_apprenant
    return resolve_apprenant(request, apprenant_id)


def _fmt_badge(ub):
    b = ub.badge
    return {
        'id': b.pk, 'code': b.code, 'nom': b.nom,
        'description': b.description, 'categorie': b.categorie,
        'rarete': b.rarete, 'icone': b.icone, 'couleur': b.couleur,
        'est_affiche': ub.est_affiche,
        'obtained_at': ub.obtained_at.isoformat(),
    }


def _fmt_mission(um):
    m = um.mission
    return {
        'id': um.pk, 'mission_id': m.pk,
        'titre': m.titre, 'description': m.description,
        'type': m.type_mission, 'difficulte': m.difficulte,
        'action': m.action,
        'progression': um.progression, 'cible': um.cible,
        'pct': um.pct_progression, 'statut': um.statut,
        'xp_recompense': m.xp_recompense,
        'expire_le': um.expire_le.isoformat(),
        'completee_le': um.completee_le.isoformat() if um.completee_le else None,
    }


def _apprenant_name(apprenant_id: int) -> str:
    try:
        from users.models import Apprenant
        a = Apprenant.objects.select_related('user').get(pk=apprenant_id)
        return f'{a.user.first_name} {a.user.last_name}'.strip() or a.user.username
    except Exception:
        return f'Apprenant #{apprenant_id}'


class GamificationProfileView(APIView):
    """GET /api/gamification/profil/<id>/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .models import UserLevel, Streak, UserBadge, UserMission, XPTransaction, LEVEL_THRESHOLDS
        from django.db.models import Sum

        lvl, _    = UserLevel.objects.get_or_create(apprenant=apprenant)
        streak, _ = Streak.objects.get_or_create(apprenant=apprenant)

        recent_badges = UserBadge.objects.filter(
            apprenant=apprenant, est_affiche=True
        ).select_related('badge').order_by('-obtained_at')[:5]

        missions_actives = UserMission.objects.filter(
            apprenant=apprenant, statut='active',
            expire_le__gte=timezone.now()
        ).select_related('mission').order_by('expire_le')[:5]

        since_monday = timezone.now() - timedelta(days=timezone.now().weekday())
        xp_semaine = XPTransaction.objects.filter(
            apprenant=apprenant, created_at__gte=since_monday
        ).aggregate(total=Sum('xp'))['total'] or 0

        return Response({
            'niveau': {
                'numero':      lvl.niveau,
                'titre':       lvl.titre,
                'xp_total':    lvl.xp_total,
                'xp_semaine':  xp_semaine,
                'xp_actuel':   LEVEL_THRESHOLDS[lvl.niveau],
                'xp_prochain': lvl.xp_pour_prochain_niveau,
                'pct':         lvl.pct_vers_prochain,
            },
            'streak': {
                'actuel':            streak.streak_actuel,
                'max':               streak.streak_max,
                'multiplicateur':    streak.multiplicateur,
                'protections_dispo': streak.protections_dispo,
                'peut_reparer':      streak.peut_reparer,
            },
            'badges_recents': [_fmt_badge(ub) for ub in recent_badges],
            'nb_badges':      UserBadge.objects.filter(apprenant=apprenant).count(),
            'missions':       [_fmt_mission(um) for um in missions_actives],
        })


class XPHistoryView(APIView):
    """GET /api/gamification/xp-history/<id>/?limit=20"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .models import XPTransaction
        limit = min(int(request.query_params.get('limit', 20)), 100)
        txs = XPTransaction.objects.filter(apprenant=apprenant).order_by('-created_at')[:limit]

        return Response({'transactions': [
            {'source': t.source, 'xp': t.xp, 'multiplicateur': float(t.multiplicateur),
             'created_at': t.created_at.isoformat()}
            for t in txs
        ]})


class BadgesView(APIView):
    """GET /api/gamification/badges/<id>/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .models import UserBadge
        ubs = UserBadge.objects.filter(apprenant=apprenant).select_related('badge').order_by('-obtained_at')
        return Response({'badges': [_fmt_badge(ub) for ub in ubs]})


class MissionsView(APIView):
    """GET /api/gamification/missions/<id>/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, apprenant_id):
        apprenant = _get_apprenant(request, apprenant_id)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        from .models import UserMission
        from .mission_engine import generate_daily_missions

        generate_daily_missions(apprenant)

        ums = UserMission.objects.filter(
            apprenant=apprenant, statut='active', expire_le__gte=timezone.now()
        ).select_related('mission').order_by('expire_le')

        return Response({'missions': [_fmt_mission(um) for um in ums]})


class StreakProtectView(APIView):
    """POST /api/gamification/streak/protect/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)
        from .streak_engine import use_protection
        ok = use_protection(apprenant)
        return Response({'success': ok})


class StreakRepairView(APIView):
    """POST /api/gamification/streak/repair/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        apprenant = _get_apprenant(request)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)
        from .streak_engine import repair_streak
        ok = repair_streak(apprenant)
        return Response({'success': ok})


class LeaderboardView(APIView):
    """
    GET /api/gamification/leaderboard/?type=xp_hebdo|streak
    Retourne le classement centré sur l'apprenant courant.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        apprenant = _get_apprenant(request)
        if not apprenant:
            return Response({'error': 'Apprenant introuvable'}, status=403)

        board_type = request.query_params.get('type', 'xp_hebdo')

        # ✅ Scoping : le classement est limité aux apprenants du MÊME
        # établissement (sinon on divulgue les noms/points d'autres écoles).
        scope_ids = None
        inst_id = getattr(apprenant, 'institution_id', None)
        if inst_id:
            from users.models import Apprenant
            scope_ids = list(
                Apprenant.objects.filter(institution_id=inst_id).values_list('pk', flat=True)
            )

        if board_type == 'streak':
            from .models import Streak
            qs = Streak.objects.all()
            if scope_ids is not None:
                qs = qs.filter(apprenant_id__in=scope_ids)
            rows = list(qs.select_related('apprenant').order_by('-streak_actuel'))
            key  = lambda r: r.streak_actuel
            name = lambda r: _apprenant_name(r.apprenant_id)
            own  = next((i for i, r in enumerate(rows) if r.apprenant_id == apprenant.pk), None)
        else:
            from .models import XPTransaction
            from django.db.models import Sum
            since = timezone.now() - timedelta(days=timezone.now().weekday())
            qs = XPTransaction.objects.filter(created_at__gte=since)
            if scope_ids is not None:
                qs = qs.filter(apprenant_id__in=scope_ids)
            rows = list(
                qs.values('apprenant_id')
                .annotate(score=Sum('xp'))
                .order_by('-score')
            )
            key  = lambda r: r['score']
            name = lambda r: _apprenant_name(r['apprenant_id'])
            own  = next((i for i, r in enumerate(rows) if r['apprenant_id'] == apprenant.pk), None)

        if own is None:
            return Response({'entries': [], 'mon_rang': None, 'total': len(rows)})

        indices = set(range(min(3, len(rows))))
        indices |= set(range(max(0, own - 3), min(len(rows), own + 4)))
        indices = sorted(indices)

        entries = []
        prev_idx = None
        for idx in indices:
            if prev_idx is not None and idx > prev_idx + 1:
                entries.append({'separator': True})
            r = rows[idx]
            entries.append({
                'rang':    idx + 1,
                'est_moi': idx == own,
                'nom':     name(r),
                'score':   key(r),
            })
            prev_idx = idx

        return Response({'entries': entries, 'mon_rang': own + 1, 'total': len(rows)})
