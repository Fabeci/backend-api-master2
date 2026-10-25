# analytics/services/dashboard_formateur.py
"""
DashboardFormateurService — périmètre strict : cours de ce formateur,
filtrés par l'année scolaire active ou sélectionnée.
"""
from __future__ import annotations

from datetime import timedelta

from courses.utils import INSCRIPTION_ACTIVE_STATUSES
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q, Sum

from .dashboard_base import BaseDashboardService
from .dashboard_context import DashboardContext


def _streak(dates_iso_set: set, from_date) -> int:
    """Nombre de jours consécutifs de connexion jusqu'à from_date."""
    from datetime import timedelta
    count = 0
    d = from_date
    while d.isoformat() in dates_iso_set:
        count += 1
        d -= timedelta(days=1)
    return count


class DashboardFormateurService(BaseDashboardService):

    def build(self, filters: dict) -> dict:
        from courses.models import Cours, Session, InscriptionCours
        from courses.models import Module, Sequence, BlocContenu, Participation
        from evaluations.models import Evaluation, PassageEvaluation
        from progress.models import ProgressionApprenant
        from analytics.models import BlocAnalyticsSummary
        from feedback.models import Feedback
        from academics.models import AnneeScolaire

        form    = self.ctx.profile   # Formateur
        annee   = self.ctx.annee
        now     = self.now
        today   = self.today
        in7     = now + timedelta(days=7)
        in30    = now + timedelta(days=30)

        # Résolution de l'institution pour les années disponibles
        inst_first = getattr(annee, 'institution', None) or form.institutions.first()
        annees_dispo = list(
            AnneeScolaire.objects
            .filter(institution=inst_first)
            .order_by('-date_debut', '-id')
            .values('id', 'annee_format_classique', 'est_active')
        ) if inst_first else []

        # ── Querysets — périmètre formateur + année ────────────────────────────
        if annee:
            cours_qs = Cours.objects.filter(enseignant=form, annee_scolaire=annee)
            sess_qs  = Session.objects.filter(formateur=form, annee_scolaire=annee)
            eval_qs  = Evaluation.objects.filter(enseignant=form, cours__annee_scolaire=annee)
            insc_qs  = InscriptionCours.objects.filter(cours__enseignant=form, annee_scolaire=annee)
            pass_qs  = PassageEvaluation.objects.filter(evaluation__enseignant=form, evaluation__cours__annee_scolaire=annee)
            prog_qs  = ProgressionApprenant.objects.filter(cours__enseignant=form, cours__annee_scolaire=annee)
            part_qs  = Participation.objects.filter(session__formateur=form, session__annee_scolaire=annee)
        else:
            cours_qs = Cours.objects.filter(enseignant=form)
            sess_qs  = Session.objects.filter(formateur=form)
            eval_qs  = Evaluation.objects.filter(enseignant=form)
            insc_qs  = InscriptionCours.objects.filter(cours__enseignant=form)
            pass_qs  = PassageEvaluation.objects.filter(evaluation__enseignant=form)
            prog_qs  = ProgressionApprenant.objects.filter(cours__enseignant=form)
            part_qs  = Participation.objects.filter(session__formateur=form)

        # ── Agrégations groupées ──────────────────────────────────────────────
        cours_agg = cours_qs.aggregate(
            total=Count('id'),
            en_cours=Count('id', filter=Q(statut='en_cours')),
            planifies=Count('id', filter=Q(statut='planifie')),
            termines=Count('id', filter=Q(statut='termine')),
            annules=Count('id', filter=Q(statut='annule')),
        )
        pass_agg = pass_qs.aggregate(
            total=Count('id'),
            soumis=Count('id', filter=Q(statut='soumis')),
            corriges=Count('id', filter=Q(statut='corrige')),
        )
        part_agg = part_qs.aggregate(total=Count('id'), presents=Count('id', filter=Q(statut='present')))

        nb_cours             = cours_agg['total']
        en_cours             = cours_agg['en_cours']
        planifies            = cours_agg['planifies']
        termines             = cours_agg['termines']
        annules              = cours_agg['annules']
        backlog              = pass_agg['soumis']
        corriges             = pass_agg['corriges']
        taux_pres            = self._pct(part_agg['presents'], part_agg['total'])
        nb_apprenants_actifs = insc_qs.filter(statut='actif').values('apprenant').distinct().count()
        taux_completion      = self._safe_avg(prog_qs, 'pourcentage_completion')
        sessions_proch       = sess_qs.filter(date_debut__gte=now, date_debut__lte=in7).count()
        sessions_auj         = sess_qs.filter(date_debut__date=today).count()

        evals_actives = eval_qs.filter(est_publiee=True).filter(
            Q(date_debut__isnull=True) | Q(date_debut__date__lte=today),
            Q(date_fin__isnull=True)   | Q(date_fin__date__gte=today),
        ).count()

        # Blocs à retravailler
        blocs_ids = list(
            BlocContenu.objects.filter(sequence__module__cours__in=cours_qs).values_list('id', flat=True)
        )
        blocs_prob = BlocAnalyticsSummary.objects.filter(bloc_id__in=blocs_ids).filter(
            Q(nb_ouvertures__gt=0, nb_completions=0) | Q(ratio_temps_pct__gt=130)
        ).count()

        # ── KPIs ──────────────────────────────────────────────────────────────
        kpis = [
            self._kpi('Cours actifs', en_cours, 'ri-play-circle-line',
                      sub=f'{nb_cours} cours au total',
                      tooltip=f'En cours: {en_cours} | Planifiés: {planifies} | Terminés: {termines} | Annulés: {annules}'),
            self._kpi('Apprenants actifs', nb_apprenants_actifs, 'ri-group-line',
                      sub='dans vos cours',
                      tooltip='Apprenants avec inscription active dans au moins un de vos cours'),
            self._kpi('Taux de complétion', f'{taux_completion:.0f}%' if taux_completion else '—',
                      'ri-checkbox-circle-line',
                      trend='down' if taux_completion > 0 and taux_completion < 30 else 'stable',
                      tooltip='Progression moyenne des apprenants sur vos cours'),
            self._kpi('Sessions à venir (7j)', sessions_proch, 'ri-calendar-event-line',
                      sub=f"{sessions_auj} aujourd'hui · {sess_qs.count()} total",
                      tooltip='Sessions planifiées dans les 7 prochains jours'),
            self._kpi('Taux de présence', f'{taux_pres}%' if part_agg['total'] else '—',
                      'ri-calendar-check-line',
                      trend='down' if taux_pres > 0 and taux_pres < 70 else 'stable',
                      sub=f"{part_agg['presents']} présent(s)" if part_agg['total'] else 'Aucune donnée',
                      tooltip=f"Présence globale: {part_agg['presents']}/{part_agg['total']} participations"),
            self._kpi('Évaluations actives', evals_actives, 'ri-file-edit-line',
                      sub=f'{eval_qs.count()} au total',
                      tooltip='Évaluations publiées et actuellement accessibles'),
            self._kpi('À corriger', backlog, 'ri-edit-box-line',
                      trend='down' if backlog > 0 else 'stable',
                      sub=f'{pass_agg["total"]} passage(s) total',
                      tooltip=f'{backlog} en attente · {corriges} corrigé(s)'),
            self._kpi('Blocs à retravailler', blocs_prob, 'ri-alert-line',
                      trend='down' if blocs_prob > 0 else 'stable',
                      tooltip='Blocs jamais complétés après ouverture ou trop lents (>130% du temps estimé)'),
        ]

        # ── Section Apprenants ────────────────────────────────────────────────
        appr_total      = insc_qs.values('apprenant').distinct().count()
        appr_termines   = insc_qs.filter(statut='termine').values('apprenant').distinct().count()
        appr_abandonnes = insc_qs.filter(statut='abandonne').values('apprenant').distinct().count()
        progression_moy = round(float(self._safe_avg(prog_qs, 'pourcentage_completion')), 1)
        temps_moy_min   = round(float(self._safe_avg(prog_qs, 'temps_total_minutes')), 0)

        top_cours_appr = (
            insc_qs.filter(statut__in=INSCRIPTION_ACTIVE_STATUSES)
            .values('cours__titre', 'cours__statut')
            .annotate(nb=Count('apprenant', distinct=True))
            .order_by('-nb')[:5]
        )
        section_apprenants = {
            'total': appr_total, 'actifs': nb_apprenants_actifs,
            'termines': appr_termines, 'abandonnes': appr_abandonnes,
            'progression_moy': progression_moy,
            'temps_moy_minutes': int(temps_moy_min),
            'top_cours': [
                {'cours': r['cours__titre'] or '—', 'statut': r['cours__statut'], 'nb_apprenants': r['nb']}
                for r in top_cours_appr
            ],
        }

        # ── Section Sessions & Présence ───────────────────────────────────────
        pres_par_cours = []
        for c in cours_qs.filter(statut='en_cours').order_by('titre'):
            p_c  = part_qs.filter(session__cours=c)
            pres = p_c.filter(statut='present').count()
            tot  = p_c.count()
            pres_par_cours.append({
                'cours': c.titre or f'Cours #{c.id}',
                'taux': self._pct(pres, tot),
                'presents': pres, 'total': tot,
            })

        prochaines_sess = []
        for s in sess_qs.filter(date_debut__gte=now).order_by('date_debut')[:5]:
            prochaines_sess.append({
                'cours': s.cours.titre if getattr(s, 'cours_id', None) else '—',
                'date':  s.date_debut.strftime('%d/%m/%Y %H:%M') if s.date_debut else '—',
                'mode':  getattr(s, 'participation_mode', '—') or '—',
            })

        section_sessions = {
            'total': sess_qs.count(),
            'a_venir_7j': sessions_proch,
            'a_venir_30j': sess_qs.filter(date_debut__gte=now, date_debut__lte=in30).count(),
            'passees': sess_qs.filter(date_fin__lt=now).count(),
            'taux_presence': taux_pres,
            'pres_par_cours': pres_par_cours,
            'prochaines': prochaines_sess,
        }

        # ── Section Évaluations ───────────────────────────────────────────────
        pass_total_nb = pass_agg['total']

        avg_note_pct = 0
        dist_notes   = []
        try:
            pct_qs2 = pass_qs.filter(statut='corrige', note__isnull=False, evaluation__bareme__gt=0).annotate(
                pct=ExpressionWrapper(F('note') / F('evaluation__bareme') * 100, output_field=FloatField())
            )
            avg_v = pct_qs2.aggregate(v=Avg('pct'))['v']
            avg_note_pct = round(float(avg_v), 1) if avg_v else 0

            for lo, hi, lbl in [(0,20,'0-19%'),(20,40,'20-39%'),(40,60,'40-59%'),(60,80,'60-79%'),(80,101,'80-100%')]:
                dist_notes.append({'label': lbl, 'count': pct_qs2.filter(pct__gte=lo, pct__lt=hi).count()})
            max_dist = max((d['count'] for d in dist_notes), default=1) or 1
            for d in dist_notes:
                d['pct'] = round(d['count'] / max_dist * 100)
        except Exception:
            pass

        section_evaluations = {
            'total': eval_qs.count(), 'publiees': eval_qs.filter(est_publiee=True).count(),
            'actives': evals_actives,
            'passages_total': pass_total_nb, 'passages_soumis': backlog, 'passages_corriges': corriges,
            'taux_correction': self._pct(corriges, pass_total_nb),
            'note_moy_pct': avg_note_pct,
            'distribution_notes': dist_notes,
        }

        # ── Section Contenu ───────────────────────────────────────────────────
        mod_qs_f  = Module.objects.filter(cours__in=cours_qs)
        seq_qs_f  = Sequence.objects.filter(module__in=mod_qs_f)
        bloc_qs_f = BlocContenu.objects.filter(sequence__in=seq_qs_f)
        blocs_ids2 = list(bloc_qs_f.values_list('id', flat=True))
        ana_qs     = BlocAnalyticsSummary.objects.filter(bloc_id__in=blocs_ids2)

        nb_blocs_tot    = bloc_qs_f.count()
        blocs_jamais_vis = nb_blocs_tot - ana_qs.filter(nb_ouvertures__gt=0).values('bloc').distinct().count()

        section_contenu = {
            'nb_modules': mod_qs_f.count(),
            'nb_sequences': seq_qs_f.count(),
            'nb_blocs': nb_blocs_tot,
            'blocs_jamais_vus': max(0, blocs_jamais_vis),
            'blocs_trop_lents': ana_qs.filter(ratio_temps_pct__gt=130).count(),
            'blocs_non_completes': ana_qs.filter(nb_ouvertures__gt=0, nb_completions=0).count(),
        }

        # ── Section Feedback ──────────────────────────────────────────────────
        feed_qs2 = Feedback.objects.filter(cours__in=cours_qs)
        feed_notes = feed_qs2.filter(note__isnull=False)
        avg_feed = round(float(self._safe_avg(feed_notes, 'note')), 2) if feed_notes.count() else 0
        rep_feed = []
        for n in range(1, 6):
            cnt = feed_notes.filter(note__gte=n, note__lt=n + 1).count()
            rep_feed.append({'note': n, 'count': cnt})
        max_fb = max((r['count'] for r in rep_feed), default=1) or 1
        for r in rep_feed:
            r['pct'] = round(r['count'] / max_fb * 100)
        section_feedback = {
            'total': feed_qs2.count(), 'note_moyenne': avg_feed, 'repartition': rep_feed,
        }

        # ── Drill-down cours enrichi ───────────────────────────────────────────
        lignes_cours = []
        for ci, c in enumerate(cours_qs.order_by('-id')):
            nb_insc   = insc_qs.filter(cours=c, statut='actif').count()
            prog_c    = prog_qs.filter(cours=c)
            taux_c    = self._safe_avg(prog_c, 'pourcentage_completion')
            sess_c    = sess_qs.filter(cours=c).count()
            eval_c    = eval_qs.filter(cours=c).count()
            pass_c    = pass_qs.filter(evaluation__cours=c)
            backlog_c = pass_c.filter(statut='soumis').count()
            part_c    = part_qs.filter(session__cours=c)
            pres_c    = part_c.filter(statut='present').count()
            taux_pc   = self._pct(pres_c, part_c.count())
            nb_blocs  = BlocContenu.objects.filter(sequence__module__cours=c).count()
            jamais    = nb_blocs - BlocAnalyticsSummary.objects.filter(
                bloc__sequence__module__cours=c, nb_ouvertures__gt=0
            ).values('bloc').distinct().count()

            ens = c.indicateurs_enseignement() if hasattr(c, 'indicateurs_enseignement') else {}

            lignes_cours.append({
                'id': c.id, 'libelle': c.titre or f'Cours #{c.id}',
                'value': int(taux_c),
                'metadata': {
                    'statut': c.statut,
                    'nb_apprenants': nb_insc,
                    'taux_completion': int(taux_c),
                    'nb_sessions': sess_c, 'nb_evals': eval_c,
                    'nb_passages': pass_c.count(), 'backlog': backlog_c,
                    'taux_presence': taux_pc,
                    'jamais_consultes': max(0, jamais),
                    'couleur': self.color(ci),
                    'groupes_noms': [str(c.groupe)] if getattr(c, 'groupe', None) else [],
                    'volume_prevu_h':      ens.get('volume_prevu_h', 0),
                    'volume_realise_h':    ens.get('volume_realise_h', 0),
                    'volume_restant_h':    ens.get('volume_restant_h', 0),
                    'taux_execution_pct':  ens.get('taux_execution_pct', 0),
                    'nb_seances_realisees': ens.get('nb_seances_realisees', 0),
                    'nb_seances_total':    ens.get('nb_seances_total', 0),
                }
            })

        # ── Alertes ───────────────────────────────────────────────────────────
        alerts = []
        if backlog > 0:
            alerts.append(self._alert('warning', 'Copies à corriger',
                f'{backlog} évaluation(s) en attente de correction.'))
        if taux_pres > 0 and taux_pres < 70:
            alerts.append(self._alert('danger', 'Taux de présence faible',
                f'Taux de présence à {taux_pres}% (objectif ≥ 70%).'))
        if blocs_jamais_vis > 0:
            alerts.append(self._alert('info', 'Contenu non consulté',
                f'{max(0, blocs_jamais_vis)} bloc(s) jamais ouvert(s) par vos apprenants.'))
        if appr_abandonnes > 0:
            alerts.append(self._alert('warning', 'Abandons',
                f'{appr_abandonnes} apprenant(s) ont abandonné un de vos cours.'))

        # ── Assemblage final ──────────────────────────────────────────────────
        data = self._base('Dashboard Formateur', 'Mes cours et apprenants', kpis, alerts)
        data['mes_cours']          = self._drill('Mes cours', ['Cours', 'Apprenants', 'Complétion'], lignes_cours)
        data['apprenants']         = section_apprenants
        data['sessions']           = section_sessions
        data['evaluations']        = section_evaluations
        data['contenu']            = section_contenu
        data['feedback']           = section_feedback
        data['annee_scolaire']     = self.ctx.annee_payload()
        data['annees_disponibles'] = annees_dispo
        return data
