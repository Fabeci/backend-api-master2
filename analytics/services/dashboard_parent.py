# analytics/services/dashboard_parent.py
"""
DashboardParentService — suivi des enfants.
Périmètre strict : uniquement les apprenants liés à ce parent (tuteur).
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum

from .dashboard_base import BaseDashboardService
from .dashboard_context import DashboardContext


AVATAR_COLORS = ['#757fef', '#00b69b', '#ee368c', '#2db6f5', '#f59e0b', '#8b5cf6']


class DashboardParentService(BaseDashboardService):

    def build(self, filters: dict) -> dict:
        from courses.models import InscriptionCours, Session
        from progress.models import ProgressionApprenant, HistoriqueActivite
        from evaluations.models import PassageEvaluation
        from notifications.models import Notification

        parent   = self.ctx.profile   # Parent
        enfants  = self.ctx.children  # list[Apprenant]
        now      = self.now
        today    = self.today
        in7      = today + timedelta(days=7)

        # ✅ Filtre par enfant : si ?apprenant_id=… est fourni, on restreint TOUT
        #    le contenu (KPI, alertes, tableau) à cet enfant.
        apprenant_id = self.ctx.filters.get('apprenant_id')
        if isinstance(apprenant_id, (list, tuple)):
            apprenant_id = apprenant_id[0] if apprenant_id else None
        if apprenant_id:
            enfants = [e for e in enfants if str(e.id) == str(apprenant_id)]

        nb_enfants  = len(enfants)
        enfants_ids = [e.id for e in enfants]

        # ── Données agrégées toutes-enfants ───────────────────────────────────
        prog_qs = ProgressionApprenant.objects.filter(apprenant__in=enfants_ids)
        pass_qs = PassageEvaluation.objects.filter(apprenant__in=enfants_ids, statut='corrige')
        notif_nb = Notification.objects.filter(recipient=self.ctx.user, is_read=False).count()

        agg_all = prog_qs.aggregate(
            avg_comp=Avg('pourcentage_completion'),
            avg_note=Avg('note_moyenne_evaluations'),
        )
        avg_comp = round(float(agg_all['avg_comp'] or 0), 1)
        avg_note = round(float(self._safe_avg(pass_qs, 'note')), 1)

        # ── KPIs globaux ──────────────────────────────────────────────────────
        kpis = [
            self._kpi('Enfants suivis',  nb_enfants,            'ri-parent-line',
                      tooltip="Nombre d'enfants liés à ce compte parent"),
            self._kpi('Complétion moy.', f'{avg_comp:.0f}%',    'ri-percent-line',
                      tooltip='Progression moyenne de vos enfants sur leurs cours'),
            self._kpi('Note moyenne',    f'{avg_note:.1f}/20',   'ri-star-line',
                      tooltip='Note moyenne sur toutes les évaluations corrigées'),
            self._kpi('Notifications',   notif_nb,               'ri-notification-line',
                      trend='down' if notif_nb > 5 else 'stable',
                      tooltip='Notifications non lues'),
        ]

        # ── Données par enfant ────────────────────────────────────────────────
        lignes_enfants = []
        alerts = []
        for i, enfant in enumerate(enfants[:6]):
            prog_e = prog_qs.filter(apprenant=enfant)
            agg_e  = prog_e.aggregate(avg_c=Avg('pourcentage_completion'))
            avg_c  = round(float(agg_e['avg_c'] or 0), 1)
            avg_n  = round(float(
                PassageEvaluation.objects.filter(
                    apprenant=enfant, statut='corrige'
                ).aggregate(v=Avg('note'))['v'] or 0
            ), 1)

            cours_ids = list(
                InscriptionCours.objects.filter(apprenant=enfant)
                .values_list('cours_id', flat=True)
            )
            cours_actifs = InscriptionCours.objects.filter(
                apprenant=enfant, cours__statut='en_cours',
            ).count()
            sessions_7j = Session.objects.filter(
                cours_id__in=cours_ids,
                date_debut__date__gte=today,
                date_debut__date__lte=in7,
            ).count() if cours_ids else 0
            last_act = (
                HistoriqueActivite.objects
                .filter(apprenant=enfant)
                .order_by('-date_activite')
                .first()
            )

            if avg_c < 20 and cours_actifs > 0:
                alerts.append(self._alert(
                    'warning', f'{enfant.prenom} en difficulté',
                    f'Progression à {avg_c:.0f}% — encouragez-le !'
                ))

            lignes_enfants.append({
                'id':      enfant.id,
                'libelle': f'{enfant.prenom} {enfant.nom}',
                'value':   int(avg_c),
                'metadata': {
                    'prenom':       enfant.prenom,
                    'nom':          enfant.nom,
                    'initiales':    f'{(enfant.prenom or "E")[0]}{(enfant.nom or "E")[0]}'.upper(),
                    'avatarColor':  AVATAR_COLORS[i % len(AVATAR_COLORS)],
                    'cours_actifs': cours_actifs,
                    'prog_globale': int(avg_c),
                    'avg_note':     avg_n,
                    'sessions_7j':  sessions_7j,
                    'derniere_act': (
                        last_act.date_activite.date().isoformat() if last_act else ''
                    ),
                }
            })

        # ── Assemblage final ──────────────────────────────────────────────────
        data = self._base('Dashboard Parent', 'Suivi de mon enfant', kpis, alerts)
        data['enfants'] = self._drill(
            'Mes enfants', ['Enfant', 'Progression', 'Note'], lignes_enfants,
        )
        return data
