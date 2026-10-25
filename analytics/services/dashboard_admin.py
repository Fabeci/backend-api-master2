# analytics/services/dashboard_admin.py
"""
DashboardAdminService — dashboard filtré sur l'institution de l'admin.
Toutes les statistiques sont scoped à inst = ctx.institution.
"""
from __future__ import annotations

from datetime import timedelta

from courses.utils import INSCRIPTION_ACTIVE_STATUSES
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q, Sum

from .dashboard_base import BaseDashboardService
from .dashboard_context import DashboardContext


class DashboardAdminService(BaseDashboardService):

    def build(self, filters: dict) -> dict:
        from users.models import Apprenant, Formateur, ResponsableAcademique, Parent
        from courses.models import Cours, Session, InscriptionCours, Module, Participation
        from academics.models import Classe
        from evaluations.models import Evaluation, PassageEvaluation
        from feedback.models import Feedback

        inst  = self.ctx.institution
        now   = self.now
        today = self.today
        in7   = now + timedelta(days=7)
        in30  = now + timedelta(days=30)
        ago7  = now - timedelta(days=7)
        ago30 = now - timedelta(days=30)

        # ── Base querysets — périmètre institution ─────────────────────────────
        appr_qs  = Apprenant.objects.filter(institution=inst)
        form_qs  = Formateur.objects.filter(institutions=inst)
        resp_qs  = ResponsableAcademique.objects.filter(institution=inst)
        par_qs   = Parent.objects.filter(institution=inst)
        cours_qs = Cours.objects.filter(institution=inst)
        class_qs = Classe.objects.filter(institution=inst)
        sess_qs  = Session.objects.filter(institution=inst)
        insc_qs  = InscriptionCours.objects.filter(cours__institution=inst)
        eval_qs  = Evaluation.objects.filter(cours__institution=inst)
        pass_qs  = PassageEvaluation.objects.filter(evaluation__cours__institution=inst)
        part_qs  = Participation.objects.filter(session__cours__institution=inst)
        feed_qs  = Feedback.objects.filter(cours__institution=inst)

        # ── Agrégations groupées (un seul passage en base par bloc) ───────────
        user_counts = {
            'appr_total':   appr_qs.count(),
            'appr_actifs':  appr_qs.filter(is_active=True).count(),
            'frm_actifs':   form_qs.filter(is_active=True).count(),
            'frm_total':    form_qs.count(),
            'resp_actifs':  resp_qs.filter(is_active=True).count(),
            'par_actifs':   par_qs.filter(is_active=True).count(),
            'inactifs_form': form_qs.filter(is_active=False).count(),
            'inactifs_resp': resp_qs.filter(is_active=False).count(),
            'inactifs_par':  par_qs.filter(is_active=False).count(),
            'inactifs_appr': appr_qs.filter(is_active=False).count(),
        }
        all_inactifs = (
            user_counts['inactifs_appr'] + user_counts['inactifs_form'] +
            user_counts['inactifs_resp'] + user_counts['inactifs_par']
        )

        cours_counts = cours_qs.aggregate(
            total=Count('id'),
            en_cours=Count('id', filter=Q(statut='en_cours')),
            planifies=Count('id', filter=Q(statut='planifie')),
            termines=Count('id', filter=Q(statut='termine')),
        )
        nb_classes   = class_qs.count()
        sess_proch   = sess_qs.filter(date_debut__gte=now, date_debut__lte=in7).count()

        insc_counts = insc_qs.aggregate(
            total=Count('id'),
            actif=Count('id', filter=Q(statut='actif')),
            diplome=Count('id', filter=Q(statut__in=['diplome', 'diplomé'])),
            retire=Count('id', filter=Q(statut__in=['retire', 'retiré'])),
            new7j=Count('id', filter=Q(date_inscription__gte=ago7)),
            new30j=Count('id', filter=Q(date_inscription__gte=ago30)),
        )

        pass_counts = pass_qs.aggregate(
            total=Count('id'),
            soumis=Count('id', filter=Q(statut='soumis')),
            corriges=Count('id', filter=Q(statut='corrige')),
        )
        part_total = part_qs.count()
        presents   = part_qs.filter(statut='present').count()
        taux_pres  = self._pct(presents, part_total)

        appr_avec_groupe = appr_qs.exclude(Q(groupe__isnull=True)).count()
        taux_couverture  = self._pct(appr_avec_groupe, user_counts['appr_total'])

        # ── KPIs ──────────────────────────────────────────────────────────────
        kpis = [
            self._kpi('Apprenants actifs',   user_counts['appr_actifs'],  'ri-user-line',
                      tooltip=f"{user_counts['appr_actifs']}/{user_counts['appr_total']} actifs sur la plateforme"),
            self._kpi('Formateurs actifs',   user_counts['frm_actifs'],   'ri-user-star-line',
                      tooltip='Formateurs avec compte actif'),
            self._kpi('Responsables actifs', user_counts['resp_actifs'],  'ri-shield-user-line',
                      tooltip='Responsables académiques actifs'),
            self._kpi('Cours actifs',        cours_counts['en_cours'],    'ri-book-open-line',
                      sub=f"{cours_counts['total']} total",
                      tooltip='Cours actuellement en cours'),
            self._kpi('Sessions à venir',    sess_proch,                  'ri-calendar-event-line',
                      tooltip='Sessions planifiées dans les 7 prochains jours'),
            self._kpi('Classes',             nb_classes,                  'ri-building-4-line',
                      tooltip="Classes actives dans l'institution"),
            self._kpi('Parents actifs',      user_counts['par_actifs'],   'ri-parent-line',
                      tooltip='Parents avec compte actif'),
            self._kpi('Comptes en attente',  all_inactifs,                'ri-time-line',
                      trend='down' if all_inactifs > 0 else 'stable',
                      tooltip='Comptes non encore activés (tous rôles confondus)'),
        ]

        # ── Section Apprenants ────────────────────────────────────────────────
        nb_appr       = user_counts['appr_total']
        appr_actifs   = user_counts['appr_actifs']
        taux_actifs_a = self._pct(appr_actifs, nb_appr)

        top_cours_insc = []
        for c in cours_qs.order_by('-id')[:6]:
            nb = insc_qs.filter(cours=c, statut__in=INSCRIPTION_ACTIVE_STATUSES).count()
            top_cours_insc.append({'cours': c.titre or f'Cours #{c.id}', 'statut': c.statut, 'nb_inscrits': nb})
        top_cours_insc.sort(key=lambda x: x['nb_inscrits'], reverse=True)

        section_apprenants = {
            'total': nb_appr, 'actifs': appr_actifs, 'inactifs': nb_appr - appr_actifs,
            'nouveaux_7j':  appr_qs.filter(date_joined__gte=ago7).count(),
            'nouveaux_30j': appr_qs.filter(date_joined__gte=ago30).count(),
            'taux_actifs': taux_actifs_a, 'top_cours': top_cours_insc,
        }

        # ── Section Formateurs ────────────────────────────────────────────────
        cours_by_form = {}
        for c in cours_qs.values('enseignant_id'):
            fid = c['enseignant_id']
            if fid:
                cours_by_form[fid] = cours_by_form.get(fid, 0) + 1

        form_liste = []
        for f in form_qs.order_by('-is_active', '-id')[:10]:
            nb_c = cours_by_form.get(f.id, 0)
            nb_s = sess_qs.filter(formateur=f).count()
            form_liste.append({
                'nom': f'{f.prenom} {f.nom}'.strip() or f.email,
                'cours': nb_c, 'sessions': nb_s, 'actif': f.is_active,
            })

        nb_form = user_counts['frm_total']
        section_formateurs = {
            'total': nb_form, 'actifs': user_counts['frm_actifs'],
            'inactifs': nb_form - user_counts['frm_actifs'],
            'sans_cours': form_qs.filter(is_active=True).exclude(id__in=list(cours_by_form)).count(),
            'avg_cours': round(sum(cours_by_form.values()) / len(cours_by_form), 1) if cours_by_form else 0,
            'liste': form_liste,
        }

        # ── Section Cours & Contenu ───────────────────────────────────────────
        mod_qs = Module.objects.filter(cours__institution=inst)
        mod_cours_ids = set(mod_qs.values_list('cours_id', flat=True))
        cours_avec_eval_ids = set(eval_qs.values_list('cours_id', flat=True))
        nb_cours_total = cours_counts['total']

        section_cours_contenu = {
            'total': nb_cours_total,
            'en_cours': cours_counts['en_cours'],
            'planifies': cours_counts['planifies'],
            'termines': cours_counts['termines'],
            'sans_module': cours_qs.exclude(id__in=mod_cours_ids).count(),
            'sans_formateur': cours_qs.filter(Q(enseignant__isnull=True), statut='en_cours').count(),
            'sans_evaluation': cours_qs.filter(statut='en_cours').exclude(id__in=cours_avec_eval_ids).count(),
            'avg_modules': round(mod_qs.count() / nb_cours_total, 1) if nb_cours_total else 0,
            'avg_apprenants': round(insc_counts['total'] / nb_cours_total, 1) if nb_cours_total else 0,
        }
        cours_sans_form_nb = section_cours_contenu['sans_formateur']
        cours_sans_eval    = section_cours_contenu['sans_evaluation']

        # ── Section Évaluations ───────────────────────────────────────────────
        nb_evals    = eval_qs.count()
        nb_publiees = eval_qs.filter(est_publiee=True).count()
        nb_passages = pass_counts['total']
        nb_soumis   = pass_counts['soumis']
        nb_corriges = pass_counts['corriges']

        avg_note_pct = 0
        try:
            pct_qs = pass_qs.filter(
                statut='corrige', note__isnull=False, evaluation__bareme__gt=0,
            ).annotate(pct=ExpressionWrapper(F('note') / F('evaluation__bareme') * 100, output_field=FloatField()))
            r = pct_qs.aggregate(v=Avg('pct'))['v']
            avg_note_pct = round(r, 1) if r is not None else 0
        except Exception:
            pass

        section_evaluations = {
            'total': nb_evals, 'publiees': nb_publiees,
            'passages_total': nb_passages, 'passages_soumis': nb_soumis,
            'passages_corriges': nb_corriges,
            'taux_correction': self._pct(nb_corriges, nb_passages),
            'note_moy_pct': avg_note_pct,
        }

        # ── Section Sessions ──────────────────────────────────────────────────
        nb_sess    = sess_qs.count()
        sess_passees = sess_qs.filter(date_debut__lt=now).count()
        taux_corr  = self._pct(nb_corriges, nb_passages)

        prochaines = []
        for s in sess_qs.filter(date_debut__gte=now).order_by('date_debut').select_related('cours', 'formateur')[:6]:
            form_name = f'{s.formateur.prenom} {s.formateur.nom}'.strip() if s.formateur else ''
            prochaines.append({
                'id': s.id,
                'cours': s.cours.titre if s.cours else '—',
                'date': s.date_debut.strftime('%d/%m %H:%M'),
                'formateur': form_name or '—',
            })

        section_sessions = {
            'total': nb_sess,
            'a_venir_7j': sess_proch,
            'a_venir_30j': sess_qs.filter(date_debut__gte=now, date_debut__lte=in30).count(),
            'passees': sess_passees,
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
            'inscriptions_mois': self._chart_bar(
                'inscriptions_mois', 'Inscriptions / mois', mois_labels, inscr_data),
            'apprenants_mois': self._chart_bar(
                'apprenants_mois', 'Nouveaux apprenants / mois', mois_labels, appr_data, '#00b69b'),
        }

        # ── Alertes ───────────────────────────────────────────────────────────
        alerts = []
        if all_inactifs > 0:
            alerts.append(self._alert('warning', 'Comptes en attente',
                f'{all_inactifs} compte(s) non activé(s).', 'Gérer', '/utilisateurs'))
        if cours_sans_form_nb:
            alerts.append(self._alert('danger', 'Cours sans formateur',
                f'{cours_sans_form_nb} cours actif(s) sans enseignant.', 'Assigner', '/formateurs'))
        if nb_soumis > 0:
            alerts.append(self._alert('warning', 'Copies à corriger',
                f'{nb_soumis} copie(s) en attente de correction.'))
        if cours_sans_eval > 0:
            alerts.append(self._alert('info', 'Cours sans évaluation',
                f'{cours_sans_eval} cours actif(s) sans évaluation publiée.'))

        # ── Assemblage final ──────────────────────────────────────────────────
        data = self._base("Dashboard Admin", "Gestion de l'institution", kpis, alerts)

        # Compatibilité descendante (champs déjà consommés par le frontend)
        data['inscriptions_stats'] = {
            'actif': insc_counts['actif'], 'diplome': insc_counts['diplome'],
            'retire': insc_counts['retire'], 'total': insc_counts['total'],
            'nouveaux7j': insc_counts['new7j'], 'nouveaux30j': insc_counts['new30j'],
            'tauxCouverture': taux_couverture,
        }
        data['top_formateurs'] = [
            {
                'nom': f'{f.prenom} {f.nom}'.strip() or f.email,
                'cours': cours_by_form.get(f.id, 0),
                'sessions': sess_qs.filter(formateur=f).count(),
                'actifs': f.is_active,
                'statut': (
                    'En activité' if f.is_active and cours_by_form.get(f.id, 0) > 0
                    else ('Sans cours' if cours_by_form.get(f.id, 0) == 0 else 'À suivre')
                ),
            }
            for f in form_qs.order_by('-id')[:6]
        ]
        data['top_responsables'] = [
            {
                'nom': f'{r.prenom} {r.nom}'.strip() or r.email,
                'actifs': r.is_active,
                'departement': (r.departement.nom if getattr(r, 'departement', None) else 'Non renseigné'),
                'institution': inst.nom if inst else 'Établissement',
                'statut': 'Couvert' if getattr(r, 'departement', None) else 'À compléter',
            }
            for r in resp_qs.order_by('-id')[:6]
        ]
        data['cours'] = self._drill('Cours récents', ['Cours', 'Statut'], [
            {'id': c.id, 'libelle': c.titre or f'Cours #{c.id}', 'metadata': {'statut': c.statut}}
            for c in cours_qs.order_by('-id')[:8]
        ])
        data['apprenants']    = section_apprenants
        data['formateurs']    = section_formateurs
        data['cours_contenu'] = section_cours_contenu
        data['evaluations']   = section_evaluations
        data['sessions']      = section_sessions
        data['feedback']      = section_feedback
        data['tendances']     = section_tendances
        return data
