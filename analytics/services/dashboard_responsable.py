# analytics/services/dashboard_responsable.py
"""
DashboardResponsableService — pilotage académique.
Périmètre : institution du Responsable Académique connecté.
"""
from __future__ import annotations

from datetime import timedelta

from courses.utils import INSCRIPTION_ACTIVE_STATUSES
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q, Sum

from .dashboard_base import BaseDashboardService
from .dashboard_context import DashboardContext


class DashboardResponsableService(BaseDashboardService):

    def build(self, filters: dict) -> dict:
        from users.models import ResponsableAcademique, Apprenant, Formateur
        from courses.models import Cours, Module, Sequence, BlocContenu, Session, InscriptionCours, Participation
        from evaluations.models import Evaluation, PassageEvaluation
        from feedback.models import Feedback
        from progress.models import HistoriqueActivite
        from analytics.models import BlocAnalyticsSummary

        inst   = self.ctx.institution
        now    = self.now
        today  = self.today
        ago30  = now - timedelta(days=30)
        ago7   = now - timedelta(days=7)

        # ── Base querysets — périmètre institution ─────────────────────────────
        cours_qs = Cours.objects.filter(institution=inst)
        form_qs  = Formateur.objects.filter(institutions=inst)
        appr_qs  = Apprenant.objects.filter(institution=inst)
        insc_qs  = InscriptionCours.objects.filter(cours__institution=inst)
        part_qs  = Participation.objects.filter(session__cours__institution=inst)
        eval_qs  = Evaluation.objects.filter(cours__institution=inst)
        pass_qs  = PassageEvaluation.objects.filter(evaluation__cours__institution=inst)
        sess_qs  = Session.objects.filter(cours__institution=inst)
        mod_qs   = Module.objects.filter(cours__institution=inst)
        seq_qs   = Sequence.objects.filter(module__cours__institution=inst)
        bloc_qs  = BlocContenu.objects.filter(sequence__module__cours__institution=inst)
        feed_qs  = Feedback.objects.filter(cours__institution=inst)

        # ── Agrégations groupées ──────────────────────────────────────────────
        appr_agg   = appr_qs.aggregate(total=Count('id'), actifs=Count('id', filter=Q(is_active=True)))
        form_agg   = form_qs.aggregate(total=Count('id'), actifs=Count('id', filter=Q(is_active=True)))
        cours_agg  = cours_qs.aggregate(
            total=Count('id'),
            en_cours=Count('id', filter=Q(statut='en_cours')),
            planifies=Count('id', filter=Q(statut='planifie')),
            termines=Count('id', filter=Q(statut='termine')),
            en_retard=Count('id', filter=Q(statut__in=['en_cours', 'planifie'], date_fin__lt=today.isoformat())),
        )
        part_agg = part_qs.aggregate(total=Count('id'), presents=Count('id', filter=Q(statut='present')))
        pass_agg = pass_qs.aggregate(
            total=Count('id'),
            soumis=Count('id', filter=Q(statut='soumis')),
            corriges=Count('id', filter=Q(statut='corrige')),
        )
        insc_agg = insc_qs.aggregate(total=Count('id'), actif=Count('id', filter=Q(statut='actif')))

        appr_total     = appr_agg['total']
        app_actifs     = appr_agg['actifs']
        form_total     = form_agg['total']
        form_actifs_nb = form_agg['actifs']
        cours_actifs   = cours_agg['en_cours']
        cours_retard   = cours_agg['en_retard']
        taux_pres      = self._pct(part_agg['presents'], part_agg['total'])
        backlog        = pass_agg['soumis']
        insc_act       = insc_agg['actif']

        # Temps de consultation (30j)
        temps30h = round(
            self._safe_sum(
                HistoriqueActivite.objects.filter(apprenant__institution=inst, date_activite__gte=ago30),
                'duree_minutes',
            ) / 60
        )
        actifs30j = (
            HistoriqueActivite.objects.filter(apprenant__institution=inst, date_activite__gte=ago30)
            .values('apprenant').distinct().count()
        ) or app_actifs

        # Taux d'exécution moyen
        exec_vals = []
        for c in cours_qs.filter(statut='en_cours'):
            tx = getattr(c, 'taux_execution', None)
            if tx is not None and float(tx) > 0:
                val = float(tx)
                exec_vals.append(min(100, val * 100 if val <= 1 else val))
        exec_moy = round(sum(exec_vals) / len(exec_vals)) if exec_vals else 0

        # ── KPIs ──────────────────────────────────────────────────────────────
        kpis = [
            self._kpi('Apprenants actifs', app_actifs, 'ri-user-heart-line',
                      sub=f'{actifs30j} actifs 30j',
                      tooltip=f'Apprenants avec compte actif. {actifs30j} ont eu une activité dans les 30 derniers jours.'),
            self._kpi('Formateurs actifs', f'{form_actifs_nb} / {form_total}', 'ri-user-star-line',
                      sub=f'{form_total - form_actifs_nb} inactif(s)',
                      tooltip='Formateurs avec compte actif.'),
            self._kpi('Cours en cours', cours_actifs, 'ri-play-circle-line',
                      sub=f"{cours_agg['total']} total · {cours_retard} en retard",
                      trend='down' if cours_retard > 0 else 'stable',
                      tooltip=f"Cours en statut en_cours. {cours_retard} cours dépassent leur date de fin."),
            self._kpi('Taux de présence', f'{taux_pres}%', 'ri-calendar-check-line',
                      trend='down' if 0 < taux_pres < 70 else 'stable',
                      sub=f"{part_agg['total']} participations",
                      tooltip=f"{part_agg['presents']}/{part_agg['total']} présences. Objectif ≥ 70%."),
            self._kpi("Taux d'exécution moy.", f'{exec_moy}%', 'ri-bar-chart-fill',
                      trend='down' if 0 < exec_moy < 50 else 'stable',
                      sub='Avancement programme',
                      tooltip=f"Moyenne du taux d'exécution ({len(exec_vals)} cours avec données). Objectif ≥ 70%."),
            self._kpi('Temps consultation', f'{temps30h}h', 'ri-time-line',
                      sub='30 derniers jours',
                      tooltip='Temps total cumulé de consultation du contenu par tous les apprenants.'),
            self._kpi('À corriger', backlog, 'ri-edit-box-line',
                      trend='down' if backlog > 0 else 'stable',
                      sub='copies soumises',
                      tooltip='Copies soumises en attente de correction.'),
            self._kpi('Inscriptions actives', insc_act, 'ri-group-line',
                      sub=f"{insc_agg['total']} total",
                      tooltip=f"{insc_act} inscriptions actives sur {insc_agg['total']} total."),
        ]

        # ── Section Apprenants ────────────────────────────────────────────────
        top_cours_raw = (
            insc_qs.filter(statut__in=INSCRIPTION_ACTIVE_STATUSES)
            .values('cours__titre', 'cours__statut')
            .annotate(nb=Count('id'))
            .order_by('-nb')[:5]
        )
        section_apprenants = {
            'total': appr_total, 'actifs': app_actifs, 'inactifs': appr_total - app_actifs,
            'nouveaux_7j':  appr_qs.filter(date_joined__gte=ago7).count(),
            'nouveaux_30j': appr_qs.filter(date_joined__gte=ago30).count(),
            'taux_actifs':  self._pct(app_actifs, appr_total),
            'top_cours': [
                {'cours': r['cours__titre'] or '—', 'statut': r['cours__statut'], 'nb_inscrits': r['nb']}
                for r in top_cours_raw
            ],
        }

        # ── Section Formateurs ────────────────────────────────────────────────
        form_avec_cours_ids = set(cours_qs.filter(statut='en_cours').values_list('enseignant_id', flat=True))
        form_list = []
        for f in form_qs.order_by('-is_active', 'nom')[:12]:
            form_list.append({
                'nom':      f'{f.prenom} {f.nom}'.strip() or f.email,
                'cours':    cours_qs.filter(enseignant=f).count(),
                'sessions': sess_qs.filter(formateur=f).count(),
                'actif':    f.is_active,
            })

        section_formateurs = {
            'total': form_total, 'actifs': form_actifs_nb,
            'inactifs': form_total - form_actifs_nb,
            'sans_cours': form_qs.filter(is_active=True).exclude(id__in=form_avec_cours_ids).count(),
            'avg_cours': round(cours_agg['total'] / form_total, 1) if form_total else 0,
            'liste': form_list,
        }
        form_sans_cours_count = section_formateurs['sans_cours']

        # ── Section Cours & Contenu ───────────────────────────────────────────
        cours_total         = cours_agg['total']
        cours_avec_eval_ids = set(eval_qs.values_list('cours_id', flat=True))
        mod_cours_ids       = set(mod_qs.values_list('cours_id', flat=True))
        cours_sans_mod      = cours_qs.exclude(id__in=mod_cours_ids).count()
        cours_sans_form_nb  = cours_qs.filter(statut='en_cours', enseignant__isnull=True).count()
        cours_sans_eval     = cours_qs.filter(statut='en_cours').exclude(id__in=cours_avec_eval_ids).count()
        avg_appr_per_cours  = round(insc_qs.filter(statut__in=INSCRIPTION_ACTIVE_STATUSES).count() / cours_total, 1) if cours_total else 0

        section_cours_contenu = {
            'total': cours_total,
            'en_cours': cours_actifs,
            'planifies': cours_agg['planifies'],
            'termines': cours_agg['termines'],
            'en_retard': cours_retard,
            'sans_module': cours_sans_mod,
            'sans_formateur': cours_sans_form_nb,
            'sans_evaluation': cours_sans_eval,
            'avg_modules': round(mod_qs.count() / cours_total, 1) if cours_total else 0,
            'avg_apprenants': avg_appr_per_cours,
        }

        # ── Section Évaluations ───────────────────────────────────────────────
        pass_total_nb = pass_agg['total']
        pass_soumis   = pass_agg['soumis']
        pass_corriges = pass_agg['corriges']

        avg_note_pct = 0
        try:
            pct_qs = pass_qs.filter(statut='corrige', note__isnull=False, evaluation__bareme__gt=0).annotate(
                pct=ExpressionWrapper(F('note') / F('evaluation__bareme') * 100, output_field=FloatField())
            )
            r = pct_qs.aggregate(v=Avg('pct'))['v']
            avg_note_pct = round(r, 1) if r is not None else 0
        except Exception:
            pass

        section_evaluations = {
            'total': eval_qs.count(), 'publiees': eval_qs.filter(est_publiee=True).count(),
            'passages_total': pass_total_nb, 'passages_soumis': pass_soumis,
            'passages_corriges': pass_corriges,
            'taux_correction': self._pct(pass_corriges, pass_total_nb),
            'note_moy_pct': avg_note_pct,
        }

        # ── Section Sessions ──────────────────────────────────────────────────
        sess_total = sess_qs.count()
        now7       = now + timedelta(days=7)
        now30      = now + timedelta(days=30)
        form_map   = {str(f.id): f for f in form_qs}

        prochaines = []
        for s in sess_qs.filter(date_debut__gte=now).order_by('date_debut')[:5]:
            fid      = str(getattr(s, 'formateur_id', None) or '')
            form_obj = form_map.get(fid)
            prochaines.append({
                'cours':     s.cours.titre if getattr(s, 'cours_id', None) else '—',
                'date':      s.date_debut.strftime('%d/%m/%Y %H:%M') if s.date_debut else '—',
                'formateur': f'{form_obj.prenom} {form_obj.nom}'.strip() if form_obj else '—',
            })

        section_sessions = {
            'total': sess_total,
            'a_venir_7j':  sess_qs.filter(date_debut__gte=now, date_debut__lte=now7).count(),
            'a_venir_30j': sess_qs.filter(date_debut__gte=now, date_debut__lte=now30).count(),
            'passees':     sess_qs.filter(date_fin__lt=now).count(),
            'taux_presence': taux_pres,
            'prochaines': prochaines,
        }

        # ── Section Feedback ──────────────────────────────────────────────────
        feed_notes   = feed_qs.filter(note__isnull=False)
        nb_avec_note = feed_notes.count()
        avg_feed     = round(self._safe_avg(feed_notes, 'note'), 2) if nb_avec_note else 0
        rep_feed = []
        for n in range(1, 6):
            cnt = feed_notes.filter(note__gte=n, note__lt=n + 1).count()
            rep_feed.append({'note': n, 'count': cnt})
        max_cnt = max((r['count'] for r in rep_feed), default=1) or 1
        for r in rep_feed:
            r['pct'] = round(r['count'] / max_cnt * 100)
        section_feedback = {
            'total': feed_qs.count(), 'avec_note': nb_avec_note,
            'note_moyenne': avg_feed, 'repartition': rep_feed,
        }

        # ── Tendances 12 mois ─────────────────────────────────────────────────
        mois_labels, inscr_data, appr_data = [], [], []
        for i in range(11, -1, -1):
            d_start = (now - timedelta(days=i * 30)).date().replace(day=1)
            mois_labels.append(d_start.strftime('%b'))
            inscr_data.append(insc_qs.filter(
                date_inscription__year=d_start.year, date_inscription__month=d_start.month).count())
            try:
                appr_data.append(appr_qs.filter(
                    date_joined__year=d_start.year, date_joined__month=d_start.month).count())
            except Exception:
                appr_data.append(0)

        section_tendances = {
            'inscriptions_mois': self._chart_bar('inscriptions_mois', 'Inscriptions / mois', mois_labels, inscr_data),
            'apprenants_mois':   self._chart_bar('apprenants_mois', 'Nouveaux apprenants / mois', mois_labels, appr_data, '#00b69b'),
        }

        # ── Santé du contenu ──────────────────────────────────────────────────
        seq_mod_ids    = set(seq_qs.values_list('module_id', flat=True))
        bloc_seq_ids   = set(bloc_qs.values_list('sequence_id', flat=True))
        mods_sans_seq  = mod_qs.exclude(id__in=seq_mod_ids).count()
        seqs_sans_blocs = seq_qs.exclude(id__in=bloc_seq_ids).count()
        blocs_sans_dur = (bloc_qs.filter(duree_estimee_minutes__isnull=True).count() +
                          bloc_qs.filter(duree_estimee_minutes=0).count())
        blocs_consultes = set(
            BlocAnalyticsSummary.objects.filter(bloc__in=bloc_qs, nb_ouvertures__gt=0)
            .values_list('bloc_id', flat=True)
        )
        blocs_jamais = bloc_qs.count() - len(blocs_consultes)
        blocs_lents  = BlocAnalyticsSummary.objects.filter(bloc__in=bloc_qs, ratio_temps_pct__gt=130).count()

        sante_items = [
            {'label': 'Cours sans modules',          'count': cours_sans_mod,      'icon': 'ri-book-2-line',
             'severite': 'error' if cours_sans_mod > 0 else 'ok',
             'tooltip': f'{cours_sans_mod} cours sans module créé.'},
            {'label': 'Modules sans séquences',      'count': mods_sans_seq,       'icon': 'ri-layout-3-line',
             'severite': 'error' if mods_sans_seq > 0 else 'ok',
             'tooltip': f'{mods_sans_seq} module(s) sans séquence pédagogique.'},
            {'label': 'Séquences sans blocs',        'count': seqs_sans_blocs,     'icon': 'ri-stack-line',
             'severite': 'warning' if seqs_sans_blocs > 0 else 'ok',
             'tooltip': f'{seqs_sans_blocs} séquence(s) sans bloc de contenu.'},
            {'label': 'Cours actifs sans évaluation', 'count': cours_sans_eval,    'icon': 'ri-file-damage-line',
             'severite': 'warning' if cours_sans_eval > 0 else 'ok',
             'tooltip': f'{cours_sans_eval} cours en cours sans évaluation associée.'},
            {'label': 'Blocs sans durée estimée',    'count': blocs_sans_dur,      'icon': 'ri-timer-line',
             'severite': 'warning' if blocs_sans_dur > 10 else 'ok',
             'tooltip': f'{blocs_sans_dur} bloc(s) sans durée estimée.'},
            {'label': 'Blocs jamais consultés',      'count': max(0, blocs_jamais), 'icon': 'ri-eye-off-line',
             'severite': 'warning' if blocs_jamais > 0 else 'ok',
             'tooltip': f'{max(0, blocs_jamais)} bloc(s) jamais ouverts.'},
            {'label': 'Blocs trop lents (>130%)',    'count': blocs_lents,         'icon': 'ri-hourglass-2-line',
             'severite': 'warning' if blocs_lents > 0 else 'ok',
             'tooltip': f'{blocs_lents} bloc(s) dont le temps dépasse 130% du temps estimé.'},
            {'label': 'Formateurs actifs sans cours', 'count': form_sans_cours_count, 'icon': 'ri-user-unfollow-line',
             'severite': 'warning' if form_sans_cours_count > 0 else 'ok',
             'tooltip': f'{form_sans_cours_count} formateur(s) actif(s) sans cours assigné.'},
        ]
        errs  = sum(1 for s in sante_items if s['severite'] == 'error')
        warns = sum(1 for s in sante_items if s['severite'] == 'warning')
        sante_score = max(0, 100 - errs * 20 - warns * 8)

        # ── Tableau cours ──────────────────────────────────────────────────────
        lignes_cours = []
        for ci, c in enumerate(cours_qs.order_by('-id')[:15]):
            fid      = str(getattr(c, 'enseignant_id', None) or '')
            form_obj = form_map.get(fid)
            nb_app   = insc_qs.filter(cours=c, statut__in=INSCRIPTION_ACTIVE_STATUSES).count()
            nb_mod   = mod_qs.filter(cours=c).count()
            has_eval = c.id in cours_avec_eval_ids
            tx       = getattr(c, 'taux_execution', 0) or 0
            tx_norm  = min(100, int(float(tx) * 100 if float(tx) <= 1 else float(tx)))
            lignes_cours.append({
                'id': c.id, 'libelle': c.titre or f'Cours #{c.id}', 'value': tx_norm,
                'metadata': {
                    'statut': c.statut,
                    'formateur': f'{form_obj.prenom} {form_obj.nom}'.strip() if form_obj else '—',
                    'nb_modules': nb_mod, 'nb_apprenants': nb_app,
                    'has_eval': has_eval, 'taux_execution': tx_norm,
                    'couleur': self.color(ci),
                }
            })

        # ── Alertes ───────────────────────────────────────────────────────────
        alerts = []
        if backlog > 0:
            alerts.append(self._alert('warning', 'Copies à corriger',
                f'{backlog} évaluation(s) soumise(s) en attente.'))
        if cours_retard > 0:
            alerts.append(self._alert('danger', 'Cours en retard',
                f'{cours_retard} cours dépassent leur date de fin.'))
        if errs > 0:
            alerts.append(self._alert('danger', 'Problèmes de contenu',
                f'{errs} problème(s) critique(s) dans le contenu pédagogique.'))
        if form_sans_cours_count > 0:
            alerts.append(self._alert('info', 'Formateurs sans cours',
                f'{form_sans_cours_count} formateur(s) actif(s) sans cours assigné.'))

        # ── Assemblage final ──────────────────────────────────────────────────
        data = self._base('Dashboard Responsable Académique', 'Pilotage académique', kpis, alerts)
        data['sante_contenu'] = {'items': sante_items, 'score': sante_score}
        data['cours']         = self._drill('Tableau des cours', ['Cours', 'Formateur', 'Avancement'], lignes_cours)
        data['apprenants']    = section_apprenants
        data['formateurs']    = section_formateurs
        data['cours_contenu'] = section_cours_contenu
        data['evaluations']   = section_evaluations
        data['sessions']      = section_sessions
        data['feedback']      = section_feedback
        data['tendances']     = section_tendances
        return data
