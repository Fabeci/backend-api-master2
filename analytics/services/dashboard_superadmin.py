# analytics/services/dashboard_superadmin.py
"""
DashboardSuperAdminService — vue globale toutes institutions.
Accessible uniquement aux superusers Django.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count

from .dashboard_base import BaseDashboardService
from .dashboard_context import DashboardContext


class DashboardSuperAdminService(BaseDashboardService):

    def build(self, filters: dict) -> dict:
        from academics.models import Institution, AnneeScolaire
        from users.models import User, Apprenant as _A, Formateur as _F

        now   = self.now
        today = self.today

        # ── Compteurs globaux ────────────────────────────────────────────────
        nb_institutions = Institution.objects.count()
        nb_users        = User.objects.filter(is_active=True).count()
        nb_annees       = AnneeScolaire.objects.count()
        nb_apprenants   = _A.objects.count()
        nb_formateurs   = _F.objects.count()

        # ── Évolution mensuelle (12 derniers mois) ───────────────────────────
        mois_labels, mois_data = [], []
        for i in range(11, -1, -1):
            d = (now - timedelta(days=i * 30)).date().replace(day=1)
            mois_labels.append(d.strftime('%b'))
            mois_data.append(
                User.objects.filter(
                    date_joined__year=d.year,
                    date_joined__month=d.month,
                ).count()
            )

        # ── KPIs ─────────────────────────────────────────────────────────────
        kpis = [
            self._kpi('Institutions',       nb_institutions, 'ri-building-line',
                      tooltip="Nombre total d'institutions"),
            self._kpi('Utilisateurs actifs', nb_users,        'ri-group-line',
                      tooltip='Comptes actifs sur la plateforme'),
            self._kpi('Apprenants',          nb_apprenants,   'ri-user-line',
                      tooltip='Apprenants inscrits'),
            self._kpi('Formateurs',          nb_formateurs,   'ri-user-star-line',
                      tooltip='Formateurs enregistrés'),
            self._kpi('Années scolaires',    nb_annees,       'ri-calendar-line',
                      tooltip='Années scolaires créées'),
        ]

        # ── Institutions drill-down ───────────────────────────────────────────
        lignes_inst = []
        for inst in Institution.objects.values('id', 'nom')[:10]:
            nb = _A.objects.filter(institution_id=inst['id']).count()
            lignes_inst.append({
                'id': inst['id'], 'libelle': inst['nom'], 'value': nb,
                'metadata': {'apprenants': nb},
            })

        # ── Assemblage final ──────────────────────────────────────────────────
        data = self._base(
            'Dashboard Super Admin', 'Vue globale de toutes les institutions', kpis,
        )
        data['institutions'] = self._drill(
            'Institutions', ['Institution', 'Apprenants'], lignes_inst,
        )
        data['trends'] = {
            'evolution': self._chart_bar(
                'evolution', 'Nouveaux utilisateurs / mois', mois_labels, mois_data,
            ),
        }
        return data
