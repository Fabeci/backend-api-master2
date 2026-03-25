# progress/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    ProgressionApprenant,
    ProgressionModule,
    ProgressionSequence,
    ProgressionQuiz,
    HistoriqueActivite,
    PlanAction,
    ObjectifPlanAction,
)
from .serializers import (
    ProgressionApprenantSerializer,
    ProgressionApprenantDetailSerializer,
    ProgressionApprenantCreateSerializer,
    ProgressionModuleSerializer,
    ProgressionSequenceSerializer,
    ProgressionQuizSerializer,
    HistoriqueActiviteSerializer,
    PlanActionSerializer,
    PlanActionCreateSerializer,
    ObjectifPlanActionSerializer,
)


# ============================================================================
# HELPERS
# ============================================================================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    return Response(
        {"success": True, "status": http_status, "message": message, "data": data},
        status=http_status,
    )


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST, data=None):
    payload = {"success": False, "status": http_status, "message": message, "data": data}
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


def _get_role(user):
    if hasattr(user, 'role') and user.role:
        return user.role.name
    return None


def _is_super_admin(user):
    return getattr(user, 'is_superuser', False)


def _get_annee_scolaire_id(request):
    """
    Priorité : header X-Annee-Scolaire-ID > query param > profil utilisateur.
    """
    def _to_int(v):
        if v is None:
            return None
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return None

    return (
        _to_int(request.headers.get("X-Annee-Scolaire-ID"))
        or _to_int(request.query_params.get("annee_scolaire_id"))
        or _to_int(getattr(request.user, "annee_scolaire_active_id", None))
    )


def _get_enfants_ids(user):
    """Retourne les IDs des enfants d'un parent."""
    from users.models import Apprenant
    return list(Apprenant.objects.filter(tuteur=user).values_list('id', flat=True))


# ============================================================================
# MIXIN ROLE-BASED FILTERING POUR PROGRESSIONS
# ============================================================================

class ProgressionRoleFilterMixin:
    """
    Mixin qui applique le filtrage par rôle et par année scolaire
    sur les querysets de progression.

    Règles :
    - SuperAdmin   : BLOQUÉ (les progressions sont des données internes)
    - Admin/Responsable : tout leur institution, filtrable par année
    - Formateur    : apprenants de ses cours uniquement
    - Apprenant    : ses propres progressions uniquement
    - Parent       : progressions de ses enfants
    """

    def _block_if_super_admin(self, request):
        if _is_super_admin(request.user):
            return api_error(
                "Les SuperAdmins ne gèrent pas les ressources internes.",
                http_status=status.HTTP_403_FORBIDDEN
            )
        return None

    def _filter_progression_apprenant_qs(self, qs, request):
        """Filtre ProgressionApprenant selon le rôle."""
        user = request.user
        role = _get_role(user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            qs = qs.filter(cours__institution_id=institution_id)
            # ✅ Filtre par année scolaire
            if annee_scolaire_id:
                qs = qs.filter(cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Formateur':
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            from courses.models import Cours
            cours_ids = Cours.objects.filter(
                enseignant=user, institution_id=institution_id
            ).values_list('id', flat=True)
            qs = qs.filter(cours_id__in=cours_ids)
            if annee_scolaire_id:
                qs = qs.filter(cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Apprenant':
            return qs.filter(apprenant=user)

        if role == 'Parent':
            enfants_ids = _get_enfants_ids(user)
            if not enfants_ids:
                return qs.none()
            return qs.filter(apprenant_id__in=enfants_ids)

        return qs.none()

    def _filter_progression_module_qs(self, qs, request):
        """Filtre ProgressionModule selon le rôle."""
        user = request.user
        role = _get_role(user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            qs = qs.filter(progression_apprenant__cours__institution_id=institution_id)
            if annee_scolaire_id:
                qs = qs.filter(progression_apprenant__cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Formateur':
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            from courses.models import Cours
            cours_ids = Cours.objects.filter(
                enseignant=user, institution_id=institution_id
            ).values_list('id', flat=True)
            qs = qs.filter(progression_apprenant__cours_id__in=cours_ids)
            if annee_scolaire_id:
                qs = qs.filter(progression_apprenant__cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Apprenant':
            return qs.filter(progression_apprenant__apprenant=user)

        if role == 'Parent':
            enfants_ids = _get_enfants_ids(user)
            if not enfants_ids:
                return qs.none()
            return qs.filter(progression_apprenant__apprenant_id__in=enfants_ids)

        return qs.none()

    def _filter_progression_sequence_qs(self, qs, request):
        """Filtre ProgressionSequence selon le rôle."""
        user = request.user
        role = _get_role(user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            qs = qs.filter(
                progression_module__progression_apprenant__cours__institution_id=institution_id
            )
            if annee_scolaire_id:
                qs = qs.filter(
                    progression_module__progression_apprenant__cours__annee_scolaire_id=annee_scolaire_id
                )
            return qs

        if role == 'Formateur':
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            from courses.models import Cours
            cours_ids = Cours.objects.filter(
                enseignant=user, institution_id=institution_id
            ).values_list('id', flat=True)
            qs = qs.filter(
                progression_module__progression_apprenant__cours_id__in=cours_ids
            )
            if annee_scolaire_id:
                qs = qs.filter(
                    progression_module__progression_apprenant__cours__annee_scolaire_id=annee_scolaire_id
                )
            return qs

        if role == 'Apprenant':
            return qs.filter(
                progression_module__progression_apprenant__apprenant=user
            )

        if role == 'Parent':
            enfants_ids = _get_enfants_ids(user)
            if not enfants_ids:
                return qs.none()
            return qs.filter(
                progression_module__progression_apprenant__apprenant_id__in=enfants_ids
            )

        return qs.none()

    def _filter_progression_quiz_qs(self, qs, request):
        """Filtre ProgressionQuiz selon le rôle."""
        user = request.user
        role = _get_role(user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            qs = qs.filter(progression_apprenant__cours__institution_id=institution_id)
            if annee_scolaire_id:
                qs = qs.filter(progression_apprenant__cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Formateur':
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            from courses.models import Cours
            cours_ids = Cours.objects.filter(
                enseignant=user, institution_id=institution_id
            ).values_list('id', flat=True)
            qs = qs.filter(progression_apprenant__cours_id__in=cours_ids)
            if annee_scolaire_id:
                qs = qs.filter(progression_apprenant__cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Apprenant':
            return qs.filter(progression_apprenant__apprenant=user)

        if role == 'Parent':
            enfants_ids = _get_enfants_ids(user)
            if not enfants_ids:
                return qs.none()
            return qs.filter(progression_apprenant__apprenant_id__in=enfants_ids)

        return qs.none()

    def _filter_historique_qs(self, qs, request):
        """Filtre HistoriqueActivite selon le rôle."""
        user = request.user
        role = _get_role(user)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            return qs.filter(apprenant__institution_id=institution_id)

        if role == 'Formateur':
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            from courses.models import Cours
            cours_ids = Cours.objects.filter(
                enseignant=user, institution_id=institution_id
            ).values_list('id', flat=True)
            from courses.models import InscriptionCours
            apprenant_ids = InscriptionCours.objects.filter(
                cours_id__in=cours_ids
            ).values_list('apprenant_id', flat=True).distinct()
            return qs.filter(apprenant_id__in=apprenant_ids)

        if role == 'Apprenant':
            return qs.filter(apprenant=user)

        if role == 'Parent':
            enfants_ids = _get_enfants_ids(user)
            if not enfants_ids:
                return qs.none()
            return qs.filter(apprenant_id__in=enfants_ids)

        return qs.none()

    def _filter_plan_action_qs(self, qs, request):
        """Filtre PlanAction selon le rôle."""
        user = request.user
        role = _get_role(user)
        annee_scolaire_id = _get_annee_scolaire_id(request)

        if role in ('Admin', 'ResponsableAcademique'):
            institution_id = getattr(user, 'institution_id', None)
            if not institution_id:
                return qs.none()
            qs = qs.filter(apprenant__institution_id=institution_id)
            if annee_scolaire_id:
                qs = qs.filter(cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Formateur':
            qs = qs.filter(cree_par=user)
            if annee_scolaire_id:
                qs = qs.filter(cours__annee_scolaire_id=annee_scolaire_id)
            return qs

        if role == 'Apprenant':
            return qs.filter(apprenant=user)

        if role == 'Parent':
            enfants_ids = _get_enfants_ids(user)
            if not enfants_ids:
                return qs.none()
            return qs.filter(apprenant_id__in=enfants_ids)

        return qs.none()


# ============================================================================
# VIEWSETS PROGRESSION
# ============================================================================

class ProgressionApprenantViewSet(ProgressionRoleFilterMixin, viewsets.ModelViewSet):
    """
    ViewSet pour gérer les progressions des apprenants dans les cours.

    Permissions :
    - SuperAdmin            : BLOQUÉ
    - Admin/Responsable     : tout leur institution, filtrable par année
    - Formateur             : apprenants de ses cours
    - Apprenant             : ses propres progressions
    - Parent                : progressions de ses enfants
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ProgressionApprenant.objects.select_related(
            'apprenant', 'cours', 'derniere_sequence', 'dernier_module'
        ).prefetch_related(
            'progressions_modules__progressions_sequences',
            'progressions_quiz',
        )

        # Filtrage par rôle
        qs = self._filter_progression_apprenant_qs(qs, self.request)

        # Filtres additionnels via query params
        apprenant_id = self.request.query_params.get('apprenant')
        if apprenant_id:
            qs = qs.filter(apprenant_id=apprenant_id)

        cours_id = self.request.query_params.get('cours')
        if cours_id:
            qs = qs.filter(cours_id=cours_id)

        statut = self.request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)

        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProgressionApprenantDetailSerializer
        elif self.action == 'create':
            return ProgressionApprenantCreateSerializer
        return ProgressionApprenantSerializer

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Liste des progressions récupérée avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions",
                             errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails de la progression récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur lors de la récupération des détails",
                             errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        # Seul l'Apprenant (ou Admin/Responsable) peut créer une progression
        if role not in ('Apprenant', 'Admin', 'ResponsableAcademique'):
            return api_error("Action non autorisée.", http_status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = ProgressionApprenantSerializer(instance)
            return api_success("Progression créée avec succès",
                               response_serializer.data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression mise à jour avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def partial_update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression mise à jour partiellement avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        if role not in ('Admin', 'ResponsableAcademique'):
            return api_error("Suppression réservée aux Admin/Responsable.",
                             http_status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        instance.delete()
        return api_success("Progression supprimée avec succès", None, status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def recalculer_progression(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression = self.get_object()
            pourcentage = progression.calculer_progression()
            return api_success("Progression recalculée avec succès", {
                'pourcentage_completion': pourcentage,
                'statut': progression.statut
            })
        except Exception as e:
            return api_error("Erreur lors du recalcul",
                             errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def recalculer_notes(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression = self.get_object()
            note_moyenne = progression.calculer_note_moyenne_evaluations()
            taux_reussite = progression.calculer_taux_reussite_quiz()
            return api_success("Notes recalculées avec succès", {
                'note_moyenne_evaluations': note_moyenne,
                'taux_reussite_quiz': taux_reussite
            })
        except Exception as e:
            return api_error("Erreur lors du recalcul des notes",
                             errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def statistiques(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression = self.get_object()
            stats = {
                'progression_globale': {
                    'pourcentage_completion': progression.pourcentage_completion,
                    'statut': progression.statut,
                    'temps_total_minutes': progression.temps_total_minutes,
                    'temps_total_formate': progression.temps_total_formate,
                },
                'modules': {
                    'total': progression.progressions_modules.count(),
                    'termines': progression.progressions_modules.filter(est_termine=True).count(),
                },
                'quiz': {
                    'total': progression.progressions_quiz.count(),
                    'reussis': progression.progressions_quiz.filter(pourcentage_reussite__gte=50).count(),
                    'taux_reussite_moyen': progression.taux_reussite_quiz,
                },
                'evaluations': {
                    'note_moyenne': progression.note_moyenne_evaluations,
                    'nombre_reussies': progression.nombre_evaluations_reussies,
                }
            }
            return api_success("Statistiques récupérées avec succès", stats)
        except Exception as e:
            return api_error("Erreur lors de la récupération des statistiques",
                             errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProgressionModuleViewSet(ProgressionRoleFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les progressions dans les modules."""

    serializer_class = ProgressionModuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ProgressionModule.objects.select_related(
            'progression_apprenant', 'module'
        ).prefetch_related('progressions_sequences')

        # Filtrage par rôle
        qs = self._filter_progression_module_qs(qs, self.request)

        progression_id = self.request.query_params.get('progression_apprenant')
        if progression_id:
            qs = qs.filter(progression_apprenant_id=progression_id)

        return qs

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Liste des progressions modules récupérée avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur lors de la récupération",
                             errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression module créée avec succès",
                               self.get_serializer(instance).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            return api_success("Progression module mise à jour avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def partial_update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression module mise à jour partiellement avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        if role not in ('Admin', 'ResponsableAcademique'):
            return api_error("Suppression réservée aux Admin/Responsable.",
                             http_status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        instance.delete()
        return api_success("Progression module supprimée avec succès", None, status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def marquer_termine(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression_module = self.get_object()
            progression_module.marquer_comme_termine()
            return api_success("Module marqué comme terminé avec succès", {
                'est_termine': progression_module.est_termine,
                'pourcentage_completion': progression_module.pourcentage_completion,
                'date_fin': progression_module.date_fin
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def enregistrer_temps(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression_module = self.get_object()
            minutes = request.data.get('minutes', 0)
            try:
                minutes = int(minutes)
                if minutes <= 0:
                    return api_error("Le nombre de minutes doit être positif.")
            except (ValueError, TypeError):
                return api_error("Format de minutes invalide.")

            progression_module.enregistrer_temps(minutes)
            return api_success(f"{minutes} minutes enregistrées avec succès", {
                'temps_passe_minutes': progression_module.temps_passe_minutes,
                'temps_total_cours': progression_module.progression_apprenant.temps_total_minutes
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProgressionSequenceViewSet(ProgressionRoleFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les progressions dans les séquences."""

    serializer_class = ProgressionSequenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ProgressionSequence.objects.select_related(
            'progression_module', 'sequence'
        )

        # Filtrage par rôle
        qs = self._filter_progression_sequence_qs(qs, self.request)

        progression_module_id = self.request.query_params.get('progression_module')
        if progression_module_id:
            qs = qs.filter(progression_module_id=progression_module_id)

        return qs

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Liste des progressions séquences récupérée avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression séquence créée avec succès",
                               self.get_serializer(instance).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression séquence mise à jour avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def partial_update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Progression séquence mise à jour partiellement avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        if role not in ('Admin', 'ResponsableAcademique'):
            return api_error("Suppression réservée aux Admin/Responsable.",
                             http_status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        instance.delete()
        return api_success("Progression séquence supprimée avec succès", None, status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def marquer_terminee(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression_sequence = self.get_object()
            progression_sequence.marquer_comme_terminee()
            return api_success("Séquence marquée comme terminée avec succès", {
                'est_terminee': progression_sequence.est_terminee,
                'date_fin': progression_sequence.date_fin
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def enregistrer_visite(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            progression_sequence = self.get_object()
            duree_minutes = request.data.get('duree_minutes', 0)
            try:
                duree_minutes = int(duree_minutes)
            except (ValueError, TypeError):
                return api_error("Format de durée invalide.")

            progression_sequence.enregistrer_visite(duree_minutes)
            return api_success("Visite enregistrée avec succès", {
                'nombre_visites': progression_sequence.nombre_visites,
                'temps_passe_minutes': progression_sequence.temps_passe_minutes
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProgressionQuizViewSet(ProgressionRoleFilterMixin, viewsets.ReadOnlyModelViewSet):
    """ViewSet pour consulter les progressions dans les quiz."""

    serializer_class = ProgressionQuizSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ProgressionQuiz.objects.select_related(
            'progression_apprenant', 'passage_quiz__quiz'
        )

        # Filtrage par rôle
        qs = self._filter_progression_quiz_qs(qs, self.request)

        progression_id = self.request.query_params.get('progression_apprenant')
        if progression_id:
            qs = qs.filter(progression_apprenant_id=progression_id)

        quiz_id = self.request.query_params.get('quiz')
        if quiz_id:
            qs = qs.filter(passage_quiz__quiz_id=quiz_id)

        return qs

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Liste des progressions quiz récupérée avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# HISTORIQUE & PLANS D'ACTION
# ============================================================================

class HistoriqueActiviteViewSet(ProgressionRoleFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer l'historique des activités."""

    serializer_class = HistoriqueActiviteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = HistoriqueActivite.objects.select_related('apprenant')

        # Filtrage par rôle
        qs = self._filter_historique_qs(qs, self.request)

        type_activite = self.request.query_params.get('type_activite')
        if type_activite:
            qs = qs.filter(type_activite=type_activite)

        date_debut = self.request.query_params.get('date_debut')
        if date_debut:
            qs = qs.filter(date_activite__gte=date_debut)

        date_fin = self.request.query_params.get('date_fin')
        if date_fin:
            qs = qs.filter(date_activite__lte=date_fin)

        # Filtre par apprenant — uniquement si autorisé par le rôle
        apprenant_id = self.request.query_params.get('apprenant')
        role = _get_role(self.request.user)
        if apprenant_id and role in ('Admin', 'ResponsableAcademique', 'Formateur'):
            qs = qs.filter(apprenant_id=apprenant_id)

        return qs.order_by('-date_activite')

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Historique des activités récupéré avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Activité enregistrée avec succès",
                               self.get_serializer(instance).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            return api_success("Activité mise à jour avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def partial_update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Activité mise à jour partiellement avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        if role not in ('Admin', 'ResponsableAcademique'):
            return api_error("Suppression réservée aux Admin/Responsable.",
                             http_status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        instance.delete()
        return api_success("Activité supprimée avec succès", None, status.HTTP_204_NO_CONTENT)


class PlanActionViewSet(ProgressionRoleFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les plans d'action."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PlanAction.objects.select_related(
            'apprenant', 'cours', 'cree_par'
        ).prefetch_related('objectifs')

        # Filtrage par rôle
        qs = self._filter_plan_action_qs(qs, self.request)

        cours_id = self.request.query_params.get('cours')
        if cours_id:
            qs = qs.filter(cours_id=cours_id)

        statut = self.request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)

        # Filtre par apprenant (Admin/Responsable/Formateur seulement)
        apprenant_id = self.request.query_params.get('apprenant')
        role = _get_role(self.request.user)
        if apprenant_id and role in ('Admin', 'ResponsableAcademique', 'Formateur'):
            qs = qs.filter(apprenant_id=apprenant_id)

        return qs

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PlanActionCreateSerializer
        return PlanActionSerializer

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Liste des plans d'action récupérée avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails du plan d'action récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = PlanActionSerializer(instance)
            return api_success("Plan d'action créé avec succès",
                               response_serializer.data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = PlanActionSerializer(instance)
            return api_success("Plan d'action mis à jour avec succès", response_serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def partial_update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = PlanActionSerializer(instance)
            return api_success("Plan d'action mis à jour partiellement avec succès", response_serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        if role not in ('Admin', 'ResponsableAcademique'):
            return api_error("Suppression réservée aux Admin/Responsable.",
                             http_status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        instance.delete()
        return api_success("Plan d'action supprimé avec succès", None, status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def marquer_termine(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            plan = self.get_object()
            plan.marquer_comme_termine()
            return api_success("Plan d'action marqué comme terminé avec succès", {
                'statut': plan.statut,
                'date_completion': plan.date_completion
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ObjectifPlanActionViewSet(ProgressionRoleFilterMixin, viewsets.ModelViewSet):
    """ViewSet pour gérer les objectifs des plans d'action."""

    serializer_class = ObjectifPlanActionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)

        qs = ObjectifPlanAction.objects.select_related('plan_action')

        # Filtrage via les plans d'action du rôle
        plan_ids = self._filter_plan_action_qs(
            PlanAction.objects.all(), self.request
        ).values_list('id', flat=True)
        qs = qs.filter(plan_action_id__in=plan_ids)

        plan_id = self.request.query_params.get('plan_action')
        if plan_id:
            qs = qs.filter(plan_action_id=plan_id)

        return qs.order_by('ordre')

    def list(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success("Liste des objectifs récupérée avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success("Détails de l'objectif récupérés avec succès", serializer.data)
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Objectif créé avec succès",
                               self.get_serializer(instance).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors)

    def update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Objectif mis à jour avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def partial_update(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success("Objectif mis à jour partiellement avec succès", serializer.data)
        return api_error("Erreur de validation", errors=serializer.errors)

    def destroy(self, request, *args, **kwargs):
        err = self._block_if_super_admin(request)
        if err:
            return err
        role = _get_role(request.user)
        if role not in ('Admin', 'ResponsableAcademique', 'Formateur'):
            return api_error("Suppression non autorisée.", http_status=status.HTTP_403_FORBIDDEN)
        instance = self.get_object()
        instance.delete()
        return api_success("Objectif supprimé avec succès", None, status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def marquer_complete(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            objectif = self.get_object()
            objectif.marquer_comme_complete()
            return api_success("Objectif marqué comme complété avec succès", {
                'est_complete': objectif.est_complete,
                'date_completion': objectif.date_completion
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def marquer_incomplete(self, request, pk=None):
        err = self._block_if_super_admin(request)
        if err:
            return err
        try:
            objectif = self.get_object()
            objectif.marquer_comme_incomplete()
            return api_success("Objectif marqué comme incomplet avec succès", {
                'est_complete': objectif.est_complete
            })
        except Exception as e:
            return api_error("Erreur", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)