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
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
        "data": data,
    }
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# ============================================================================
# VIEWSETS PROGRESSION
# ============================================================================

class ProgressionApprenantViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour gérer les progressions des apprenants dans les cours.
    """
    permission_classes = [IsAuthenticated]
    
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
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ProgressionModule.objects.select_related(
            'progression_apprenant',
            'module'
        ).prefetch_related('progressions_sequences')
        
        # Filtrer par progression apprenant
        progression_id = self.request.query_params.get('progression_apprenant')
        if progression_id:
            queryset = queryset.filter(progression_apprenant_id=progression_id)
        
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
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ProgressionSequence.objects.select_related(
            'progression_module',
            'sequence'
        )
        
        # Filtrer par progression module
        progression_module_id = self.request.query_params.get('progression_module')
        if progression_module_id:
            queryset = queryset.filter(progression_module_id=progression_module_id)
        
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
    permission_classes = [IsAuthenticated]
    
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
    permission_classes = [IsAuthenticated]
    
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
        
        return queryset.order_by('-date_activite')
    
    def list(self, request, *args, **kwargs):
        """Liste des activités"""
        try:
            queryset = self.get_queryset()
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
    
    permission_classes = [IsAuthenticated]
    
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
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ObjectifPlanAction.objects.select_related('plan_action')
        
        # Filtrer par plan d'action
        plan_id = self.request.query_params.get('plan_action')
        if plan_id:
            queryset = queryset.filter(plan_action_id=plan_id)
        
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