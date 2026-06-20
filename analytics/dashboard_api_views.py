# analytics/dashboard_api_views.py
# REST dashboard views — one rich endpoint per actor role.
# Single call replaces all cascade calls previously done in the Angular components.
import logging
from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

COLORS = ['#757fef', '#00b69b', '#ee368c', '#2db6f5', '#f59e0b', '#8b5cf6', '#10b981', '#ef4444']


# ── Helpers ────────────────────────────────────────────────────────────────────

def _kpi(label, value, icon='ri-bar-chart-line', trend='stable', tooltip='', sub=None):
    kpi = {'label': label, 'value': value, 'icon': icon, 'trend': trend, 'tooltip': tooltip}
    if sub is not None:
        kpi['sub'] = sub
    return kpi


def _alert(type_, title, message, action_label='', action_url=''):
    return {
        'type': type_, 'title': title, 'message': message,
        'action_label': action_label, 'action_url': action_url,
        'timestamp': timezone.now().isoformat(), 'read': False,
    }


def _base(title, description, kpis, alerts=None, charts=None):
    return {
        'title': title, 'description': description,
        'kpis': kpis, 'charts': charts or [], 'alerts': alerts or [],
        'last_updated': timezone.now().isoformat(),
    }


def _drill(titre, colonnes, lignes):
    return {'titre': titre, 'colonnes': colonnes, 'lignes': lignes}


def _safe_avg(qs, field):
    r = qs.aggregate(v=Avg(field))['v']
    return round(r, 2) if r is not None else 0


def _safe_sum(qs, field):
    r = qs.aggregate(v=Sum(field))['v']
    return r or 0


def _streak(dates_iso_set, from_date):
    """Compte les jours consécutifs jusqu'à aujourd'hui."""
    count = 0
    d = from_date
    while d.isoformat() in dates_iso_set:
        count += 1
        d -= timedelta(days=1)
    return count


def _chart_bar(id_, title, labels, data, color='#757fef'):
    return {
        'id': id_, 'type': 'bar', 'title': title, 'labels': labels,
        'datasets': [{'label': title, 'data': data, 'backgroundColor': color}],
    }


# ── Super-Admin ─────────────────────────────────────────────────────────────────

class SuperAdminDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from academics.models import Institution, AnneeScolaire
            from users.models import User, Apprenant as _A, Formateur as _F

            nb_institutions = Institution.objects.count()
            nb_users        = User.objects.filter(is_active=True).count()
            nb_annees       = AnneeScolaire.objects.count()
            nb_apprenants   = _A.objects.count()
            nb_formateurs   = _F.objects.count()

            # Évolution mensuelle (12 derniers mois) via User.date_joined
            today = timezone.now().date()
            mois_labels, mois_data = [], []
            for i in range(11, -1, -1):
                d = today.replace(day=1) - timedelta(days=i * 30)
                mois_labels.append(d.strftime('%b'))
                mois_data.append(
                    User.objects.filter(
                        date_joined__year=d.year,
                        date_joined__month=d.month,
                    ).count()
                )

            kpis = [
                _kpi('Institutions',        nb_institutions, 'ri-building-line',   tooltip='Nombre total d\'institutions'),
                _kpi('Utilisateurs actifs',  nb_users,        'ri-group-line',       tooltip='Comptes actifs sur la plateforme'),
                _kpi('Apprenants',           nb_apprenants,   'ri-user-line',        tooltip='Apprenants inscrits'),
                _kpi('Formateurs',           nb_formateurs,   'ri-user-star-line',   tooltip='Formateurs enregistrés'),
                _kpi('Années scolaires',     nb_annees,       'ri-calendar-line',    tooltip='Années scolaires créées'),
            ]

            institutions_qs = Institution.objects.values('id', 'nom')[:10]
            lignes_inst = []
            for inst in institutions_qs:
                nb = _A.objects.filter(institution_id=inst['id']).count()
                lignes_inst.append({
                    'id': inst['id'], 'libelle': inst['nom'], 'value': nb,
                    'metadata': {'apprenants': nb},
                })

            data = _base('Dashboard Super Admin', 'Vue globale de toutes les institutions', kpis)
            data['institutions'] = _drill('Institutions', ['Institution', 'Apprenants'], lignes_inst)
            data['trends'] = {
                'evolution': _chart_bar('evolution', 'Nouveaux utilisateurs / mois', mois_labels, mois_data),
            }
            return Response(data)
        except Exception:
            logger.exception('SuperAdminDashboardAPIView')
            return Response(_base('Dashboard Super Admin', '', []))


# ── Admin ───────────────────────────────────────────────────────────────────────

class AdminDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from users.models import Apprenant, Formateur, ResponsableAcademique, Parent
            from courses.models import Cours, Session, InscriptionCours, Module, Participation
            from academics.models import Classe
            from evaluations.models import Evaluation, PassageEvaluation
            from feedback.models import Feedback
            from django.db.models import ExpressionWrapper, FloatField as DjFloat, F

            inst  = getattr(request.user, 'institution', None)
            now   = timezone.now()
            today = now.date()
            in7   = now + timedelta(days=7)
            in30  = now + timedelta(days=30)
            ago7  = now - timedelta(days=7)
            ago30 = now - timedelta(days=30)

            # ── Base querysets ─────────────────────────────────────────────
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

            # ── Aggregated counts ──────────────────────────────────────────
            nb_appr       = appr_qs.count()
            appr_actifs   = appr_qs.filter(is_active=True).count()
            frm_actifs    = form_qs.filter(is_active=True).count()
            resp_actifs   = resp_qs.filter(is_active=True).count()
            par_actifs    = par_qs.filter(is_active=True).count()
            nb_classes    = class_qs.count()
            cours_actifs  = cours_qs.filter(statut='en_cours').count()
            sess_proch    = sess_qs.filter(date_debut__gte=now, date_debut__lte=in7).count()
            total_insc    = insc_qs.count()
            actif_insc    = insc_qs.filter(statut='actif').count()
            diplome_insc  = insc_qs.filter(statut__in=['diplome', 'diplomé']).count()
            retire_insc   = insc_qs.filter(statut__in=['retire', 'retiré']).count()
            nouveaux7j    = insc_qs.filter(date_inscription__gte=ago7).count()
            nouveaux30j   = insc_qs.filter(date_inscription__gte=ago30).count()

            all_inactifs  = (
                appr_qs.filter(is_active=False).count() +
                form_qs.filter(is_active=False).count() +
                resp_qs.filter(is_active=False).count() +
                par_qs.filter(is_active=False).count()
            )

            appr_avec_groupe = appr_qs.exclude(Q(groupe__isnull=True)).count()
            taux_couverture  = round(appr_avec_groupe / nb_appr * 100) if nb_appr else 0

            # ── KPIs principaux ────────────────────────────────────────────
            kpis = [
                _kpi('Apprenants actifs',   appr_actifs,  'ri-user-line',
                     tooltip=f'{appr_actifs}/{nb_appr} actifs sur la plateforme'),
                _kpi('Formateurs actifs',   frm_actifs,   'ri-user-star-line',
                     tooltip='Formateurs avec compte actif'),
                _kpi('Responsables actifs', resp_actifs,  'ri-shield-user-line',
                     tooltip='Responsables académiques actifs'),
                _kpi('Cours actifs',        cours_actifs, 'ri-book-open-line',
                     sub=f'{cours_qs.count()} total',
                     tooltip='Cours actuellement en cours'),
                _kpi('Sessions à venir',    sess_proch,   'ri-calendar-event-line',
                     tooltip='Sessions planifiées dans les 7 prochains jours'),
                _kpi('Classes',             nb_classes,   'ri-building-4-line',
                     tooltip='Classes actives dans l\'institution'),
                _kpi('Parents actifs',      par_actifs,   'ri-parent-line',
                     tooltip='Parents avec compte actif'),
                _kpi('Comptes en attente',  all_inactifs, 'ri-time-line',
                     trend='danger' if all_inactifs > 0 else 'stable',
                     tooltip='Comptes non encore activés (tous rôles confondus)'),
            ]

            # ── Inscriptions stats (backward compat) ───────────────────────
            insc_stats_data = {
                'actif': actif_insc, 'diplome': diplome_insc, 'retire': retire_insc,
                'total': total_insc, 'nouveaux7j': nouveaux7j, 'nouveaux30j': nouveaux30j,
                'tauxCouverture': taux_couverture,
            }

            # ── Top formateurs (backward compat) ──────────────────────────
            cours_by_form = {}
            for c in cours_qs.values('enseignant_id'):
                fid = c['enseignant_id']
                if fid:
                    cours_by_form[fid] = cours_by_form.get(fid, 0) + 1

            top_formateurs = []
            for f in form_qs.order_by('-id')[:6]:
                nb_c = cours_by_form.get(f.id, 0)
                statut_f = 'En activité' if f.is_active and nb_c > 0 else ('Sans cours' if nb_c == 0 else 'À suivre')
                top_formateurs.append({
                    'nom': f'{f.prenom} {f.nom}'.strip() or f.email,
                    'cours': nb_c,
                    'sessions': sess_qs.filter(formateur=f).count(),
                    'actifs': f.is_active,
                    'statut': statut_f,
                })

            # ── Top responsables (backward compat) ────────────────────────
            top_responsables = []
            for r in resp_qs.order_by('-id')[:6]:
                dep = getattr(r, 'departement', None)
                top_responsables.append({
                    'nom': f'{r.prenom} {r.nom}'.strip() or r.email,
                    'actifs': r.is_active,
                    'departement': dep.nom if dep else 'Non renseigné',
                    'institution': inst.nom if inst else 'Établissement',
                    'statut': 'Couvert' if dep else 'À compléter',
                })

            # ── Cours récents (backward compat) ───────────────────────────
            lignes_cours = []
            for c in cours_qs.order_by('-id')[:8]:
                lignes_cours.append({
                    'id': c.id, 'libelle': c.titre or f'Cours #{c.id}',
                    'metadata': {'statut': c.statut},
                })

            # ──────────────────────────────────────────────────────────────
            # SECTIONS DÉTAILLÉES
            # ──────────────────────────────────────────────────────────────

            # ── Section Apprenants ─────────────────────────────────────────
            try:
                nouveaux_appr_7j  = appr_qs.filter(date_joined__gte=ago7).count()
                nouveaux_appr_30j = appr_qs.filter(date_joined__gte=ago30).count()
            except Exception:
                nouveaux_appr_7j = nouveaux_appr_30j = 0

            taux_actifs_appr = round(appr_actifs / nb_appr * 100) if nb_appr else 0

            # Top cours par inscriptions actives
            top_cours_insc = []
            for c in cours_qs.order_by('-id')[:6]:
                nb = insc_qs.filter(cours=c, statut__in=['actif', 'inscrit']).count()
                top_cours_insc.append({
                    'cours': c.titre or f'Cours #{c.id}',
                    'statut': c.statut,
                    'nb_inscrits': nb,
                })
            top_cours_insc.sort(key=lambda x: x['nb_inscrits'], reverse=True)

            section_apprenants = {
                'total': nb_appr,
                'actifs': appr_actifs,
                'inactifs': nb_appr - appr_actifs,
                'nouveaux_7j': nouveaux_appr_7j,
                'nouveaux_30j': nouveaux_appr_30j,
                'taux_actifs': taux_actifs_appr,
                'top_cours': top_cours_insc,
            }

            # ── Section Formateurs ────────────────────────────────────────
            nb_form = form_qs.count()
            form_sans_cours = form_qs.filter(is_active=True).exclude(
                id__in=[fid for fid in cours_by_form]
            ).count()
            total_cours_assigned = sum(cours_by_form.values())
            avg_cours_per_form = round(total_cours_assigned / len(cours_by_form), 1) if cours_by_form else 0

            form_liste = []
            for f in form_qs.order_by('-is_active', '-id')[:10]:
                nb_c = cours_by_form.get(f.id, 0)
                nb_s = sess_qs.filter(formateur=f).count()
                form_liste.append({
                    'nom': f'{f.prenom} {f.nom}'.strip() or f.email,
                    'cours': nb_c,
                    'sessions': nb_s,
                    'actif': f.is_active,
                })

            section_formateurs = {
                'total': nb_form,
                'actifs': frm_actifs,
                'inactifs': nb_form - frm_actifs,
                'sans_cours': form_sans_cours,
                'avg_cours': avg_cours_per_form,
                'liste': form_liste,
            }

            # ── Section Cours & Contenu ───────────────────────────────────
            nb_cours_total = cours_qs.count()
            nb_planifies   = cours_qs.filter(statut='planifie').count()
            nb_termines    = cours_qs.filter(statut='termine').count()
            mod_qs         = Module.objects.filter(cours__institution=inst)
            mod_cours_ids  = set(mod_qs.values_list('cours_id', flat=True))
            nb_sans_module = cours_qs.exclude(id__in=mod_cours_ids).count()
            avg_mods       = round(mod_qs.count() / nb_cours_total, 1) if nb_cours_total else 0
            avg_appr_cours = round(total_insc / nb_cours_total, 1) if nb_cours_total else 0
            cours_sans_form_nb = cours_qs.filter(Q(enseignant__isnull=True), statut='en_cours').count()
            cours_avec_eval_ids = set(eval_qs.values_list('cours_id', flat=True))
            cours_sans_eval = cours_qs.filter(statut='en_cours').exclude(id__in=cours_avec_eval_ids).count()

            section_cours_contenu = {
                'total': nb_cours_total,
                'en_cours': cours_actifs,
                'planifies': nb_planifies,
                'termines': nb_termines,
                'sans_module': nb_sans_module,
                'sans_formateur': cours_sans_form_nb,
                'sans_evaluation': cours_sans_eval,
                'avg_modules': avg_mods,
                'avg_apprenants': avg_appr_cours,
            }

            # ── Section Évaluations ───────────────────────────────────────
            nb_evals     = eval_qs.count()
            nb_publiees  = eval_qs.filter(est_publiee=True).count()
            nb_passages  = pass_qs.count()
            nb_soumis    = pass_qs.filter(statut='soumis').count()
            nb_corriges  = pass_qs.filter(statut='corrige').count()
            taux_corr    = round(nb_corriges / nb_passages * 100) if nb_passages else 0

            avg_note_pct = 0
            try:
                pct_qs = pass_qs.filter(
                    statut='corrige', note__isnull=False, evaluation__bareme__gt=0,
                ).annotate(
                    pct=ExpressionWrapper(F('note') / F('evaluation__bareme') * 100, output_field=DjFloat())
                )
                r = pct_qs.aggregate(v=Avg('pct'))['v']
                avg_note_pct = round(r, 1) if r is not None else 0
            except Exception:
                pass

            section_evaluations = {
                'total': nb_evals,
                'publiees': nb_publiees,
                'passages_total': nb_passages,
                'passages_soumis': nb_soumis,
                'passages_corriges': nb_corriges,
                'taux_correction': taux_corr,
                'note_moy_pct': avg_note_pct,
            }

            # ── Section Sessions ──────────────────────────────────────────
            nb_sess     = sess_qs.count()
            sess_7j     = sess_proch
            sess_30j    = sess_qs.filter(date_debut__gte=now, date_debut__lte=in30).count()
            sess_passees = sess_qs.filter(date_debut__lt=now).count()
            presents    = part_qs.filter(statut='present').count()
            taux_pres   = round(presents / part_qs.count() * 100) if part_qs.count() else 0

            prochaines = []
            for s in sess_qs.filter(date_debut__gte=now).order_by('date_debut').select_related('cours', 'formateur')[:6]:
                form_name = ''
                if s.formateur:
                    form_name = f'{s.formateur.prenom} {s.formateur.nom}'.strip()
                prochaines.append({
                    'id': s.id,
                    'cours': s.cours.titre if s.cours else '—',
                    'date': s.date_debut.strftime('%d/%m %H:%M'),
                    'formateur': form_name or '—',
                })

            section_sessions = {
                'total': nb_sess,
                'a_venir_7j': sess_7j,
                'a_venir_30j': sess_30j,
                'passees': sess_passees,
                'taux_presence': taux_pres,
                'prochaines': prochaines,
            }

            # ── Section Feedback ──────────────────────────────────────────
            nb_feed       = feed_qs.count()
            feed_notes    = feed_qs.filter(note__isnull=False)
            nb_avec_note  = feed_notes.count()
            avg_feed_note = round(_safe_avg(feed_notes, 'note'), 2) if nb_avec_note else 0

            repartition_feed = []
            for n in range(1, 6):
                cnt = feed_notes.filter(note__gte=n, note__lt=n + 1).count()
                repartition_feed.append({'note': n, 'count': cnt})
            max_cnt = max((r['count'] for r in repartition_feed), default=1) or 1
            for r in repartition_feed:
                r['pct'] = round(r['count'] / max_cnt * 100)

            section_feedback = {
                'total': nb_feed,
                'avec_note': nb_avec_note,
                'note_moyenne': avg_feed_note,
                'repartition': repartition_feed,
            }

            # ── Tendances mensuelles (12 mois) ────────────────────────────
            mois_labels, inscr_data, appr_data = [], [], []
            for i in range(11, -1, -1):
                d_start = (now - timedelta(days=i * 30)).date().replace(day=1)
                mois_labels.append(d_start.strftime('%b'))
                inscr_data.append(insc_qs.filter(
                    date_inscription__year=d_start.year,
                    date_inscription__month=d_start.month,
                ).count())
                try:
                    appr_data.append(appr_qs.filter(
                        date_joined__year=d_start.year,
                        date_joined__month=d_start.month,
                    ).count())
                except Exception:
                    appr_data.append(0)

            section_tendances = {
                'inscriptions_mois': _chart_bar(
                    'inscriptions_mois', 'Inscriptions / mois', mois_labels, inscr_data),
                'apprenants_mois': _chart_bar(
                    'apprenants_mois', 'Nouveaux apprenants / mois', mois_labels, appr_data, '#00b69b'),
            }

            # ── Alertes ───────────────────────────────────────────────────
            alerts = []
            if all_inactifs > 0:
                alerts.append(_alert('warning', 'Comptes en attente',
                    f'{all_inactifs} compte(s) non activé(s).', 'Gérer', '/utilisateurs'))
            if cours_sans_form_nb:
                alerts.append(_alert('danger', 'Cours sans formateur',
                    f'{cours_sans_form_nb} cours actif(s) sans enseignant.', 'Assigner', '/formateurs'))
            if nb_soumis > 0:
                alerts.append(_alert('warning', 'Copies à corriger',
                    f'{nb_soumis} copie(s) en attente de correction.'))
            if cours_sans_eval > 0:
                alerts.append(_alert('info', 'Cours sans évaluation',
                    f'{cours_sans_eval} cours actif(s) sans évaluation publiée.'))

            data = _base('Dashboard Admin', "Gestion de l'institution", kpis, alerts)
            # Backward compat
            data['inscriptions_stats']  = insc_stats_data
            data['top_formateurs']      = top_formateurs
            data['top_responsables']    = top_responsables
            data['cours'] = _drill('Cours récents', ['Cours', 'Statut'], lignes_cours)
            # Rich sections
            data['apprenants']      = section_apprenants
            data['formateurs']      = section_formateurs
            data['cours_contenu']   = section_cours_contenu
            data['evaluations']     = section_evaluations
            data['sessions']        = section_sessions
            data['feedback']        = section_feedback
            data['tendances']       = section_tendances
            return Response(data)
        except Exception:
            logger.exception('AdminDashboardAPIView')
            return Response(_base('Dashboard Admin', '', []))


# ── Formateur ───────────────────────────────────────────────────────────────────

class FormateurDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from users.models import Formateur
            from courses.models import Cours, Session, InscriptionCours
            from courses.models import Module, Sequence, BlocContenu, Participation
            from evaluations.models import Evaluation, PassageEvaluation
            from progress.models import ProgressionApprenant
            from analytics.models import BlocAnalyticsSummary
            from academics.models import AnneeScolaire

            try:
                form = Formateur.objects.get(pk=request.user.pk)
            except Formateur.DoesNotExist:
                return Response(_base('Dashboard Formateur', 'Profil formateur introuvable', []))

            today   = timezone.now().date()
            todaydt = timezone.now()
            in7     = todaydt + timedelta(days=7)

            # ── Résolution de l'année scolaire ─────────────────────────────
            annee_id = request.query_params.get('annee_scolaire_id')
            annee = None
            if annee_id:
                try:
                    annee = AnneeScolaire.objects.get(pk=annee_id)
                except AnneeScolaire.DoesNotExist:
                    pass
            if not annee:
                annee = getattr(form, 'annee_scolaire_active', None)
            if not annee:
                inst_q = form.institutions.first()
                if inst_q:
                    annee = AnneeScolaire.objects.filter(institution=inst_q, est_active=True).first()

            inst_first = getattr(annee, 'institution', None) or form.institutions.first()
            annees_dispo = list(
                AnneeScolaire.objects
                .filter(institution=inst_first)
                .order_by('-date_debut', '-id')
                .values('id', 'annee_format_classique', 'est_active')
            ) if inst_first else []

            # ── Querysets filtrés par année scolaire ───────────────────────
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

            nb_cours       = cours_qs.count()
            en_cours       = cours_qs.filter(statut='en_cours').count()
            planifies      = cours_qs.filter(statut='planifie').count()
            termines       = cours_qs.filter(statut='termine').count()
            annules        = cours_qs.filter(statut='annule').count()

            nb_apprenants_actifs = insc_qs.filter(statut='actif').values('apprenant').distinct().count()
            taux_completion      = _safe_avg(prog_qs, 'pourcentage_completion')
            sessions_proch       = sess_qs.filter(date_debut__gte=todaydt, date_debut__lte=in7).count()
            sessions_auj         = sess_qs.filter(date_debut__date=today).count()

            presents = part_qs.filter(statut='present').count()
            taux_pres = round(presents / part_qs.count() * 100) if part_qs.count() else 0

            evals_actives = eval_qs.filter(
                est_publiee=True
            ).filter(
                Q(date_debut__isnull=True) | Q(date_debut__date__lte=today),
                Q(date_fin__isnull=True)   | Q(date_fin__date__gte=today),
            ).count()

            backlog    = pass_qs.filter(statut='soumis').count()
            corriges   = pass_qs.filter(statut='corrige').count()

            # Blocs à retravailler (ouverts sans complétion ou ratio > 130%)
            blocs_ids = list(
                BlocContenu.objects.filter(sequence__module__cours__in=cours_qs)
                .values_list('id', flat=True)
            )
            blocs_prob = BlocAnalyticsSummary.objects.filter(
                bloc_id__in=blocs_ids
            ).filter(
                Q(nb_ouvertures__gt=0, nb_completions=0) | Q(ratio_temps_pct__gt=130)
            ).count()

            kpis = [
                _kpi('Cours actifs',          en_cours,            'ri-play-circle-line',
                     sub=f'{nb_cours} cours au total',
                     tooltip=f'En cours: {en_cours} | Planifiés: {planifies} | Terminés: {termines} | Annulés: {annules}'),
                _kpi('Apprenants actifs',      nb_apprenants_actifs, 'ri-group-line',
                     sub='dans vos cours',
                     tooltip='Apprenants avec inscription active dans au moins un de vos cours'),
                _kpi('Taux de complétion',     f'{taux_completion:.0f}%' if taux_completion else '—',
                     'ri-checkbox-circle-line',
                     trend='danger' if taux_completion > 0 and taux_completion < 30 else 'stable',
                     tooltip='Progression moyenne des apprenants sur vos cours'),
                _kpi('Sessions à venir (7j)',  sessions_proch, 'ri-calendar-event-line',
                     sub=f'{sessions_auj} aujourd\'hui · {sess_qs.count()} total',
                     tooltip='Sessions planifiées dans les 7 prochains jours'),
                _kpi('Taux de présence',       f'{taux_pres}%' if part_qs.count() else '—',
                     'ri-calendar-check-line',
                     trend='danger' if taux_pres > 0 and taux_pres < 70 else 'stable',
                     sub=f'{presents} présent(s)' if part_qs.count() else 'Aucune donnée',
                     tooltip=f'Présence globale: {presents}/{part_qs.count()} participations'),
                _kpi('Évaluations actives',    evals_actives, 'ri-file-edit-line',
                     sub=f'{eval_qs.count()} au total',
                     tooltip='Évaluations publiées et actuellement accessibles'),
                _kpi('À corriger',             backlog, 'ri-edit-box-line',
                     trend='danger' if backlog > 0 else 'stable',
                     sub=f'{pass_qs.count()} passage(s) total',
                     tooltip=f'{backlog} en attente · {corriges} corrigé(s)'),
                _kpi('Blocs à retravailler',   blocs_prob, 'ri-alert-line',
                     trend='danger' if blocs_prob > 0 else 'stable',
                     tooltip='Blocs jamais complétés après ouverture ou trop lents (>130% du temps estimé)'),
            ]

            # ── Alertes ───────────────────────────────────────────────────
            alerts = []
            if backlog > 0:
                alerts.append(_alert('warning', 'Copies à corriger',
                    f'{backlog} évaluation(s) en attente de correction.'))
            if taux_pres > 0 and taux_pres < 70:
                alerts.append(_alert('danger', 'Taux de présence faible',
                    f'Taux de présence à {taux_pres}% (objectif ≥ 70%).'))

            # ── Mes cours (drill-down enrichi) ────────────────────────────
            lignes_cours = []
            for ci, c in enumerate(cours_qs.order_by('-id')):
                nb_insc   = insc_qs.filter(cours=c, statut='actif').count()
                prog_c    = prog_qs.filter(cours=c)
                taux_c    = _safe_avg(prog_c, 'pourcentage_completion')
                sess_c    = sess_qs.filter(cours=c).count()
                eval_c    = eval_qs.filter(cours=c).count()
                pass_c    = pass_qs.filter(evaluation__cours=c)
                backlog_c = pass_c.filter(statut='soumis').count()

                part_c    = part_qs.filter(session__cours=c)
                pres_c    = part_c.filter(statut='present').count()
                taux_pc   = round(pres_c / part_c.count() * 100) if part_c.count() else 0

                nb_blocs  = BlocContenu.objects.filter(sequence__module__cours=c).count()
                jamais    = nb_blocs - BlocAnalyticsSummary.objects.filter(
                    bloc__sequence__module__cours=c, nb_ouvertures__gt=0
                ).values('bloc').distinct().count()

                lignes_cours.append({
                    'id': c.id, 'libelle': c.titre or f'Cours #{c.id}',
                    'value': int(taux_c),
                    'metadata': {
                        'statut': c.statut,
                        'nb_apprenants': nb_insc,
                        'taux_completion': int(taux_c),
                        'nb_sessions': sess_c,
                        'nb_evals': eval_c,
                        'nb_passages': pass_c.count(),
                        'backlog': backlog_c,
                        'taux_presence': taux_pc,
                        'jamais_consultes': max(0, jamais),
                        'couleur': COLORS[ci % len(COLORS)],
                        'groupes_noms': [str(c.groupe)] if c.groupe else [],
                    }
                })

            # ── Section Apprenants ─────────────────────────────────────────
            from courses.models import Participation as Part2
            appr_total     = insc_qs.values('apprenant').distinct().count()
            appr_actifs_nb = insc_qs.filter(statut='actif').values('apprenant').distinct().count()
            appr_termines  = insc_qs.filter(statut='termine').values('apprenant').distinct().count()
            appr_abandonnes= insc_qs.filter(statut='abandonne').values('apprenant').distinct().count()
            progression_moy= round(float(_safe_avg(prog_qs, 'pourcentage_completion')), 1)
            temps_moy_min  = round(float(_safe_avg(prog_qs, 'temps_total_minutes')), 0)

            top_cours_appr = (
                insc_qs.filter(statut__in=['actif', 'inscrit'])
                .values('cours__titre', 'cours__statut')
                .annotate(nb=Count('apprenant', distinct=True))
                .order_by('-nb')[:5]
            )

            section_apprenants = {
                'total': appr_total, 'actifs': appr_actifs_nb,
                'termines': appr_termines, 'abandonnes': appr_abandonnes,
                'progression_moy': progression_moy,
                'temps_moy_minutes': int(temps_moy_min),
                'top_cours': [
                    {'cours': r['cours__titre'] or '—', 'statut': r['cours__statut'], 'nb_apprenants': r['nb']}
                    for r in top_cours_appr
                ],
            }

            # ── Section Sessions & Présence ───────────────────────────────
            in30 = todaydt + timedelta(days=30)
            sess_total  = sess_qs.count()
            sess_7j     = sessions_proch
            sess_30j    = sess_qs.filter(date_debut__gte=todaydt, date_debut__lte=in30).count()
            sess_passees= sess_qs.filter(date_fin__lt=todaydt).count()

            pres_par_cours = []
            for c in cours_qs.filter(statut='en_cours').order_by('titre'):
                p_c   = part_qs.filter(session__cours=c)
                pres  = p_c.filter(statut='present').count()
                tot   = p_c.count()
                pres_par_cours.append({
                    'cours': c.titre or f'Cours #{c.id}',
                    'taux': round(pres / tot * 100) if tot else 0,
                    'presents': pres, 'total': tot,
                })

            prochaines_sess = []
            for s in sess_qs.filter(date_debut__gte=todaydt).order_by('date_debut')[:5]:
                prochaines_sess.append({
                    'cours': s.cours.titre if getattr(s, 'cours_id', None) else '—',
                    'date': s.date_debut.strftime('%d/%m/%Y %H:%M') if s.date_debut else '—',
                    'mode': getattr(s, 'participation_mode', '—') or '—',
                })

            section_sessions = {
                'total': sess_total, 'a_venir_7j': sess_7j, 'a_venir_30j': sess_30j,
                'passees': sess_passees, 'taux_presence': taux_pres,
                'pres_par_cours': pres_par_cours,
                'prochaines': prochaines_sess,
            }

            # ── Section Évaluations ───────────────────────────────────────
            from django.db.models import ExpressionWrapper, FloatField as DjFloat, F as DjF
            eval_total  = eval_qs.count()
            eval_pub    = eval_qs.filter(est_publiee=True).count()
            pass_total  = pass_qs.count()
            pass_soumis = backlog
            pass_cor    = corriges
            taux_corr   = round(pass_cor / pass_total * 100) if pass_total else 0

            pct_qs2 = pass_qs.filter(statut='corrige', note__isnull=False, evaluation__bareme__gt=0).annotate(
                pct=ExpressionWrapper(DjF('note') / DjF('evaluation__bareme') * 100, output_field=DjFloat())
            )
            avg_note_v = pct_qs2.aggregate(v=Avg('pct'))['v']
            avg_note_pct = round(float(avg_note_v), 1) if avg_note_v else 0

            dist_notes = []
            for lo, hi, lbl in [(0,20,'0-19%'),(20,40,'20-39%'),(40,60,'40-59%'),(60,80,'60-79%'),(80,101,'80-100%')]:
                dist_notes.append({'label': lbl, 'count': pct_qs2.filter(pct__gte=lo, pct__lt=hi).count()})
            max_dist = max((d['count'] for d in dist_notes), default=1) or 1
            for d in dist_notes:
                d['pct'] = round(d['count'] / max_dist * 100)

            section_evaluations = {
                'total': eval_total, 'publiees': eval_pub, 'actives': evals_actives,
                'passages_total': pass_total, 'passages_soumis': pass_soumis, 'passages_corriges': pass_cor,
                'taux_correction': taux_corr, 'note_moy_pct': avg_note_pct,
                'distribution_notes': dist_notes,
            }

            # ── Section Contenu ───────────────────────────────────────────
            mod_qs_f  = Module.objects.filter(cours__in=cours_qs)
            seq_qs_f  = Sequence.objects.filter(module__in=mod_qs_f)
            bloc_qs_f = BlocContenu.objects.filter(sequence__in=seq_qs_f)
            blocs_ids2 = list(bloc_qs_f.values_list('id', flat=True))
            ana_qs = BlocAnalyticsSummary.objects.filter(bloc_id__in=blocs_ids2)

            nb_modules   = mod_qs_f.count()
            nb_sequences = seq_qs_f.count()
            nb_blocs_tot = bloc_qs_f.count()
            blocs_jamais_vis = nb_blocs_tot - ana_qs.filter(nb_ouvertures__gt=0).values('bloc').distinct().count()
            blocs_lents_nb   = ana_qs.filter(ratio_temps_pct__gt=130).count()
            blocs_non_comp   = ana_qs.filter(nb_ouvertures__gt=0, nb_completions=0).count()

            section_contenu = {
                'nb_modules': nb_modules, 'nb_sequences': nb_sequences, 'nb_blocs': nb_blocs_tot,
                'blocs_jamais_vus': max(0, blocs_jamais_vis),
                'blocs_trop_lents': blocs_lents_nb,
                'blocs_non_completes': blocs_non_comp,
            }

            # ── Section Feedback ──────────────────────────────────────────
            from feedback.models import Feedback
            feed_qs2 = Feedback.objects.filter(cours__in=cours_qs)
            nb_feed   = feed_qs2.count()
            feed_notes= feed_qs2.filter(note__isnull=False)
            avg_feed  = round(float(_safe_avg(feed_notes, 'note')), 2) if feed_notes.count() else 0

            rep_feed = []
            for n in range(1, 6):
                cnt = feed_notes.filter(note__gte=n, note__lt=n + 1).count()
                rep_feed.append({'note': n, 'count': cnt})
            max_fb = max((r['count'] for r in rep_feed), default=1) or 1
            for r in rep_feed:
                r['pct'] = round(r['count'] / max_fb * 100)

            section_feedback = {
                'total': nb_feed, 'note_moyenne': avg_feed, 'repartition': rep_feed,
            }

            # ── Alertes enrichies ─────────────────────────────────────────
            if blocs_jamais_vis > 0:
                alerts.append(_alert('info', 'Contenu non consulté',
                    f'{max(0, blocs_jamais_vis)} bloc(s) jamais ouvert(s) par vos apprenants.'))
            if appr_abandonnes > 0:
                alerts.append(_alert('warning', 'Abandons',
                    f'{appr_abandonnes} apprenant(s) ont abandonné un de vos cours.'))

            data = _base('Dashboard Formateur', 'Mes cours et apprenants', kpis, alerts)
            data['mes_cours']     = _drill('Mes cours', ['Cours', 'Apprenants', 'Complétion'], lignes_cours)
            data['apprenants']    = section_apprenants
            data['sessions']      = section_sessions
            data['evaluations']   = section_evaluations
            data['contenu']       = section_contenu
            data['feedback']      = section_feedback
            data['annee_scolaire'] = {
                'id':         annee.id if annee else None,
                'label':      getattr(annee, 'annee_format_classique', None) or 'Toutes années',
                'est_active': getattr(annee, 'est_active', False),
            }
            data['annees_disponibles'] = annees_dispo
            return Response(data)
        except Exception:
            logger.exception('FormateurDashboardAPIView')
            return Response(_base('Dashboard Formateur', '', []))


# ── Responsable Académique ──────────────────────────────────────────────────────

class ResponsableDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from users.models import ResponsableAcademique, Apprenant, Formateur
            from courses.models import Cours, Module, Sequence, BlocContenu, Session, InscriptionCours, Participation
            from evaluations.models import Evaluation, PassageEvaluation
            from feedback.models import Feedback
            from progress.models import HistoriqueActivite
            from analytics.models import BlocAnalyticsSummary
            from django.db.models import ExpressionWrapper, FloatField as DjFloat, F

            try:
                resp = ResponsableAcademique.objects.get(pk=request.user.pk)
            except ResponsableAcademique.DoesNotExist:
                return Response(_base('Dashboard Responsable Académique', 'Profil introuvable', []))

            inst   = getattr(request.user, 'institution', None)
            today  = timezone.now().date()
            now_dt = timezone.now()
            ago30  = now_dt - timedelta(days=30)
            ago7   = now_dt - timedelta(days=7)

            # ── Querysets de base ──────────────────────────────────────────
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

            # ── Valeurs KPIs ───────────────────────────────────────────────
            appr_total     = appr_qs.count()
            app_actifs     = appr_qs.filter(is_active=True).count()
            form_total     = form_qs.count()
            form_actifs_nb = form_qs.filter(is_active=True).count()
            cours_actifs   = cours_qs.filter(statut='en_cours').count()
            cours_retard   = cours_qs.filter(statut__in=['en_cours', 'planifie'], date_fin__lt=today.isoformat()).count()

            presents    = part_qs.filter(statut='present').count()
            part_total  = part_qs.count()
            taux_pres   = round(presents / part_total * 100) if part_total else 0

            backlog  = pass_qs.filter(statut='soumis').count()
            insc_act = insc_qs.filter(statut='actif').count()

            temps30h = round(
                _safe_sum(
                    HistoriqueActivite.objects.filter(apprenant__institution=inst, date_activite__gte=ago30),
                    'duree_minutes'
                ) / 60
            )
            actifs30j = HistoriqueActivite.objects.filter(
                apprenant__institution=inst, date_activite__gte=ago30
            ).values('apprenant').distinct().count() or app_actifs

            exec_vals = []
            for c in cours_qs.filter(statut='en_cours'):
                tx = getattr(c, 'taux_execution', None)
                if tx is not None and float(tx) > 0:
                    val = float(tx)
                    exec_vals.append(min(100, val * 100 if val <= 1 else val))
            exec_moy = round(sum(exec_vals) / len(exec_vals)) if exec_vals else 0

            kpis = [
                _kpi('Apprenants actifs', app_actifs, 'ri-user-heart-line',
                     sub=f'{actifs30j} actifs 30j',
                     tooltip=f'Apprenants avec compte actif. {actifs30j} ont eu une activité dans les 30 derniers jours.'),
                _kpi('Formateurs actifs', f'{form_actifs_nb} / {form_total}', 'ri-user-star-line',
                     sub=f'{form_total - form_actifs_nb} inactif(s)',
                     tooltip='Formateurs avec compte actif.'),
                _kpi('Cours en cours', cours_actifs, 'ri-play-circle-line',
                     sub=f'{cours_qs.count()} total · {cours_retard} en retard',
                     trend='danger' if cours_retard > 0 else 'stable',
                     tooltip=f'Cours en statut en_cours. {cours_retard} cours dépassent leur date de fin.'),
                _kpi('Taux de présence', f'{taux_pres}%', 'ri-calendar-check-line',
                     trend='danger' if 0 < taux_pres < 70 else 'stable',
                     sub=f'{part_total} participations',
                     tooltip=f'{presents}/{part_total} présences enregistrées. Objectif ≥ 70%.'),
                _kpi("Taux d'exécution moy.", f'{exec_moy}%', 'ri-bar-chart-fill',
                     trend='danger' if 0 < exec_moy < 50 else 'stable',
                     sub='Avancement programme',
                     tooltip=f"Moyenne du taux d'exécution ({len(exec_vals)} cours avec données). Objectif ≥ 70%."),
                _kpi('Temps consultation', f'{temps30h}h', 'ri-time-line',
                     sub='30 derniers jours',
                     tooltip='Temps total cumulé de consultation du contenu par tous les apprenants.'),
                _kpi('À corriger', backlog, 'ri-edit-box-line',
                     trend='danger' if backlog > 0 else 'stable',
                     sub='copies soumises',
                     tooltip='Copies soumises en attente de correction.'),
                _kpi('Inscriptions actives', insc_act, 'ri-group-line',
                     sub=f'{insc_qs.count()} total',
                     tooltip=f'{insc_act} inscriptions actives sur {insc_qs.count()} total.'),
            ]

            # ── Section Apprenants ─────────────────────────────────────────
            appr_inactifs = appr_total - app_actifs
            appr_nouv_7j  = appr_qs.filter(date_joined__gte=ago7).count()
            appr_nouv_30j = appr_qs.filter(date_joined__gte=ago30).count()
            taux_actifs   = round(app_actifs / appr_total * 100) if appr_total else 0

            top_cours_raw = (
                insc_qs.filter(statut__in=['actif', 'inscrit'])
                .values('cours__titre', 'cours__statut')
                .annotate(nb=Count('id'))
                .order_by('-nb')[:5]
            )
            section_apprenants = {
                'total': appr_total, 'actifs': app_actifs, 'inactifs': appr_inactifs,
                'nouveaux_7j': appr_nouv_7j, 'nouveaux_30j': appr_nouv_30j,
                'taux_actifs': taux_actifs,
                'top_cours': [
                    {'cours': r['cours__titre'] or '—', 'statut': r['cours__statut'], 'nb_inscrits': r['nb']}
                    for r in top_cours_raw
                ],
            }

            # ── Section Formateurs ─────────────────────────────────────────
            form_map              = {str(f.id): f for f in form_qs}
            form_avec_cours_ids   = set(cours_qs.filter(statut='en_cours').values_list('enseignant_id', flat=True))
            form_sans_cours_count = form_qs.filter(is_active=True).exclude(id__in=form_avec_cours_ids).count()
            avg_cours_per_form    = round(cours_qs.count() / form_total, 1) if form_total else 0

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
                'sans_cours': form_sans_cours_count,
                'avg_cours': avg_cours_per_form,
                'liste': form_list,
            }

            # ── Section Cours & Contenu ────────────────────────────────────
            cours_total        = cours_qs.count()
            cours_avec_eval_ids = set(eval_qs.values_list('cours_id', flat=True))
            mod_cours_ids      = set(mod_qs.values_list('cours_id', flat=True))
            cours_sans_mod     = cours_qs.exclude(id__in=mod_cours_ids).count()
            cours_sans_form_nb = cours_qs.filter(statut='en_cours', enseignant__isnull=True).count()
            cours_sans_eval    = cours_qs.filter(statut='en_cours').exclude(id__in=cours_avec_eval_ids).count()
            avg_mods           = round(mod_qs.count() / cours_total, 1) if cours_total else 0
            avg_appr_per_cours = round(insc_qs.filter(statut__in=['actif', 'inscrit']).count() / cours_total, 1) if cours_total else 0

            section_cours_contenu = {
                'total': cours_total,
                'en_cours': cours_actifs,
                'planifies': cours_qs.filter(statut='planifie').count(),
                'termines': cours_qs.filter(statut='termine').count(),
                'en_retard': cours_retard,
                'sans_module': cours_sans_mod,
                'sans_formateur': cours_sans_form_nb,
                'sans_evaluation': cours_sans_eval,
                'avg_modules': avg_mods,
                'avg_apprenants': avg_appr_per_cours,
            }

            # ── Section Évaluations ───────────────────────────────────────
            eval_total    = eval_qs.count()
            eval_publiees = eval_qs.filter(est_publiee=True).count()
            pass_total_nb = pass_qs.count()
            pass_soumis   = pass_qs.filter(statut='soumis').count()
            pass_corriges = pass_qs.filter(statut='corrige').count()
            taux_corr     = round(pass_corriges / pass_total_nb * 100) if pass_total_nb else 0

            pct_qs = pass_qs.filter(statut='corrige', note__isnull=False, evaluation__bareme__gt=0).annotate(
                pct=ExpressionWrapper(F('note') / F('evaluation__bareme') * 100, output_field=DjFloat())
            )
            avg_note_pct_v = pct_qs.aggregate(v=Avg('pct'))['v']
            avg_note_pct   = round(avg_note_pct_v, 1) if avg_note_pct_v else 0

            section_evaluations = {
                'total': eval_total, 'publiees': eval_publiees,
                'passages_total': pass_total_nb, 'passages_soumis': pass_soumis,
                'passages_corriges': pass_corriges,
                'taux_correction': taux_corr, 'note_moy_pct': avg_note_pct,
            }

            # ── Section Sessions & Présence ───────────────────────────────
            sess_total    = sess_qs.count()
            sess_7j       = sess_qs.filter(date_debut__gte=now_dt, date_debut__lte=now_dt + timedelta(days=7)).count()
            sess_30j      = sess_qs.filter(date_debut__gte=now_dt, date_debut__lte=now_dt + timedelta(days=30)).count()
            sess_passees  = sess_qs.filter(date_fin__lt=now_dt).count()

            prochaines = []
            for s in sess_qs.filter(date_debut__gte=now_dt).order_by('date_debut')[:5]:
                fid      = str(getattr(s, 'formateur_id', None) or '')
                form_obj = form_map.get(fid)
                prochaines.append({
                    'cours':     s.cours.titre if getattr(s, 'cours_id', None) else '—',
                    'date':      s.date_debut.strftime('%d/%m/%Y %H:%M') if s.date_debut else '—',
                    'formateur': f'{form_obj.prenom} {form_obj.nom}'.strip() if form_obj else '—',
                })
            section_sessions = {
                'total': sess_total, 'a_venir_7j': sess_7j, 'a_venir_30j': sess_30j,
                'passees': sess_passees, 'taux_presence': taux_pres, 'prochaines': prochaines,
            }

            # ── Section Feedback ──────────────────────────────────────────
            nb_feed      = feed_qs.count()
            feed_notes   = feed_qs.filter(note__isnull=False)
            nb_avec_note = feed_notes.count()
            avg_feed     = round(_safe_avg(feed_notes, 'note'), 2) if nb_avec_note else 0

            rep_feed = []
            for n in range(1, 6):
                cnt = feed_notes.filter(note__gte=n, note__lt=n + 1).count()
                rep_feed.append({'note': n, 'count': cnt})
            max_cnt = max((r['count'] for r in rep_feed), default=1) or 1
            for r in rep_feed:
                r['pct'] = round(r['count'] / max_cnt * 100)
            section_feedback = {
                'total': nb_feed, 'avec_note': nb_avec_note,
                'note_moyenne': avg_feed, 'repartition': rep_feed,
            }

            # ── Section Tendances (12 mois) ───────────────────────────────
            mois_labels, inscr_data, appr_data = [], [], []
            for i in range(11, -1, -1):
                d_start = (now_dt - timedelta(days=i * 30)).date().replace(day=1)
                mois_labels.append(d_start.strftime('%b'))
                inscr_data.append(insc_qs.filter(
                    date_inscription__year=d_start.year,
                    date_inscription__month=d_start.month,
                ).count())
                try:
                    appr_data.append(appr_qs.filter(
                        date_joined__year=d_start.year,
                        date_joined__month=d_start.month,
                    ).count())
                except Exception:
                    appr_data.append(0)
            section_tendances = {
                'inscriptions_mois': _chart_bar('inscriptions_mois', 'Inscriptions / mois', mois_labels, inscr_data),
                'apprenants_mois': _chart_bar('apprenants_mois', 'Nouveaux apprenants / mois', mois_labels, appr_data, '#00b69b'),
            }

            # ── Santé du contenu ───────────────────────────────────────────
            seq_mod_ids   = set(seq_qs.values_list('module_id', flat=True))
            bloc_seq_ids  = set(bloc_qs.values_list('sequence_id', flat=True))
            mods_sans_seq = mod_qs.exclude(id__in=seq_mod_ids).count()
            seqs_sans_blocs = seq_qs.exclude(id__in=bloc_seq_ids).count()

            blocs_sans_duree = bloc_qs.filter(duree_estimee_minutes__isnull=True).count() + \
                               bloc_qs.filter(duree_estimee_minutes=0).count()
            blocs_consultes  = set(BlocAnalyticsSummary.objects.filter(
                bloc__in=bloc_qs, nb_ouvertures__gt=0).values_list('bloc_id', flat=True))
            blocs_jamais     = bloc_qs.count() - len(blocs_consultes)
            blocs_lents      = BlocAnalyticsSummary.objects.filter(
                bloc__in=bloc_qs, ratio_temps_pct__gt=130).count()

            sante_items = [
                {'label': 'Cours sans modules', 'count': cours_sans_mod, 'icon': 'ri-book-2-line',
                 'severite': 'error' if cours_sans_mod > 0 else 'ok',
                 'tooltip': f'{cours_sans_mod} cours sans module créé.'},
                {'label': 'Modules sans séquences', 'count': mods_sans_seq, 'icon': 'ri-layout-3-line',
                 'severite': 'error' if mods_sans_seq > 0 else 'ok',
                 'tooltip': f'{mods_sans_seq} module(s) sans séquence pédagogique.'},
                {'label': 'Séquences sans blocs', 'count': seqs_sans_blocs, 'icon': 'ri-stack-line',
                 'severite': 'warning' if seqs_sans_blocs > 0 else 'ok',
                 'tooltip': f'{seqs_sans_blocs} séquence(s) sans bloc de contenu.'},
                {'label': 'Cours actifs sans évaluation', 'count': cours_sans_eval, 'icon': 'ri-file-damage-line',
                 'severite': 'warning' if cours_sans_eval > 0 else 'ok',
                 'tooltip': f'{cours_sans_eval} cours en cours sans évaluation associée.'},
                {'label': 'Blocs sans durée estimée', 'count': blocs_sans_duree, 'icon': 'ri-timer-line',
                 'severite': 'warning' if blocs_sans_duree > 10 else 'ok',
                 'tooltip': f'{blocs_sans_duree} bloc(s) sans durée estimée.'},
                {'label': 'Blocs jamais consultés', 'count': max(0, blocs_jamais), 'icon': 'ri-eye-off-line',
                 'severite': 'warning' if blocs_jamais > 0 else 'ok',
                 'tooltip': f'{max(0, blocs_jamais)} bloc(s) jamais ouverts.'},
                {'label': 'Blocs trop lents (>130%)', 'count': blocs_lents, 'icon': 'ri-hourglass-2-line',
                 'severite': 'warning' if blocs_lents > 0 else 'ok',
                 'tooltip': f'{blocs_lents} bloc(s) dont le temps dépasse 130% du temps estimé.'},
                {'label': 'Formateurs actifs sans cours', 'count': form_sans_cours_count, 'icon': 'ri-user-unfollow-line',
                 'severite': 'warning' if form_sans_cours_count > 0 else 'ok',
                 'tooltip': f'{form_sans_cours_count} formateur(s) actif(s) sans cours assigné.'},
            ]
            errs  = sum(1 for s in sante_items if s['severite'] == 'error')
            warns = sum(1 for s in sante_items if s['severite'] == 'warning')
            sante_score = max(0, 100 - errs * 20 - warns * 8)

            # ── Tableau cours (enrichi, backward compat) ───────────────────
            lignes_cours = []
            for ci, c in enumerate(cours_qs.order_by('-id')[:15]):
                fid      = str(getattr(c, 'enseignant_id', None) or '')
                form_obj = form_map.get(fid)
                nb_app   = insc_qs.filter(cours=c, statut__in=['actif', 'inscrit']).count()
                nb_mod   = mod_qs.filter(cours=c).count()
                has_eval = c.id in cours_avec_eval_ids
                tx       = getattr(c, 'taux_execution', 0) or 0
                tx_norm  = min(100, int(float(tx) * 100 if float(tx) <= 1 else float(tx)))
                lignes_cours.append({
                    'id': c.id, 'libelle': c.titre or f'Cours #{c.id}',
                    'value': tx_norm,
                    'metadata': {
                        'statut': c.statut,
                        'formateur': f'{form_obj.prenom} {form_obj.nom}'.strip() if form_obj else '—',
                        'nb_modules': nb_mod, 'nb_apprenants': nb_app,
                        'has_eval': has_eval, 'taux_execution': tx_norm,
                        'couleur': COLORS[ci % len(COLORS)],
                    }
                })

            # ── Alertes ───────────────────────────────────────────────────
            alerts = []
            if backlog > 0:
                alerts.append(_alert('warning', 'Copies à corriger',
                    f'{backlog} évaluation(s) soumise(s) en attente.'))
            if cours_retard > 0:
                alerts.append(_alert('danger', 'Cours en retard',
                    f'{cours_retard} cours dépassent leur date de fin.'))
            if errs > 0:
                alerts.append(_alert('danger', 'Problèmes de contenu',
                    f'{errs} problème(s) critique(s) dans le contenu pédagogique.'))
            if form_sans_cours_count > 0:
                alerts.append(_alert('info', 'Formateurs sans cours',
                    f'{form_sans_cours_count} formateur(s) actif(s) sans cours assigné.'))

            data = _base('Dashboard Responsable Académique', 'Pilotage académique', kpis, alerts)
            data['sante_contenu'] = {'items': sante_items, 'score': sante_score}
            data['cours']         = _drill('Tableau des cours', ['Cours', 'Formateur', 'Avancement'], lignes_cours)
            data['apprenants']    = section_apprenants
            data['formateurs']    = section_formateurs
            data['cours_contenu'] = section_cours_contenu
            data['evaluations']   = section_evaluations
            data['sessions']      = section_sessions
            data['feedback']      = section_feedback
            data['tendances']     = section_tendances
            return Response(data)
        except Exception:
            logger.exception('ResponsableDashboardAPIView')
            return Response(_base('Dashboard Responsable Académique', '', []))


# ── Apprenant ───────────────────────────────────────────────────────────────────

class ApprenantDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from users.models import Apprenant
            from courses.models import Cours, InscriptionCours, Session
            from courses.models import Module, Sequence, BlocContenu
            from evaluations.models import Evaluation, PassageEvaluation
            from progress.models import ProgressionApprenant, HistoriqueActivite, PlanAction
            from academics.models import AnneeScolaire

            try:
                appr = Apprenant.objects.get(pk=request.user.pk)
            except Apprenant.DoesNotExist:
                return Response(_base('Mon Dashboard', 'Profil apprenant introuvable', []))

            now   = timezone.now()
            today = now.date()
            in7   = today + timedelta(days=7)
            ago7  = now - timedelta(days=7)
            ago30 = now - timedelta(days=30)
            week_start = today - timedelta(days=today.weekday())

            # ── Résolution de l'année scolaire ─────────────────────────────
            annee_id = request.query_params.get('annee_scolaire_id')
            annee = None
            if annee_id:
                try:
                    annee = AnneeScolaire.objects.get(pk=annee_id)
                except AnneeScolaire.DoesNotExist:
                    pass
            if not annee:
                annee = getattr(appr, 'annee_scolaire_active', None)
            if not annee:
                inst_a = getattr(appr, 'institution', None)
                if inst_a:
                    annee = AnneeScolaire.objects.filter(institution=inst_a, est_active=True).first()

            inst_first = getattr(appr, 'institution', None)
            annees_dispo = list(
                AnneeScolaire.objects
                .filter(institution=inst_first)
                .order_by('-date_debut', '-id')
                .values('id', 'annee_format_classique', 'est_active')
            ) if inst_first else []

            # ── Cours inscrits (filtrés par année) ────────────────────────
            insc_filter = {'apprenant': appr}
            if annee:
                insc_filter['annee_scolaire'] = annee
            inscriptions = InscriptionCours.objects.filter(**insc_filter).select_related('cours')
            cours_list   = [i.cours for i in inscriptions]
            cours_ids    = [c.id for c in cours_list]
            en_cours     = sum(1 for c in cours_list if c.statut == 'en_cours')
            planifies    = sum(1 for c in cours_list if c.statut == 'planifie')

            # ── Progression (filtrée par cours de l'année) ────────────────
            if cours_ids:
                prog_qs = ProgressionApprenant.objects.filter(apprenant=appr, cours__in=cours_ids)
            else:
                prog_qs = ProgressionApprenant.objects.none()
            prog_map  = {p.cours_id: p for p in prog_qs.select_related('cours')}
            avg_comp  = _safe_avg(prog_qs, 'pourcentage_completion')
            nb_termines = prog_qs.filter(statut='termine').count()

            # ── Historique (filtré par dates de l'année si disponibles) ───
            hist_base = HistoriqueActivite.objects.filter(apprenant=appr)
            if annee and getattr(annee, 'date_debut', None):
                hist_base = hist_base.filter(date_activite__gte=annee.date_debut)
                if getattr(annee, 'date_fin', None):
                    hist_base = hist_base.filter(date_activite__lte=annee.date_fin)
            hist_qs = hist_base
            temps_7j  = _safe_sum(hist_qs.filter(date_activite__gte=ago7), 'duree_minutes')
            temps_30j = _safe_sum(hist_qs.filter(date_activite__gte=ago30), 'duree_minutes')
            temps_week = _safe_sum(hist_qs.filter(date_activite__date__gte=week_start), 'duree_minutes')

            dates_actives = set(
                hist_qs.values_list('date_activite__date', flat=True).distinct()
            )
            streak = _streak({d.isoformat() for d in dates_actives}, today)

            # ── Sessions à venir ──────────────────────────────────────────
            sessions_proch = Session.objects.filter(
                cours__in=cours_ids,
                date_debut__date__gte=today,
                date_debut__date__lte=in7,
            ).count()

            # ── Évaluations ───────────────────────────────────────────────
            eval_qs = Evaluation.objects.filter(cours__in=cours_ids, est_publiee=True).filter(
                Q(date_debut__isnull=True) | Q(date_debut__date__lte=today),
                Q(date_fin__isnull=True)   | Q(date_fin__date__gte=today),
            )
            pass_qs  = PassageEvaluation.objects.filter(apprenant=appr, evaluation__cours__in=cours_ids)
            soumises = pass_qs.filter(statut='soumis').count()
            corriges = pass_qs.filter(statut='corrige').count()

            # ── Plans d'action ────────────────────────────────────────────
            plan_qs     = PlanAction.objects.filter(apprenant=appr)
            plans_retard = plan_qs.filter(
                statut__in=['a_faire', 'en_cours'],
                date_echeance__lt=today,
            ).count()

            # ── KPIs ──────────────────────────────────────────────────────
            kpis = [
                _kpi('Cours actifs',         f'{en_cours} cours', 'ri-play-circle-line',
                     sub=f'{planifies} planifié(s)' if planifies else None,
                     tooltip=f'En cours: {en_cours} | Planifiés: {planifies} | Total: {len(cours_list)}'),
                _kpi('Progression globale',   f'{avg_comp:.0f}%', 'ri-bar-chart-line',
                     trend='danger' if avg_comp < 20 else 'stable',
                     tooltip=f'{nb_termines} cours terminé(s) sur {len(cours_list)}'),
                _kpi('Temps passé 7j / 30j',
                     f'{temps_7j // 60}h / {temps_30j // 60}h', 'ri-time-line',
                     tooltip='Temps total de consultation du contenu'),
                _kpi('Streak',               f'{streak}j', 'ri-fire-line',
                     sub='🔥 Super !' if streak >= 7 else None,
                     tooltip=f'{streak} jours consécutifs d\'activité'),
                _kpi('Sessions à venir (7j)', sessions_proch, 'ri-calendar-event-line',
                     tooltip='Sessions planifiées dans les 7 prochains jours'),
                _kpi('Évaluations ouvertes', eval_qs.count(), 'ri-file-edit-line',
                     tooltip='Évaluations actuellement accessibles'),
                _kpi('Soumises',             soumises, 'ri-send-plane-line',
                     tooltip='Copies soumises en attente de correction'),
                _kpi('Corrigées',            corriges, 'ri-check-double-line',
                     trend='danger' if soumises > 0 and corriges == 0 else 'stable',
                     tooltip='Copies corrigées par le formateur'),
            ]

            # ── Alertes ───────────────────────────────────────────────────
            alerts = []
            if plans_retard:
                alerts.append(_alert('danger', 'Plans d\'action en retard',
                    f'{plans_retard} plan(s) dépassé(s).', 'Voir', '/formations/cours'))
            if soumises > 0 and corriges == 0:
                alerts.append(_alert('warning', 'Copies en attente',
                    f'{soumises} copie(s) soumise(s) pas encore corrigée(s).'))
            if avg_comp < 20 and len(cours_list) > 0:
                alerts.append(_alert('info', 'Progression faible',
                    f'Votre progression globale est de {avg_comp:.0f}%. Continuez !'))

            # ── Progression par cours (drill-down) ────────────────────────
            lignes_prog = []
            for ci, cours in enumerate(cours_list):
                prog = prog_map.get(cours.id)
                pct  = int(prog.pourcentage_completion) if prog else 0
                lignes_prog.append({
                    'id': cours.id,
                    'libelle': cours.titre or f'Cours #{cours.id}',
                    'value': pct,
                    'metadata': {
                        'pct_blocs':          pct,
                        'blocs_termines':     0,
                        'blocs_total':        0,
                        'seqs_terminees':     0,
                        'seqs_total':         0,
                        'mods_termines':      0,
                        'mods_total':         0,
                        'statut':             cours.statut,
                        'derniere_activite':  prog.date_derniere_activite.isoformat() if prog else None,
                        'note_moyenne':       float(prog.note_moyenne_evaluations or 0) if prog else 0,
                        'taux_quiz':          float(prog.taux_reussite_quiz or 0) if prog else 0,
                        'couleur':            COLORS[ci % len(COLORS)],
                    }
                })

            # ── Historique récent ──────────────────────────────────────────
            lignes_hist = []
            for act in hist_qs.order_by('-date_activite')[:7]:
                lignes_hist.append({
                    'id': act.id,
                    'libelle': act.description or act.get_type_activite_display(),
                    'metadata': {
                        'type': act.type_activite,
                        'date': act.date_activite.isoformat(),
                        'duree': act.duree_minutes,
                    }
                })

            # ── Plans d'action ────────────────────────────────────────────
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

            # ── Chart activité 7 derniers jours ───────────────────────────
            chart_labels, chart_data = [], []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                chart_labels.append(d.strftime('%a'))
                mins = _safe_sum(hist_qs.filter(date_activite__date=d), 'duree_minutes')
                chart_data.append(int(mins))

            charts = [_chart_bar('activity_week', 'Activité 7j (minutes)', chart_labels, chart_data)]

            # ── Détail passages évaluations ───────────────────────────────
            passages_detail = []
            for p in pass_qs.select_related('evaluation', 'evaluation__cours').order_by('-date_soumission', '-date_debut')[:15]:
                passages_detail.append({
                    'evaluation': p.evaluation.titre,
                    'cours': p.evaluation.cours.titre if getattr(p.evaluation, 'cours_id', None) else '—',
                    'statut': p.statut,
                    'note': float(p.note) if p.note is not None else None,
                    'bareme': float(p.evaluation.bareme) if getattr(p.evaluation, 'bareme', None) else 20.0,
                    'date': p.date_soumission.isoformat() if p.date_soumission else None,
                })

            data = _base('Mon Dashboard', 'Ma progression personnelle', kpis, alerts, charts)
            data['progression']  = _drill('Mes cours', ['Cours', 'Progression'], lignes_prog)
            data['historique']   = _drill('Activité récente', ['Activité', 'Date'], lignes_hist)
            data['plans_action'] = _drill("Plans d'action", ['Plan', 'Échéance'], lignes_plans)
            data['blocsWeek']    = 0
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
                'streak':          streak,
                'chart_labels':    chart_labels,
                'chart_data':      chart_data,
            }
            data['annee_scolaire'] = {
                'id':         annee.id if annee else None,
                'label':      getattr(annee, 'annee_format_classique', None) or 'Toutes années',
                'est_active': getattr(annee, 'est_active', False),
            }
            data['annees_disponibles'] = annees_dispo
            return Response(data)
        except Exception:
            logger.exception('ApprenantDashboardAPIView')
            return Response(_base('Mon Dashboard', '', []))


# ── Parent ──────────────────────────────────────────────────────────────────────

class ParentDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from users.models import Parent, Apprenant
            from courses.models import Cours, InscriptionCours, Session
            from progress.models import ProgressionApprenant, HistoriqueActivite
            from evaluations.models import PassageEvaluation
            from notifications.models import Notification

            try:
                parent = Parent.objects.get(pk=request.user.pk)
            except Parent.DoesNotExist:
                return Response(_base('Dashboard Parent', 'Profil parent introuvable', []))

            now   = timezone.now()
            today = now.date()
            in7   = today + timedelta(days=7)

            enfants      = Apprenant.objects.filter(tuteur=parent)
            nb_enfants   = enfants.count()
            enfants_ids  = list(enfants.values_list('id', flat=True))

            prog_qs = ProgressionApprenant.objects.filter(apprenant__in=enfants)
            pass_qs = PassageEvaluation.objects.filter(apprenant__in=enfants, statut='corrige')
            notif_nb = Notification.objects.filter(recipient=request.user, is_read=False).count()

            avg_comp = _safe_avg(prog_qs, 'pourcentage_completion')
            avg_note = _safe_avg(pass_qs, 'note')

            kpis = [
                _kpi('Enfants suivis',   nb_enfants,       'ri-parent-line',
                     tooltip='Nombre d\'enfants liés à ce compte parent'),
                _kpi('Complétion moy.',  f'{avg_comp:.0f}%', 'ri-percent-line',
                     tooltip='Progression moyenne de vos enfants sur leurs cours'),
                _kpi('Note moyenne',     f'{avg_note:.1f}/20', 'ri-star-line',
                     tooltip='Note moyenne sur toutes les évaluations corrigées'),
                _kpi('Notifications',    notif_nb, 'ri-notification-line',
                     trend='danger' if notif_nb > 5 else 'stable',
                     tooltip='Notifications non lues'),
            ]

            # ── Données par enfant ─────────────────────────────────────────
            AVATAR_COLORS = ['#757fef', '#00b69b', '#ee368c', '#2db6f5', '#f59e0b', '#8b5cf6']
            lignes_enfants = []
            alerts = []
            for i, enfant in enumerate(enfants[:6]):
                prog_e    = prog_qs.filter(apprenant=enfant)
                avg_c     = _safe_avg(prog_e, 'pourcentage_completion')
                avg_n     = _safe_avg(
                    PassageEvaluation.objects.filter(apprenant=enfant, statut='corrige'), 'note'
                )
                cours_actifs = InscriptionCours.objects.filter(
                    apprenant=enfant, cours__statut='en_cours'
                ).count()
                sessions_7j = Session.objects.filter(
                    cours__inscriptioncours__apprenant=enfant,
                    date_debut__date__gte=today,
                    date_debut__date__lte=in7,
                ).count()
                last_act = HistoriqueActivite.objects.filter(
                    apprenant=enfant
                ).order_by('-date_activite').first()

                if avg_c < 20 and cours_actifs > 0:
                    alerts.append(_alert('warning', f'{enfant.prenom} en difficulté',
                        f'Progression à {avg_c:.0f}% — encouragez-le !'))

                lignes_enfants.append({
                    'id':      enfant.id,
                    'libelle': f'{enfant.prenom} {enfant.nom}',
                    'value':   int(avg_c),
                    'metadata': {
                        'prenom':        enfant.prenom,
                        'nom':           enfant.nom,
                        'initiales':     f'{(enfant.prenom or "E")[0]}{(enfant.nom or "E")[0]}'.upper(),
                        'avatarColor':   AVATAR_COLORS[i % len(AVATAR_COLORS)],
                        'cours_actifs':  cours_actifs,
                        'prog_globale':  int(avg_c),
                        'avg_note':      round(avg_n, 1),
                        'sessions_7j':   sessions_7j,
                        'derniere_act':  last_act.date_activite.date().isoformat() if last_act else '',
                    }
                })

            data = _base('Dashboard Parent', 'Suivi de mon enfant', kpis, alerts)
            data['enfants'] = _drill('Mes enfants', ['Enfant', 'Progression', 'Note'], lignes_enfants)
            return Response(data)
        except Exception:
            logger.exception('ParentDashboardAPIView')
            return Response(_base('Dashboard Parent', '', []))
