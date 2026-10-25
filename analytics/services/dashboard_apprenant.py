# analytics/services/dashboard_apprenant.py
"""
DashboardApprenantService — vue personnelle de l'apprenant.
Périmètre strict : seules les données de cet apprenant.
Jamais de données d'autres apprenants de l'établissement.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .dashboard_base import BaseDashboardService
from .dashboard_context import DashboardContext


def _streak(dates_iso_set: set, from_date) -> int:
    """Nombre de jours consécutifs d'activité jusqu'à from_date."""
    count = 0
    d = from_date
    while d.isoformat() in dates_iso_set:
        count += 1
        d -= timedelta(days=1)
    return count


class DashboardApprenantService(BaseDashboardService):

    def build(self, filters: dict) -> dict:
        from courses.models import Cours, InscriptionCours, Session
        from courses.models import Module, Sequence, BlocContenu
        from evaluations.models import Evaluation, PassageEvaluation
        from progress.models import ProgressionApprenant, HistoriqueActivite, PlanAction
        from academics.models import AnneeScolaire

        appr   = self.ctx.profile   # Apprenant
        annee  = self.ctx.annee
        now    = self.now
        today  = self.today
        in7    = today + timedelta(days=7)
        ago7   = now - timedelta(days=7)
        ago30  = now - timedelta(days=30)
        week_start = today - timedelta(days=today.weekday())

        inst_first = getattr(appr, 'institution', None)
        annees_dispo = list(
            AnneeScolaire.objects
            .filter(institution=inst_first)
            .order_by('-date_debut', '-id')
            .values('id', 'annee_format_classique', 'est_active')
        ) if inst_first else []

        # ── Cours inscrits (filtrés par année) ───────────────────────────────
        insc_filter = {'apprenant': appr}
        if annee:
            insc_filter['annee_scolaire'] = annee
        inscriptions = InscriptionCours.objects.filter(**insc_filter).select_related('cours')
        cours_list   = [i.cours for i in inscriptions]
        cours_ids    = [c.id for c in cours_list]
        en_cours     = sum(1 for c in cours_list if c.statut == 'en_cours')
        planifies    = sum(1 for c in cours_list if c.statut == 'planifie')

        # ── Progression ───────────────────────────────────────────────────────
        if cours_ids:
            prog_qs = ProgressionApprenant.objects.filter(apprenant=appr, cours__in=cours_ids)
        else:
            prog_qs = ProgressionApprenant.objects.none()
        prog_map    = {p.cours_id: p for p in prog_qs.select_related('cours')}
        avg_comp    = self._safe_avg(prog_qs, 'pourcentage_completion')
        nb_termines = prog_qs.filter(statut='termine').count()

        # ── Historique d'activité ─────────────────────────────────────────────
        hist_base = HistoriqueActivite.objects.filter(apprenant=appr)
        if annee and getattr(annee, 'date_debut', None):
            hist_base = hist_base.filter(date_activite__gte=annee.date_debut)
            if getattr(annee, 'date_fin', None):
                hist_base = hist_base.filter(date_activite__lte=annee.date_fin)

        hist_agg = hist_base.aggregate(
            total_min=Sum('duree_minutes'),
            min_7j=Sum('duree_minutes', filter=Q(date_activite__gte=ago7)),
            min_30j=Sum('duree_minutes', filter=Q(date_activite__gte=ago30)),
            min_week=Sum('duree_minutes', filter=Q(date_activite__date__gte=week_start)),
        )
        temps_7j   = hist_agg['min_7j'] or 0
        temps_30j  = hist_agg['min_30j'] or 0
        temps_week = hist_agg['min_week'] or 0

        dates_actives = set(
            hist_base.values_list('date_activite__date', flat=True).distinct()
        )
        streak_nb = _streak({d.isoformat() for d in dates_actives}, today)

        # ── Sessions à venir ──────────────────────────────────────────────────
        sessions_proch = Session.objects.filter(
            cours__in=cours_ids,
            date_debut__date__gte=today,
            date_debut__date__lte=in7,
        ).count() if cours_ids else 0

        # ── Évaluations — UNIQUEMENT les passages de cet apprenant ───────────
        eval_qs = Evaluation.objects.filter(cours__in=cours_ids, est_publiee=True).filter(
            Q(date_debut__isnull=True) | Q(date_debut__date__lte=today),
            Q(date_fin__isnull=True)   | Q(date_fin__date__gte=today),
        ) if cours_ids else Evaluation.objects.none()

        pass_qs = PassageEvaluation.objects.filter(
            apprenant=appr,
            evaluation__cours__in=cours_ids,
        ) if cours_ids else PassageEvaluation.objects.none()

        pass_agg = pass_qs.aggregate(
            soumises=Count('id', filter=Q(statut='soumis')),
            corriges=Count('id', filter=Q(statut='corrige')),
        )
        soumises = pass_agg['soumises']
        corriges = pass_agg['corriges']

        # ── Plans d'action ────────────────────────────────────────────────────
        plan_qs = PlanAction.objects.filter(apprenant=appr)
        plans_retard = plan_qs.filter(
            statut__in=['a_faire', 'en_cours'],
            date_echeance__lt=today,
        ).count()

        # ── KPIs ──────────────────────────────────────────────────────────────
        kpis = [
            self._kpi('Cours actifs', f'{en_cours} cours', 'ri-play-circle-line',
                      sub=f'{planifies} planifié(s)' if planifies else None,
                      tooltip=f'En cours: {en_cours} | Planifiés: {planifies} | Total: {len(cours_list)}'),
            self._kpi('Progression globale', f'{avg_comp:.0f}%', 'ri-bar-chart-line',
                      trend='down' if avg_comp < 20 else 'stable',
                      tooltip=f'{nb_termines} cours terminé(s) sur {len(cours_list)}'),
            self._kpi('Temps passé 7j / 30j',
                      f'{temps_7j // 60}h / {temps_30j // 60}h', 'ri-time-line',
                      tooltip='Temps total de consultation du contenu'),
            self._kpi('Streak', f'{streak_nb}j', 'ri-fire-line',
                      sub='Super !' if streak_nb >= 7 else None,
                      tooltip=f"{streak_nb} jours consécutifs d'activité"),
            self._kpi('Sessions à venir (7j)', sessions_proch, 'ri-calendar-event-line',
                      tooltip='Sessions planifiées dans les 7 prochains jours'),
            self._kpi('Évaluations ouvertes', eval_qs.count(), 'ri-file-edit-line',
                      tooltip='Évaluations actuellement accessibles'),
            self._kpi('Soumises', soumises, 'ri-send-plane-line',
                      tooltip='Copies soumises en attente de correction'),
            self._kpi('Corrigées', corriges, 'ri-check-double-line',
                      trend='down' if soumises > 0 and corriges == 0 else 'stable',
                      tooltip='Copies corrigées par le formateur'),
        ]

        # ── Alertes ───────────────────────────────────────────────────────────
        alerts = []
        if plans_retard:
            alerts.append(self._alert('danger', "Plans d'action en retard",
                f'{plans_retard} plan(s) dépassé(s).', 'Voir', '/formations/cours'))
        if soumises > 0 and corriges == 0:
            alerts.append(self._alert('warning', 'Copies en attente',
                f'{soumises} copie(s) soumise(s) pas encore corrigée(s).'))
        if avg_comp < 20 and len(cours_list) > 0:
            alerts.append(self._alert('info', 'Progression faible',
                f'Votre progression globale est de {avg_comp:.0f}%. Continuez !'))

        # ── Temps d'apprentissage par cours ───────────────────────────────────
        try:
            from analytics.models import BlocAnalyticsSummary as BAS
            temps_par_cours = {
                row['bloc__sequence__module__cours_id']: row['total']
                for row in BAS.objects.filter(
                    apprenant=appr,
                    bloc__sequence__module__cours_id__in=cours_ids,
                ).values('bloc__sequence__module__cours_id')
                 .annotate(total=Sum('duree_totale_sec'))
            } if cours_ids else {}
        except Exception:
            temps_par_cours = {}

        # ── Blocs complétés cette semaine ─────────────────────────────────────
        try:
            from progress.models import BlocProgress
            blocs_semaine = BlocProgress.objects.filter(
                apprenant=appr,
                est_termine=True,
                updated_at__date__gte=week_start,
                bloc__sequence__module__cours_id__in=cours_ids,
            ).count() if cours_ids else 0
        except Exception:
            blocs_semaine = 0

        # ── Progression par cours (drill-down) ────────────────────────────────
        COLORS = self.COLORS
        lignes_prog = []
        for ci, cours in enumerate(cours_list):
            prog      = prog_map.get(cours.id)
            pct       = int(prog.pourcentage_completion) if prog else 0
            temps_sec = temps_par_cours.get(cours.id, 0) or 0
            lignes_prog.append({
                'id': cours.id,
                'libelle': cours.titre or f'Cours #{cours.id}',
                'value': pct,
                'metadata': {
                    'pct_blocs':    pct,
                    'statut':       cours.statut,
                    'derniere_activite': prog.date_derniere_activite.isoformat() if prog else None,
                    'note_moyenne': float(prog.note_moyenne_evaluations or 0) if prog else 0,
                    'taux_quiz':    float(prog.taux_reussite_quiz or 0) if prog else 0,
                    'couleur':      COLORS[ci % len(COLORS)],
                    'temps_apprentissage_sec': temps_sec,
                    'temps_apprentissage_h':   round(temps_sec / 3600, 2),
                    'volume_prevu_h':  getattr(cours, 'volume_horaire', 0) or 0,
                    'taux_execution_ens': getattr(cours, 'taux_execution', None),
                }
            })

        # ── Historique récent ──────────────────────────────────────────────────
        lignes_hist = []
        for act in hist_base.order_by('-date_activite')[:7]:
            lignes_hist.append({
                'id': act.id,
                'libelle': act.description or act.get_type_activite_display(),
                'metadata': {
                    'type': act.type_activite,
                    'date': act.date_activite.isoformat(),
                    'duree': act.duree_minutes,
                }
            })

        # ── Plans d'action ─────────────────────────────────────────────────────
        lignes_plans = []
        for p in plan_qs.order_by('date_echeance')[:5]:
            en_retard = bool(
                p.date_echeance and p.date_echeance < today and p.statut in ('a_faire', 'en_cours')
            )
            lignes_plans.append({
                'id': p.id, 'libelle': p.titre,
                'metadata': {
                    'statut': p.statut,
                    'date_echeance': p.date_echeance.isoformat() if p.date_echeance else None,
                    'en_retard': en_retard,
                }
            })

        # ── Chart activité 7 jours ────────────────────────────────────────────
        chart_labels, chart_data = [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            chart_labels.append(d.strftime('%a'))
            r = hist_base.filter(date_activite__date=d).aggregate(v=Sum('duree_minutes'))['v']
            chart_data.append(int(r or 0))

        charts = [self._chart_bar('activity_week', 'Activité 7j (minutes)', chart_labels, chart_data)]

        # ── Passages évaluations ──────────────────────────────────────────────
        passages_detail = []
        for p in pass_qs.select_related('evaluation', 'evaluation__cours').order_by('-date_soumission', '-date_debut')[:15]:
            passages_detail.append({
                'evaluation': p.evaluation.titre,
                'cours':      p.evaluation.cours.titre if getattr(p.evaluation, 'cours_id', None) else '—',
                'statut':     p.statut,
                'note':       float(p.note) if p.note is not None else None,
                'bareme':     float(p.evaluation.bareme) if getattr(p.evaluation, 'bareme', None) else 20.0,
                'date':       p.date_soumission.isoformat() if p.date_soumission else None,
            })

        # ── Assemblage final ──────────────────────────────────────────────────
        data = self._base('Mon Dashboard', 'Ma progression personnelle', kpis, alerts, charts)
        data['progression']  = self._drill('Mes cours', ['Cours', 'Progression'], lignes_prog)
        data['historique']   = self._drill('Activité récente', ['Activité', 'Date'], lignes_hist)
        data['plans_action'] = self._drill("Plans d'action", ['Plan', 'Échéance'], lignes_plans)
        data['blocsWeek']    = blocs_semaine
        data['tempsWeekH']   = round(float(temps_week) / 60, 1)
        data['evaluations']  = {
            'ouvertes': eval_qs.count(),
            'soumises': soumises,
            'corriges': corriges,
            'passages': passages_detail,
        }
        data['activite'] = {
            'temps_7j_h':      round(float(temps_7j)   / 60, 1),
            'temps_30j_h':     round(float(temps_30j)  / 60, 1),
            'temps_semaine_h': round(float(temps_week) / 60, 1),
            'streak':          streak_nb,
            'chart_labels':    chart_labels,
            'chart_data':      chart_data,
        }
        data['annee_scolaire']     = self.ctx.annee_payload()
        data['annees_disponibles'] = annees_dispo
        return data
