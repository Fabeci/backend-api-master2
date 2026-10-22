# progress/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.rbac import RBACPermission
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    ProgressionApprenant,
    ProgressionModule,
    ProgressionSequence,
    ProgressionQuiz,
    HistoriqueActivite,
    SessionApprenant,
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
    SessionApprenantSerializer,
    PlanActionSerializer,
    PlanActionCreateSerializer,
    ObjectifPlanActionSerializer,
)

# ✅ SÉCURITÉ : contrôle d'accès par apprenant (anti-IDOR)
from users.access_control import accessible_apprenants, user_can_access_apprenant
from users.models import Apprenant


# ============================================================================
# FONCTIONS UTILITAIRES (vos méthodes standards)
# ============================================================================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    """Réponse standardisée pour les succès"""
    return Response(
        {
            "success": True,
            "status": http_status,
            "message": message,
            "data": data,
        },
        status=http_status,
    )


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST, data=None):
    """Réponse standardisée pour les erreurs"""
    # Message plus précis quand des erreurs de champ sont fournies
    if errors and isinstance(errors, dict) and (not message or message == "Erreur de validation"):
        for _field, _val in errors.items():
            _msgs = _val if isinstance(_val, (list, tuple)) else [_val]
            _first = next((str(m) for m in _msgs if m), None)
            if _first:
                message = f"{_field} : {_first}"
                break
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
        "data": data,
    }
    _code_map = {
        400: "VALIDATION_ERROR", 401: "NOT_AUTHENTICATED", 403: "PERMISSION_DENIED",
        404: "NOT_FOUND", 409: "CONFLICT", 429: "THROTTLED",
    }
    payload["code"] = _code_map.get(http_status, "SERVER_ERROR" if http_status >= 500 else "ERROR")
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


def _deny_foreign_apprenant(request):
    """
    ✅ SÉCURITÉ : retourne une réponse 403 si le payload cible un apprenant
    dont l'accès n'est pas autorisé pour l'utilisateur courant. None sinon.
    """
    raw = request.data.get("apprenant") if hasattr(request.data, "get") else None
    if raw in (None, ""):
        return None
    try:
        from users.models import Apprenant
        target = Apprenant.objects.filter(pk=raw).first()
    except (ValueError, TypeError):
        return None
    if target is not None and not user_can_access_apprenant(request.user, target):
        return api_error(
            "Accès refusé : cet apprenant n'est pas dans votre périmètre.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _check_progression_target(request):
    """✅ PÉRIMÈTRE : interdit d'écrire la progression d'un apprenant hors
    périmètre. Les ViewSets ProgressionModule/Sequence ne fournissent que la FK
    parente (`progression_apprenant` / `progression_module`) : on remonte donc
    la chaîne jusqu'à l'apprenant réel."""
    user = request.user
    try:
        from users.access_control import is_global_reader
        if is_global_reader(user):
            return None
    except Exception:
        pass

    data = request.data if hasattr(request.data, "get") else {}

    def _resolve():
        raw = data.get("apprenant")
        if raw:
            return Apprenant.objects.filter(pk=raw).first()
        raw = data.get("progression_apprenant")
        if raw:
            pa = ProgressionApprenant.objects.filter(pk=raw).select_related("apprenant").first()
            return pa.apprenant if pa else None
        raw = data.get("progression_module")
        if raw:
            pm = ProgressionModule.objects.filter(pk=raw).select_related("progression_apprenant__apprenant").first()
            return pm.progression_apprenant.apprenant if pm else None
        return None

    try:
        target = _resolve()
    except Exception:
        target = None

    if target is not None and not user_can_access_apprenant(user, target):
        return api_error(
            "Accès refusé : cet apprenant n'est pas dans votre périmètre.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return None


# ============================================================================
# VIEWSETS PROGRESSION
# ============================================================================

class ProgressionApprenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les progressions des apprenants dans les cours.
    """
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "progression"
    
    def get_queryset(self):
        queryset = ProgressionApprenant.objects.select_related(
            'apprenant',
            'cours',
            'derniere_sequence',
            'dernier_module'
        ).prefetch_related(
            'progressions_modules__progressions_sequences',
            'progressions_quiz',
        )
        
        # Filtrer par apprenant si paramètre fourni
        apprenant_id = self.request.query_params.get('apprenant')
        if apprenant_id:
            queryset = queryset.filter(apprenant_id=apprenant_id)
        
        # Filtrer par cours si paramètre fourni
        cours_id = self.request.query_params.get('cours')
        if cours_id:
            queryset = queryset.filter(cours_id=cours_id)
        
        # Filtrer par statut
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(apprenant__in=allowed)

        return queryset
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProgressionApprenantDetailSerializer
        elif self.action == 'create':
            return ProgressionApprenantCreateSerializer
        return ProgressionApprenantSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste des progressions"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Liste des progressions récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'une progression"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails de la progression récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Créer une progression"""
        denied = _deny_foreign_apprenant(request)
        if denied:
            return denied
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = ProgressionApprenantSerializer(instance)
            return api_success(
                "Progression créée avec succès",
                response_serializer.data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def update(self, request, *args, **kwargs):
        """Mettre à jour une progression (PUT)"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Mettre à jour partiellement une progression (PATCH)"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def destroy(self, request, *args, **kwargs):
        """Supprimer une progression"""
        instance = self.get_object()
        instance.delete()
        return api_success(
            "Progression supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=True, methods=['post'])
    def recalculer_progression(self, request, pk=None):
        """Recalcule la progression globale"""
        try:
            progression = self.get_object()
            pourcentage = progression.calculer_progression()
            return api_success(
                "Progression recalculée avec succès",
                {
                    'pourcentage_completion': pourcentage,
                    'statut': progression.statut
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du recalcul de la progression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def recalculer_notes(self, request, pk=None):
        """Recalcule les notes moyennes"""
        try:
            progression = self.get_object()
            note_moyenne = progression.calculer_note_moyenne_evaluations()
            taux_reussite = progression.calculer_taux_reussite_quiz()
            
            return api_success(
                "Notes recalculées avec succès",
                {
                    'note_moyenne_evaluations': note_moyenne,
                    'taux_reussite_quiz': taux_reussite
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du recalcul des notes",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def statistiques(self, request, pk=None):
        """Statistiques détaillées de la progression"""
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
            
            return api_success(
                "Statistiques récupérées avec succès",
                stats,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des statistiques",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProgressionModuleViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les progressions dans les modules"""
    
    serializer_class = ProgressionModuleSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "progression"
    
    def get_queryset(self):
        queryset = ProgressionModule.objects.select_related(
            'progression_apprenant',
            'module'
        ).prefetch_related('progressions_sequences')
        
        # Filtrer par progression apprenant
        progression_id = self.request.query_params.get('progression_apprenant')
        if progression_id:
            queryset = queryset.filter(progression_apprenant_id=progression_id)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(progression_apprenant__apprenant__in=allowed)

        return queryset
    
    def list(self, request, *args, **kwargs):
        """Liste des progressions modules"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Liste des progressions modules récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions modules",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'une progression module"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails de la progression module récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Créer une progression module"""
        # ✅ PÉRIMÈTRE : empêche d'écrire la progression d'un autre apprenant
        err = _check_progression_target(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression module créée avec succès",
                self.get_serializer(instance).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def update(self, request, *args, **kwargs):
        """Mettre à jour une progression module"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression module mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Mettre à jour partiellement une progression module"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression module mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def destroy(self, request, *args, **kwargs):
        """Supprimer une progression module"""
        instance = self.get_object()
        instance.delete()
        return api_success(
            "Progression module supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=True, methods=['post'])
    def marquer_termine(self, request, pk=None):
        """Marque le module comme terminé"""
        try:
            progression_module = self.get_object()
            progression_module.marquer_comme_termine()
            
            return api_success(
                "Module marqué comme terminé avec succès",
                {
                    'est_termine': progression_module.est_termine,
                    'pourcentage_completion': progression_module.pourcentage_completion,
                    'date_fin': progression_module.date_fin
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du marquage du module",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def enregistrer_temps(self, request, pk=None):
        """Enregistre du temps passé sur le module"""
        try:
            progression_module = self.get_object()
            minutes = request.data.get('minutes', 0)
            
            try:
                minutes = int(minutes)
                if minutes <= 0:
                    return api_error(
                        "Le nombre de minutes doit être positif",
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return api_error(
                    "Format de minutes invalide",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            progression_module.enregistrer_temps(minutes)
            return api_success(
                f"{minutes} minutes enregistrées avec succès",
                {
                    'temps_passe_minutes': progression_module.temps_passe_minutes,
                    'temps_total_cours': progression_module.progression_apprenant.temps_total_minutes
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de l'enregistrement du temps",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProgressionSequenceViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les progressions dans les séquences"""
    
    serializer_class = ProgressionSequenceSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "progression"
    
    def get_queryset(self):
        queryset = ProgressionSequence.objects.select_related(
            'progression_module',
            'sequence'
        )
        
        # Filtrer par progression module
        progression_module_id = self.request.query_params.get('progression_module')
        if progression_module_id:
            queryset = queryset.filter(progression_module_id=progression_module_id)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(progression_module__progression_apprenant__apprenant__in=allowed)

        return queryset
    
    def list(self, request, *args, **kwargs):
        """Liste des progressions séquences"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Liste des progressions séquences récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions séquences",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'une progression séquence"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails de la progression séquence récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Créer une progression séquence"""
        # ✅ PÉRIMÈTRE : empêche d'écrire la progression d'un autre apprenant
        err = _check_progression_target(request)
        if err:
            return err
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression séquence créée avec succès",
                self.get_serializer(instance).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def update(self, request, *args, **kwargs):
        """Mettre à jour une progression séquence"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression séquence mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Mettre à jour partiellement une progression séquence"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Progression séquence mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def destroy(self, request, *args, **kwargs):
        """Supprimer une progression séquence"""
        instance = self.get_object()
        instance.delete()
        return api_success(
            "Progression séquence supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=True, methods=['post'])
    def marquer_terminee(self, request, pk=None):
        """Marque la séquence comme terminée"""
        try:
            progression_sequence = self.get_object()
            progression_sequence.marquer_comme_terminee()
            
            return api_success(
                "Séquence marquée comme terminée avec succès",
                {
                    'est_terminee': progression_sequence.est_terminee,
                    'date_fin': progression_sequence.date_fin
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du marquage de la séquence",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def enregistrer_visite(self, request, pk=None):
        """Enregistre une visite de la séquence"""
        try:
            progression_sequence = self.get_object()
            duree_minutes = request.data.get('duree_minutes', 0)
            
            try:
                duree_minutes = int(duree_minutes)
            except (ValueError, TypeError):
                return api_error(
                    "Format de durée invalide",
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            progression_sequence.enregistrer_visite(duree_minutes)
            
            return api_success(
                "Visite enregistrée avec succès",
                {
                    'nombre_visites': progression_sequence.nombre_visites,
                    'temps_passe_minutes': progression_sequence.temps_passe_minutes
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de l'enregistrement de la visite",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ProgressionQuizViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet pour consulter les progressions dans les quiz"""
    
    serializer_class = ProgressionQuizSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "progression"
    
    def get_queryset(self):
        queryset = ProgressionQuiz.objects.select_related(
            'progression_apprenant',
            'passage_quiz__quiz'
        )
        
        # Filtrer par progression apprenant
        progression_id = self.request.query_params.get('progression_apprenant')
        if progression_id:
            queryset = queryset.filter(progression_apprenant_id=progression_id)
        
        # Filtrer par quiz
        quiz_id = self.request.query_params.get('quiz')
        if quiz_id:
            queryset = queryset.filter(passage_quiz__quiz_id=quiz_id)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(progression_apprenant__apprenant__in=allowed)

        return queryset
    
    def list(self, request, *args, **kwargs):
        """Liste des progressions quiz"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Liste des progressions quiz récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions quiz",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'une progression quiz"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails de la progression quiz récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# VIEWSETS HISTORIQUE ET PLANS D'ACTION
# ============================================================================

class HistoriqueActiviteViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer l'historique des activités"""
    
    serializer_class = HistoriqueActiviteSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "historique"

    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk(self, request):
        """Enregistre un LOT d'activités en une seule requête (tracage frontend)."""
        items = request.data.get('activites') if isinstance(request.data, dict) else request.data
        if not isinstance(items, list):
            items = [items] if items else []
        created, errors = 0, []
        for raw in items[:300]:
            if not isinstance(raw, dict):
                continue
            appr = Apprenant.objects.filter(pk=raw.get('apprenant')).first()
            if not appr or not user_can_access_apprenant(request.user, appr):
                errors.append({'apprenant': raw.get('apprenant'), 'error': 'non autorisé'})
                continue
            try:
                HistoriqueActivite.objects.create(
                    apprenant=appr,
                    type_activite=raw.get('type_activite', 'autre'),
                    objet_type=raw.get('objet_type', '') or '',
                    objet_id=raw.get('objet_id'),
                    duree_minutes=int(raw.get('duree_minutes') or 0),
                    duree_secondes=int(raw.get('duree_secondes') or 0),
                    description=raw.get('description', '') or '',
                    metadata=raw.get('metadata') or {},
                )
                created += 1
            except Exception as e:
                errors.append({'raw': str(raw)[:120], 'error': str(e)})
        return api_success(
            f"{created} activité(s) enregistrée(s)",
            {'created': created, 'errors': errors},
            status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'], url_path='rapport')
    def rapport(self, request):
        """Rapport agrégé d'activité des apprenants (dashboard Admin/Formateur)."""
        from django.db.models import Sum, Count, Q

        debut = request.query_params.get('date_debut')
        fin = request.query_params.get('date_fin')
        apprenant_id = request.query_params.get('apprenant')

        qs = HistoriqueActivite.objects.all()
        sessions = SessionApprenant.objects.all()

        allowed = accessible_apprenants(request.user)
        if allowed is not None:
            qs = qs.filter(apprenant__in=allowed)
            sessions = sessions.filter(apprenant__in=allowed)
        if apprenant_id:
            qs = qs.filter(apprenant_id=apprenant_id)
            sessions = sessions.filter(apprenant_id=apprenant_id)
        if debut:
            qs = qs.filter(date_activite__gte=debut)
            sessions = sessions.filter(date_debut__gte=debut)
        if fin:
            qs = qs.filter(date_activite__lte=fin)
            sessions = sessions.filter(date_debut__lte=fin)

        def _i(v):
            return int(v or 0)

        q_agg = qs.aggregate(
            nb_pages=Count('id', filter=Q(type_activite='page_vue')),
            temps_page=Sum('duree_secondes', filter=Q(type_activite='page_vue')),
            nb_pratique=Count('id', filter=Q(type_activite__in=['consultation_cours', 'consultation_bloc', 'consultation_module'])),
            nb_eval=Count('id', filter=Q(type_activite__in=['debut_evaluation', 'soumission_evaluation', 'debut_quiz', 'fin_quiz', 'soumission_quiz'])),
            nb_inact=Count('id', filter=Q(type_activite='inactivite')),
            temps_inact=Sum('duree_secondes', filter=Q(type_activite='inactivite')),
            nb_offline=Count('id', filter=Q(type_activite='perte_connexion')),
            nb_onglet_masque=Count('id', filter=Q(type_activite='onglet_masque')),
            temps_onglet_masque=Sum('duree_secondes', filter=Q(type_activite='onglet_masque')),
            nb_fenetre_inactive=Count('id', filter=Q(type_activite='fenetre_inactive')),
            temps_fenetre_inactive=Sum('duree_secondes', filter=Q(type_activite='fenetre_inactive')),
            nb_hors_app=Count('id', filter=Q(type_activite__in=['onglet_masque', 'fenetre_inactive'])),
            temps_hors_app=Sum('duree_secondes', filter=Q(type_activite__in=['onglet_masque', 'fenetre_inactive'])),
            nb_apprenants=Count('apprenant', distinct=True),
        )
        s_agg = sessions.aggregate(nb=Count('id'), duree=Sum('duree_secondes'))

        top_pages = list(
            qs.filter(type_activite='page_vue')
              .values('description')
              .annotate(vues=Count('id'), temps=Sum('duree_secondes'))
              .order_by('-temps')[:12]
        )
        for t in top_pages:
            t['temps'] = _i(t['temps'])
            t['temps_moyen'] = round(t['temps'] / t['vues']) if t['vues'] else 0

        temps_par_type = list(
            qs.values('type_activite')
              .annotate(total=Sum('duree_secondes'), nb=Count('id'))
              .order_by('-total')[:12]
        )

        par_apprenant = list(
            qs.values('apprenant__id', 'apprenant__nom', 'apprenant__prenom')
              .annotate(pages=Count('id', filter=Q(type_activite='page_vue')),
                        temps=Sum('duree_secondes', filter=Q(type_activite='page_vue')),
                        inact=Count('id', filter=Q(type_activite='inactivite')))
              .order_by('-temps')[:20]
        )

        sessions_list = [
            {
                'id': s.id,
                'apprenant': s.apprenant_id,
                'apprenant_nom': f"{s.apprenant.prenom} {s.apprenant.nom}" if s.apprenant_id else '',
                'date_debut': s.date_debut, 'date_fin': s.date_fin,
                'duree_secondes': s.duree_effective_secondes,
                'fin_reason': s.fin_reason, 'actif': s.actif, 'ip_address': s.ip_address,
            }
            for s in sessions.select_related('apprenant').order_by('-date_debut')[:25]
        ]

        nb_sessions = _i(s_agg['nb'])
        duree_totale = _i(s_agg['duree'])
        kpis = {
            'nb_apprenants': _i(q_agg['nb_apprenants']),
            'nb_sessions': nb_sessions,
            'duree_totale_s': duree_totale,
            'duree_moyenne_session_s': round(duree_totale / nb_sessions) if nb_sessions else 0,
            'nb_pages_vues': _i(q_agg['nb_pages']),
            'temps_page_s': _i(q_agg['temps_page']),
            'temps_moyen_page_s': round(_i(q_agg['temps_page']) / _i(q_agg['nb_pages'])) if _i(q_agg['nb_pages']) else 0,
            'nb_consultations': _i(q_agg['nb_pratique']),
            'nb_evaluations': _i(q_agg['nb_eval']),
            'nb_inactivites': _i(q_agg['nb_inact']),
            'temps_inactivite_s': _i(q_agg['temps_inact']),
            'nb_pertes_connexion': _i(q_agg['nb_offline']),
            'nb_onglet_masque': _i(q_agg['nb_onglet_masque']),
            'temps_onglet_masque_s': _i(q_agg['temps_onglet_masque']),
            'nb_fenetre_inactive': _i(q_agg['nb_fenetre_inactive']),
            'temps_fenetre_inactive_s': _i(q_agg['temps_fenetre_inactive']),
            'nb_sorties_application': _i(q_agg['nb_hors_app']),
            'temps_hors_application_s': _i(q_agg['temps_hors_app']),
        }

        return api_success("Rapport d'activité", {
            'kpis': kpis,
            'top_pages': top_pages,
            'temps_par_type': temps_par_type,
            'par_apprenant': par_apprenant,
            'sessions': sessions_list,
        })

    def get_queryset(self):
        queryset = HistoriqueActivite.objects.select_related('apprenant')
        
        # Filtrer par apprenant
        apprenant_id = self.request.query_params.get('apprenant')
        if apprenant_id:
            queryset = queryset.filter(apprenant_id=apprenant_id)
        
        # Filtrer par type d'activité
        type_activite = self.request.query_params.get('type_activite')
        if type_activite:
            queryset = queryset.filter(type_activite=type_activite)
        
        # Filtrer par date
        date_debut = self.request.query_params.get('date_debut')
        if date_debut:
            queryset = queryset.filter(date_activite__gte=date_debut)
        
        date_fin = self.request.query_params.get('date_fin')
        if date_fin:
            queryset = queryset.filter(date_activite__lte=date_fin)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(apprenant__in=allowed)

        return queryset.order_by('-date_activite')
    
    def list(self, request, *args, **kwargs):
        """Liste des activités"""
        try:
            queryset = self.get_queryset()
            # ✅ Limite optionnelle (?limit=N) — utilisée par le détail de cours (5).
            limit = request.query_params.get('limit')
            if limit:
                try:
                    queryset = queryset[:max(1, int(limit))]
                except (ValueError, TypeError):
                    pass
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Historique des activités récupéré avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération de l'historique",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'une activité"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails de l'activité récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Créer une activité"""
        denied = _deny_foreign_apprenant(request)
        if denied:
            return denied
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Activité enregistrée avec succès",
                self.get_serializer(instance).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def update(self, request, *args, **kwargs):
        """Mettre à jour une activité"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Activité mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Mettre à jour partiellement une activité"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Activité mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def destroy(self, request, *args, **kwargs):
        """Supprimer une activité"""
        instance = self.get_object()
        instance.delete()
        return api_success(
            "Activité supprimée avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )


class PlanActionViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les plans d'action"""
    
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "planAction"
    
    def get_queryset(self):
        queryset = PlanAction.objects.select_related(
            'apprenant',
            'cours',
            'cree_par'
        ).prefetch_related('objectifs')
        
        # Filtrer par apprenant
        apprenant_id = self.request.query_params.get('apprenant')
        if apprenant_id:
            queryset = queryset.filter(apprenant_id=apprenant_id)
        
        # Filtrer par cours
        cours_id = self.request.query_params.get('cours')
        if cours_id:
            queryset = queryset.filter(cours_id=cours_id)
        
        # Filtrer par statut
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(apprenant__in=allowed)

        return queryset
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PlanActionCreateSerializer
        return PlanActionSerializer
    
    def list(self, request, *args, **kwargs):
        """Liste des plans d'action"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Liste des plans d'action récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des plans d'action",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'un plan d'action"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails du plan d'action récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Créer un plan d'action"""
        denied = _deny_foreign_apprenant(request)
        if denied:
            return denied
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = PlanActionSerializer(instance)
            return api_success(
                "Plan d'action créé avec succès",
                response_serializer.data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def update(self, request, *args, **kwargs):
        """Mettre à jour un plan d'action"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = PlanActionSerializer(instance)
            return api_success(
                "Plan d'action mis à jour avec succès",
                response_serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Mettre à jour partiellement un plan d'action"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            response_serializer = PlanActionSerializer(instance)
            return api_success(
                "Plan d'action mis à jour partiellement avec succès",
                response_serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def destroy(self, request, *args, **kwargs):
        """Supprimer un plan d'action"""
        instance = self.get_object()
        instance.delete()
        return api_success(
            "Plan d'action supprimé avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=True, methods=['post'])
    def marquer_termine(self, request, pk=None):
        """Marque le plan comme terminé"""
        try:
            plan = self.get_object()
            plan.marquer_comme_termine()
            
            return api_success(
                "Plan d'action marqué comme terminé avec succès",
                {
                    'statut': plan.statut,
                    'date_completion': plan.date_completion
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du marquage du plan",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ObjectifPlanActionViewSet(viewsets.ModelViewSet):
    """ViewSet pour gérer les objectifs des plans d'action"""
    
    serializer_class = ObjectifPlanActionSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "planAction"
    
    def get_queryset(self):
        queryset = ObjectifPlanAction.objects.select_related('plan_action')
        
        # Filtrer par plan d'action
        plan_id = self.request.query_params.get('plan_action')
        if plan_id:
            queryset = queryset.filter(plan_action_id=plan_id)

        # ✅ SÉCURITÉ : limiter aux apprenants autorisés (anti-IDOR).
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            queryset = queryset.filter(plan_action__apprenant__in=allowed)

        return queryset.order_by('ordre')
    
    def list(self, request, *args, **kwargs):
        """Liste des objectifs"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return api_success(
                "Liste des objectifs récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des objectifs",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Détails d'un objectif"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return api_success(
                "Détails de l'objectif récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des détails",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Créer un objectif"""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Objectif créé avec succès",
                self.get_serializer(instance).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def update(self, request, *args, **kwargs):
        """Mettre à jour un objectif"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Objectif mis à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Mettre à jour partiellement un objectif"""
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            instance = serializer.save()
            return api_success(
                "Objectif mis à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )
    
    def destroy(self, request, *args, **kwargs):
        """Supprimer un objectif"""
        instance = self.get_object()
        instance.delete()
        return api_success(
            "Objectif supprimé avec succès",
            None,
            status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=True, methods=['post'])
    def marquer_complete(self, request, pk=None):
        """Marque l'objectif comme complété"""
        try:
            objectif = self.get_object()
            objectif.marquer_comme_complete()
            
            return api_success(
                "Objectif marqué comme complété avec succès",
                {
                    'est_complete': objectif.est_complete,
                    'date_completion': objectif.date_completion
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du marquage de l'objectif",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def marquer_incomplete(self, request, pk=None):
        """Marque l'objectif comme incomplet"""
        try:
            objectif = self.get_object()
            objectif.marquer_comme_incomplete()
            
            return api_success(
                "Objectif marqué comme incomplet avec succès",
                {
                    'est_complete': objectif.est_complete
                },
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors du marquage de l'objectif",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ============================================================================
# SESSION APPRENANT — démarrer / heartbeat / terminer
# ============================================================================

class SessionApprenantViewSet(viewsets.ModelViewSet):
    """Sessions des apprenants : démarrer, heartbeat, terminer, lister."""
    serializer_class = SessionApprenantSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    rbac_resource = "progression"

    def create(self, request, *args, **kwargs):
        """✅ PÉRIMÈTRE : empêche de créer une session au nom d'un autre apprenant."""
        err = _check_progression_target(request)
        if err:
            return err
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        qs = SessionApprenant.objects.select_related('apprenant')
        apprenant_id = self.request.query_params.get('apprenant')
        if apprenant_id:
            qs = qs.filter(apprenant_id=apprenant_id)
        actif = self.request.query_params.get('actif')
        if actif in ('1', 'true', 'True'):
            qs = qs.filter(actif=True)
        allowed = accessible_apprenants(self.request.user)
        if allowed is not None:
            qs = qs.filter(apprenant__in=allowed)
        return qs.order_by('-date_debut')

    def _client_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR')

    @action(detail=False, methods=['post'], url_path='demarrer')
    def demarrer(self, request):
        appr = Apprenant.objects.filter(pk=request.data.get('apprenant')).first()
        if not appr or not user_can_access_apprenant(request.user, appr):
            return api_error("Apprenant non autorisé", http_status=status.HTTP_403_FORBIDDEN)
        # On clôt toute session active restée ouverte (navigateur fermé sans logout)
        SessionApprenant.objects.filter(apprenant=appr, actif=True).update(
            actif=False, date_fin=timezone.now(), fin_reason='expiration'
        )
        s = SessionApprenant.objects.create(
            apprenant=appr,
            ip_address=self._client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
        )
        return api_success("Session démarrée", SessionApprenantSerializer(s).data, status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='heartbeat')
    def heartbeat(self, request):
        s = SessionApprenant.objects.filter(pk=request.data.get('session'), actif=True).first()
        if not s or not user_can_access_apprenant(request.user, s.apprenant):
            return api_error("Session introuvable", http_status=status.HTTP_404_NOT_FOUND)
        s.touch()
        return api_success("ok", {'id': s.id, 'duree_secondes': s.duree_effective_secondes})

    @action(detail=False, methods=['post'], url_path='terminer')
    def terminer(self, request):
        s = SessionApprenant.objects.filter(pk=request.data.get('session'), actif=True).first()
        if not s or not user_can_access_apprenant(request.user, s.apprenant):
            return api_error("Session introuvable", http_status=status.HTTP_404_NOT_FOUND)
        s.terminer(request.data.get('reason') or 'inconnue')
        return api_success("Session terminée", SessionApprenantSerializer(s).data)
