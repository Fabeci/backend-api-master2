"""
Dashboard personnalisés pour l'interface admin Django.
Chaque profil voit un dashboard adapté à ses responsabilités.
"""
from django.views.generic import TemplateView
from django.db.models import Count, Sum, Avg, Q, F
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import PermissionDenied

from users.models import User, Admin, Parent, Apprenant, Formateur, ResponsableAcademique, SuperAdmin
from academics.models import Institution, AnneeScolaire, Classe, Departement, Specialite
from courses.models import Cours, Module, Sequence, InscriptionCours, Session
from evaluations.models import Evaluation, Quiz, Question, Reponse, PassageQuiz, PassageEvaluation
from progress.models import ProgressionApprenant, ProgressionModule, ProgressionSequence, HistoriqueActivite, PlanAction, ObjectifPlanAction
from collaborations.models import Conversation, Message, Forum, Commentaire
from feedback.models import Feedback
from notifications.models import Notification


def get_user_profile_type(user):
    """Retourne le type de profil de l'utilisateur ('formateur', 'admin', etc.) ou None."""
    if hasattr(user, 'superadmin'):
        return 'superadmin'
    if hasattr(user, 'admin'):
        return 'admin'
    if hasattr(user, 'responsableacademique'):
        return 'responsable'
    if hasattr(user, 'formateur'):
        return 'formateur'
    if hasattr(user, 'parent'):
        return 'parent'
    if hasattr(user, 'apprenant'):
        return 'apprenant'
    return None


def require_profile(profile_name):
    """
    Décorateur-like : lève PermissionDenied si l'utilisateur n'a pas le profil requis.
    Usage dans la vue : check_profile(user, 'formateur')
    """
    def decorator(view_func):
        def _wrapped_view(self, request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not user.is_staff:
                raise PermissionDenied("Accès réservé au personnel.")
            if not hasattr(user, profile_name):
                raise PermissionDenied(f"Vous n'avez pas le profil requis ({profile_name}).")
            return view_func(self, request, *args, **kwargs)
        return _wrapped_view
    return decorator


# =============================
# DASHBOARD INDEX (accueil)
# =============================
class DashboardIndexView(TemplateView):
    template_name = 'admin/dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff:
            raise PermissionDenied("Accès réservé au personnel.")
        context['user_profile'] = user
        context['profile'] = get_user_profile_type(user)
        return context


# =============================
# SUPERADMIN
# =============================
class SuperAdminDashboardView(TemplateView):
    template_name = 'admin/dashboard/superadmin.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff or not hasattr(user, 'superadmin'):
            raise PermissionDenied("Vous n'avez pas les permissions SuperAdmin.")
        context['user_profile'] = user
        context['profile'] = 'superadmin'

        total_users = User.objects.count()
        total_apprenants = Apprenant.objects.count()
        total_formateurs = Formateur.objects.count()
        total_parents = Parent.objects.count()
        total_institutions = Institution.objects.count()
        total_courses = Cours.objects.count()
        total_evaluations = Evaluation.objects.count()
        total_quizzes = Quiz.objects.count()

        thirty_days_ago = timezone.now() - timedelta(days=30)
        new_users_30d = User.objects.filter(date_joined__gte=thirty_days_ago).count()

        avg_completion = ProgressionApprenant.objects.aggregate(avg=Avg('pourcentage_completion'))['avg'] or 0

        week_ago = timezone.now() - timedelta(days=7)
        recent_logins = User.objects.filter(last_login__gte=week_ago).count() if hasattr(User, 'last_login') else 0
        recent_feedbacks = Feedback.objects.filter(date_creation__gte=week_ago).count()
        recent_forums = Forum.objects.filter(date_creation__gte=week_ago).count() if hasattr(Forum, 'date_creation') else 0

        inactive_users = User.objects.filter(is_active=False).count()
        overdue_plans = PlanAction.objects.filter(date_echeance__lt=timezone.now().date()).exclude(statut='termine').count()

        top_institutions = Institution.objects.annotate(
            nb_apprenants=Count('users', filter=Q(users__apprenant__isnull=False))
        ).order_by('-nb_apprenants')[:5]

        context.update({
            'total_users': total_users,
            'total_apprenants': total_apprenants,
            'total_formateurs': total_formateurs,
            'total_parents': total_parents,
            'total_institutions': total_institutions,
            'total_courses': total_courses,
            'total_evaluations': total_evaluations,
            'total_quizzes': total_quizzes,
            'new_users_30d': new_users_30d,
            'avg_completion': round(avg_completion, 1),
            'recent_logins': recent_logins,
            'recent_feedbacks': recent_feedbacks,
            'recent_forums': recent_forums,
            'inactive_users': inactive_users,
            'overdue_plans': overdue_plans,
            'top_institutions': top_institutions,
        })
        return context


# =============================
# ADMIN (institution)
# =============================
class AdminDashboardView(TemplateView):
    template_name = 'admin/dashboard/admin.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff or not hasattr(user, 'admin'):
            raise PermissionDenied("Vous n'avez pas les permissions Admin.")
        context['user_profile'] = user
        context['profile'] = 'admin'

        try:
            admin_profile = Admin.objects.get(user_ptr=user)
            institution = admin_profile.institution
        except Admin.DoesNotExist:
            institution = None

        if institution:
            nb_apprenants = Apprenant.objects.filter(institution=institution).count()
            nb_formateurs = Formateur.objects.filter(institutions=institution).count()
            nb_parents = Parent.objects.filter(institution=institution).count()
            nb_responsables = ResponsableAcademique.objects.filter(institution=institution).count()

            nb_courses = Cours.objects.filter(institution=institution).count()
            nb_inscriptions = InscriptionCours.objects.filter(institution=institution).count()

            progressions = ProgressionApprenant.objects.filter(cours__institution=institution)
            avg_completion = progressions.aggregate(avg=Avg('pourcentage_completion'))['avg'] or 0

            nb_evaluations = Evaluation.objects.filter(cours__institution=institution).count()
            nb_quizzes = Quiz.objects.filter(sequence__module__cours__institution=institution).count()

            avg_feedback = Feedback.objects.filter(cours__institution=institution).aggregate(avg=Avg('note'))['avg'] or 0

            annees = AnneeScolaire.objects.filter(institution=institution).count()
            classes = Classe.objects.filter(institution=institution).count()
        else:
            nb_apprenants = nb_formateurs = nb_parents = nb_responsables = 0
            nb_courses = nb_inscriptions = 0
            avg_completion = 0
            nb_evaluations = nb_quizzes = 0
            avg_feedback = 0
            annees = classes = 0

        context.update({
            'institution': institution,
            'nb_apprenants': nb_apprenants,
            'nb_formateurs': nb_formateurs,
            'nb_parents': nb_parents,
            'nb_responsables': nb_responsables,
            'nb_courses': nb_courses,
            'nb_inscriptions': nb_inscriptions,
            'avg_completion': round(avg_completion, 1),
            'nb_evaluations': nb_evaluations,
            'nb_quizzes': nb_quizzes,
            'avg_feedback': round(avg_feedback, 1) if avg_feedback else 0,
            'nb_annees': annees,
            'nb_classes': classes,
        })
        return context


# =============================
# FORMATEUR
# =============================
class FormateurDashboardView(TemplateView):
    template_name = 'admin/dashboard/formateur.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff or not hasattr(user, 'formateur'):
            raise PermissionDenied("Vous n'avez pas les permissions Formateur.")
        context['user_profile'] = user
        context['profile'] = 'formateur'

        try:
            formateur_profile = Formateur.objects.get(user_ptr=user)
        except Formateur.DoesNotExist:
            formateur_profile = None

        if formateur_profile:
            courses = Cours.objects.filter(enseignant=formateur_profile)
            nb_courses = courses.count()

            nb_sessions = Session.objects.filter(cours__in=courses).count()

            nb_evaluations = Evaluation.objects.filter(enseignant=formateur_profile).count()
            nb_quizzes = Quiz.objects.filter(sequence__module__cours__enseignant=formateur_profile).count()

            nb_questions = Question.objects.filter(
                Q(evaluation__enseignant=formateur_profile) |
                Q(quiz__sequence__module__cours__enseignant=formateur_profile)
            ).distinct().count()

            progressions = ProgressionApprenant.objects.filter(cours__in=courses)
            avg_completion = progressions.aggregate(avg=Avg('pourcentage_completion'))['avg'] or 0
            avg_notes = progressions.aggregate(avg=Avg('note_moyenne_evaluations'))['avg'] or 0

            avg_feedback = Feedback.objects.filter(cours__in=courses).aggregate(avg=Avg('note'))['avg'] or 0

            nb_forums = Forum.objects.filter(auteur=formateur_profile).count() if hasattr(Forum, 'auteur') else 0
            nb_commentaires = Commentaire.objects.filter(auteur=formateur_profile).count() if hasattr(Commentaire, 'auteur') else 0

            week_ago = timezone.now() - timedelta(days=7)
            recent_progressions = progressions.filter(date_derniere_activite__gte=week_ago).count()
        else:
            nb_courses = nb_sessions = nb_evaluations = nb_quizzes = nb_questions = 0
            avg_completion = avg_notes = avg_feedback = 0
            nb_forums = nb_commentaires = recent_progressions = 0

        context.update({
            'formateur': formateur_profile,
            'nb_courses': nb_courses,
            'nb_sessions': nb_sessions,
            'nb_evaluations': nb_evaluations,
            'nb_quizzes': nb_quizzes,
            'nb_questions': nb_questions,
            'avg_completion': round(avg_completion, 1),
            'avg_notes': round(avg_notes, 1) if avg_notes else 0,
            'avg_feedback': round(avg_feedback, 1) if avg_feedback else 0,
            'nb_forums': nb_forums,
            'nb_commentaires': nb_commentaires,
            'recent_progressions': recent_progressions,
        })
        return context


# =============================
# PARENT
# =============================
class ParentDashboardView(TemplateView):
    template_name = 'admin/dashboard/parent.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff or not hasattr(user, 'parent'):
            raise PermissionDenied("Vous n'avez pas les permissions Parent.")
        context['user_profile'] = user
        context['profile'] = 'parent'

        try:
            parent_profile = Parent.objects.get(user_ptr=user)
        except Parent.DoesNotExist:
            parent_profile = None

        if parent_profile:
            enfants = Apprenant.objects.filter(tuteur=parent_profile)
            nb_enfants = enfants.count()

            enfants_data = []
            for enfant in enfants:
                progressions = ProgressionApprenant.objects.filter(apprenant=enfant)
                avg_comp = progressions.aggregate(avg=Avg('pourcentage_completion'))['avg'] or 0
                avg_note = progressions.aggregate(avg=Avg('note_moyenne_evaluations'))['avg'] or 0
                nb_cours = progressions.count()
                last_activity = HistoriqueActivite.objects.filter(apprenant=enfant).order_by('-date_activite').first()

                enfants_data.append({
                    'enfant': enfant,
                    'avg_completion': round(avg_comp, 1),
                    'avg_notes': round(avg_note, 1) if avg_note else 0,
                    'nb_cours': nb_cours,
                    'last_activity': last_activity,
                })

            total_plans = PlanAction.objects.filter(apprenant__in=enfants).count()
            overdue_plans = PlanAction.objects.filter(
                apprenant__in=enfants,
                date_echeance__lt=timezone.now().date()
            ).exclude(statut='termine').count()

            unread_notifications = Notification.objects.filter(recipient=user, is_read=False).count()

            conversations = Conversation.objects.filter(participants__user=user).distinct()
            nb_conversations = conversations.count()
        else:
            enfants_data = []
            nb_enfants = total_plans = overdue_plans = unread_notifications = nb_conversations = 0

        context.update({
            'parent': parent_profile,
            'enfants_data': enfants_data,
            'nb_enfants': nb_enfants,
            'total_plans': total_plans,
            'overdue_plans': overdue_plans,
            'unread_notifications': unread_notifications,
            'nb_conversations': nb_conversations,
        })
        return context


# =============================
# RESPONSABLE ACADÉMIIQUE
# =============================
class ResponsableDashboardView(TemplateView):
    template_name = 'admin/dashboard/responsable.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff or not hasattr(user, 'responsableacademique'):
            raise PermissionDenied("Vous n'avez pas les permissions Responsable.")
        context['user_profile'] = user
        context['profile'] = 'responsable'

        try:
            responsable_profile = ResponsableAcademique.objects.get(user_ptr=user)
            departements = Departement.objects.filter(responsables_departement=responsable_profile)
        except ResponsableAcademique.DoesNotExist:
            departements = Departement.objects.none()
            responsable_profile = None

        if departements.exists():
            courses = Cours.objects.filter(departement__in=departements)
            nb_courses = courses.count()

            nb_formateurs = Formateur.objects.filter(cours_enseignes__in=courses).distinct().count()

            nb_apprenants = Apprenant.objects.filter(inscriptions_cours__cours__in=courses).distinct().count()

            progressions = ProgressionApprenant.objects.filter(cours__in=courses)
            avg_completion = progressions.aggregate(avg=Avg('pourcentage_completion'))['avg'] or 0
            avg_notes = progressions.aggregate(avg=Avg('note_moyenne_evaluations'))['avg'] or 0

            nb_evaluations = Evaluation.objects.filter(cours__in=courses).count()
            nb_quizzes = Quiz.objects.filter(sequence__module__cours__in=courses).count()

            reussite_count = progressions.filter(note_moyenne_evaluations__gte=10).count()
            taux_reussite = (reussite_count / progressions.count() * 100) if progressions.count() > 0 else 0

            low_completion = progressions.filter(pourcentage_completion__lt=50).count()
            dept_apprenants = Apprenant.objects.filter(inscriptions_cours__cours__in=courses).distinct()
            inactive_learners = dept_apprenants.exclude(id__in=progressions.values_list('apprenant_id', flat=True)).count()
        else:
            nb_courses = nb_formateurs = nb_apprenants = avg_completion = avg_notes = 0
            nb_evaluations = nb_quizzes = taux_reussite = low_completion = inactive_learners = 0

        context.update({
            'responsable': responsable_profile,
            'departements': departements,
            'nb_courses': nb_courses,
            'nb_formateurs': nb_formateurs,
            'nb_apprenants': nb_apprenants,
            'avg_completion': round(avg_completion, 1),
            'avg_notes': round(avg_notes, 1) if avg_notes else 0,
            'nb_evaluations': nb_evaluations,
            'nb_quizzes': nb_quizzes,
            'taux_reussite': round(taux_reussite, 1),
            'low_completion': low_completion,
            'inactive_learners': inactive_learners,
        })
        return context


# =============================
# APPRENANT
# =============================
class ApprenantDashboardView(TemplateView):
    template_name = 'admin/dashboard/apprenant.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if not user.is_authenticated or not user.is_staff or not hasattr(user, 'apprenant'):
            raise PermissionDenied("Vous n'avez pas les permissions Apprenant.")
        context['user_profile'] = user
        context['profile'] = 'apprenant'

        try:
            apprenant_profile = Apprenant.objects.get(user_ptr=user)
        except Apprenant.DoesNotExist:
            apprenant_profile = None

        if apprenant_profile:
            inscriptions = InscriptionCours.objects.filter(apprenant=apprenant_profile)
            nb_courses = inscriptions.count()

            progressions = ProgressionApprenant.objects.filter(apprenant=apprenant_profile)
            avg_completion = progressions.aggregate(avg=Avg('pourcentage_completion'))['avg'] or 0
            avg_note = progressions.aggregate(avg=Avg('note_moyenne_evaluations'))['avg'] or 0

            recent_activities = HistoriqueActivite.objects.filter(apprenant=apprenant_profile).order_by('-date_activite')[:10]

            plans = PlanAction.objects.filter(apprenant=apprenant_profile)
            nb_plans = plans.count()
            plans_completed = plans.filter(statut='termine').count()

            unread_notifications = Notification.objects.filter(recipient=user, is_read=False).count()

            # Calcul du streak : jours consécutifs d'activité jusqu'à aujourd'hui
            streak = 0
            today = timezone.now().date()
            activite_dates = (
                HistoriqueActivite.objects.filter(apprenant=apprenant_profile)
                .values_list('date_activite__date', flat=True)
                .distinct()
                .order_by('-date_activite__date')
            )
            check_day = today
            for day in activite_dates:
                if day == check_day:
                    streak += 1
                    check_day = check_day - timedelta(days=1)
                elif day < check_day:
                    break
        else:
            inscriptions = progressions = []
            nb_courses = avg_completion = avg_note = nb_plans = plans_completed = 0
            unread_notifications = streak = 0
            recent_activities = []
            plans = []

        context.update({
            'apprenant': apprenant_profile,
            'inscriptions': inscriptions,
            'nb_courses': nb_courses,
            'avg_completion': round(avg_completion, 1),
            'avg_note': round(avg_note, 1) if avg_note else 0,
            'recent_activities': recent_activities,
            'plans': plans,
            'nb_plans': nb_plans,
            'plans_completed': plans_completed,
            'unread_notifications': unread_notifications,
            'streak': streak,
        })
        return context
