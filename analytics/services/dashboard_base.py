# analytics/services/dashboard_base.py
"""
BaseDashboardService — classe abstraite commune à tous les services Dashboard.
Fournit les helpers de construction JSON (KPI, chart, alerte, drill-down)
et les utilitaires de calcul (avg sécurisé, formatage date…).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from django.db.models import Avg, Count, Q, Sum

from .dashboard_context import DashboardContext


class BaseDashboardService:
    """
    Classe de base dont héritent tous les services Dashboard.
    Chaque sous-classe implémente :
        def build(self, filters: dict) -> dict
    """

    # Palette cohérente avec le design SOMAPRO 2026
    COLORS = [
        '#757fef',  # violet-blue  (primaire)
        '#00b69b',  # teal         (succès)
        '#ee368c',  # rose         (accent)
        '#2db6f5',  # ciel         (info)
        '#f59e0b',  # ambre        (warning)
        '#8b5cf6',  # violet       (secondaire)
        '#10b981',  # vert-émeraude
        '#ef4444',  # rouge        (danger)
    ]

    def __init__(self, ctx: DashboardContext):
        self.ctx = ctx
        self.now   = ctx.now
        self.today = ctx.today

    # ── Interface publique ──────────────────────────────────────────────────────

    def build(self, filters: dict) -> dict:
        raise NotImplementedError("Chaque service doit implémenter build()")

    # ── Constructeurs JSON ──────────────────────────────────────────────────────

    def _kpi(
        self,
        label:   str,
        value:   Any,
        icon:    str  = 'ri-bar-chart-line',
        color:   str  = '#757fef',
        trend:   str  = 'stable',   # 'up' | 'down' | 'stable'
        trend_val: Optional[str] = None,
        tooltip: str  = '',
        sub:     Optional[str] = None,
    ) -> dict:
        kpi: dict = {
            'label':   label,
            'value':   value,
            'icon':    icon,
            'color':   color,
            'trend':   trend,
            'tooltip': tooltip,
        }
        if trend_val is not None:
            kpi['trend_val'] = trend_val
        if sub is not None:
            kpi['sub'] = sub
        return kpi

    def _alert(
        self,
        type_:        str,   # 'info' | 'warning' | 'danger' | 'success'
        title:        str,
        message:      str,
        action_label: str = '',
        action_url:   str = '',
    ) -> dict:
        return {
            'type':         type_,
            'title':        title,
            'message':      message,
            'action_label': action_label,
            'action_url':   action_url,
            'timestamp':    self.now.isoformat(),
            'read':         False,
        }

    def _base(
        self,
        title:       str,
        description: str,
        kpis:        list,
        alerts:      Optional[list]  = None,
        charts:      Optional[list]  = None,
        sections:    Optional[dict]  = None,
    ) -> dict:
        payload: dict = {
            'title':        title,
            'description':  description,
            'kpis':         kpis,
            'charts':       charts or [],
            'alerts':       alerts or [],
            'annee':        self.ctx.annee_payload(),
            'last_updated': self.now.isoformat(),
        }
        if sections:
            payload.update(sections)
        return payload

    def _drill(self, titre: str, colonnes: list, lignes: list) -> dict:
        return {'titre': titre, 'colonnes': colonnes, 'lignes': lignes}

    # ── Charts ─────────────────────────────────────────────────────────────────

    def _chart_bar(
        self,
        id_:     str,
        title:   str,
        labels:  list,
        data:    list,
        color:   str = '#757fef',
    ) -> dict:
        return {
            'id':   id_,
            'type': 'bar',
            'title': title,
            'labels': labels,
            'datasets': [{'label': title, 'data': data, 'backgroundColor': color}],
        }

    def _chart_line(
        self,
        id_:      str,
        title:    str,
        labels:   list,
        datasets: list,   # [{label, data, color}]
    ) -> dict:
        return {
            'id':    id_,
            'type':  'line',
            'title': title,
            'labels': labels,
            'datasets': [
                {
                    'label': d['label'],
                    'data':  d['data'],
                    'borderColor': d.get('color', self.COLORS[i % len(self.COLORS)]),
                    'fill': d.get('fill', False),
                }
                for i, d in enumerate(datasets)
            ],
        }

    def _chart_donut(
        self,
        id_:     str,
        title:   str,
        labels:  list,
        data:    list,
        colors:  Optional[list] = None,
    ) -> dict:
        return {
            'id':     id_,
            'type':   'donut',
            'title':  title,
            'labels': labels,
            'datasets': [{
                'data':            data,
                'backgroundColor': colors or self.COLORS[:len(data)],
            }],
        }

    # ── Calculs ────────────────────────────────────────────────────────────────

    def _safe_avg(self, qs, field: str) -> float:
        r = qs.aggregate(v=Avg(field))['v']
        return round(r, 2) if r is not None else 0.0

    def _safe_sum(self, qs, field: str) -> int | float:
        r = qs.aggregate(v=Sum(field))['v']
        return r or 0

    def _pct(self, numerateur: int | float, denominateur: int | float) -> int:
        """Pourcentage entier, 0 si denominateur == 0."""
        if not denominateur:
            return 0
        return round(numerateur / denominateur * 100)

    # ── Temps ──────────────────────────────────────────────────────────────────

    def _ago(self, days: int):
        return self.now - timedelta(days=days)

    def _in(self, days: int):
        return self.now + timedelta(days=days)

    # ── Palette ────────────────────────────────────────────────────────────────

    def color(self, idx: int) -> str:
        return self.COLORS[idx % len(self.COLORS)]
