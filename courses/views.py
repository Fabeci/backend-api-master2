# courses/views.py

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.http import FileResponse, Http404

from academics.models import Inscription
from courses.utils import can_create_in_context, filter_queryset_by_role, get_filtered_object, get_user_context
from .models import (
    BlocContenu,
    BlocProgress,
    Cours,
    CoursProgress, 
    InscriptionCours, 
    Module,
    ModuleProgress, 
    Participation,
    RessourceSequence, 
    Sequence,
    SequenceProgress, 
    Session, 
    Suivi
)
from .serializers import (
    BlocContenuCreateSerializer,
    BlocContenuSerializer,
    BlocProgressSerializer,
    CoursProgressSerializer,
    CoursSerializer, 
    InscriptionCoursSerializer,
    ModuleProgressSerializer, 
    ModuleSerializer, 
    ParticipationSerializer,
    ProgressToggleSerializer,
    RessourceSequenceCreateSerializer,
    RessourceSequenceSerializer,
    SequenceContentSerializer,
    SequenceDetailSerializer,
    SequenceProgressSerializer, 
    SequenceSerializer,
    SessionLiteSerializer, 
    SessionSerializer, 
    SuiviSerializer
)


# ============================================================================
# FONCTIONS UTILITAIRES
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
# COURS
# ============================================================================

class CoursListCreateAPIView(APIView):
    """
    Liste et création de cours.
    
    FILTRAGE PAR RÔLE :
    - SuperUser : Tous les cours
    - Admin : Tous les cours de son institution
    - Responsable : Cours de son institution + année
    - Formateur : UNIQUEMENT SES cours (enseignant=lui)
    - Apprenant : Cours inscrits uniquement
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Liste les cours selon le rôle"""
        try:
            qs = Cours.objects.select_related(
                "groupe", "matiere", "enseignant", "institution", "annee_scolaire"
            ).all()
            
            # Filtrage par rôle (incluant Formateur strict)
            qs = filter_queryset_by_role(qs, request, 'Cours')
            
            qs = qs.order_by("-id")
            data = CoursSerializer(qs, many=True).data
            
            return api_success(
                "Liste des cours récupérée avec succès", 
                data, 
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des cours",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée un nouveau cours"""
        serializer = CoursSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            
            # Auto-assignation pour non-SuperUser
            if not user.is_superuser:
                if 'institution' not in request.data and user.institution:
                    serializer.validated_data['institution'] = user.institution
                
                if 'annee_scolaire' not in request.data and user.annee_scolaire_active:
                    serializer.validated_data['annee_scolaire'] = user.annee_scolaire_active
                
                # Pour Formateur : s'auto-assigner comme enseignant
                role_name = user.role.name if user.role else None
                if role_name == 'Formateur' and 'enseignant' not in request.data:
                    serializer.validated_data['enseignant'] = user
            
            obj = serializer.save()
            return api_success(
                "Cours créé avec succès",
                CoursSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class CoursDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère un cours filtré par rôle"""
        return get_filtered_object(Cours, pk, request, 'Cours')

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success(
            "Cours trouvé avec succès", 
            CoursSerializer(obj).data, 
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        
        # Formateur ne peut modifier que SES cours
        if not can_create_in_context(request.user, obj):
            return api_error(
                "Vous ne pouvez pas modifier ce cours",
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = CoursSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Cours mis à jour avec succès", 
                CoursSerializer(obj).data, 
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation", 
            errors=serializer.errors, 
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        
        if not can_create_in_context(request.user, obj):
            return api_error(
                "Vous ne pouvez pas modifier ce cours",
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = CoursSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Cours mis à jour partiellement avec succès", 
                CoursSerializer(obj).data, 
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation", 
            errors=serializer.errors, 
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        
        if not can_create_in_context(request.user, obj):
            return api_error(
                "Vous ne pouvez pas supprimer ce cours",
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        obj.delete()
        return api_success(
            "Cours supprimé avec succès", 
            data=None, 
            http_status=status.HTTP_204_NO_CONTENT
        )
class CoursModulesAPIView(APIView):
    """Liste les modules d'un cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, cours_id):
        try:
            # Vérifier l'accès au cours
            cours = get_filtered_object(Cours, cours_id, request, 'Cours')
            
            # Récupérer les modules
            modules = Module.objects.filter(cours=cours).order_by('id')
            serializer = ModuleSerializer(modules, many=True)
            
            return api_success(
                f"Modules du cours '{cours}' récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des modules",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# MODULES
# ============================================================================

class ModuleListCreateAPIView(APIView):
    """Liste et création de modules"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            qs = Module.objects.select_related(
                'cours', 'institution', 'annee_scolaire'
            ).all()
            
            # Filtrage par rôle (Formateur voit uniquement modules de SES cours)
            qs = filter_queryset_by_role(qs, request, 'Module')
            
            qs = qs.order_by('-id')
            serializer = ModuleSerializer(qs, many=True)
            
            return api_success(
                "Liste des modules récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des modules",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        serializer = ModuleSerializer(data=request.data)
        if serializer.is_valid():
            # Vérifier que l'utilisateur peut créer dans ce cours
            cours_id = request.data.get('cours')
            if cours_id:
                try:
                    cours = get_filtered_object(Cours, cours_id, request, 'Cours')
                    if not can_create_in_context(request.user, cours):
                        return api_error(
                            "Vous ne pouvez pas créer de module dans ce cours",
                            http_status=status.HTTP_403_FORBIDDEN
                        )
                except:
                    return api_error(
                        "Cours non trouvé ou accès refusé",
                        http_status=status.HTTP_404_NOT_FOUND
                    )
            
            obj = serializer.save()
            return api_success(
                "Module créé avec succès",
                ModuleSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class ModuleDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un module"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_object(Module, pk, request, 'Module')

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success(
            "Module trouvé avec succès",
            ModuleSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        
        if not can_create_in_context(request.user, obj):
            return api_error(
                "Vous ne pouvez pas modifier ce module",
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ModuleSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Module mis à jour avec succès",
                ModuleSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        
        if not can_create_in_context(request.user, obj):
            return api_error(
                "Vous ne pouvez pas modifier ce module",
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ModuleSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Module mis à jour partiellement avec succès",
                ModuleSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        
        if not can_create_in_context(request.user, obj):
            return api_error(
                "Vous ne pouvez pas supprimer ce module",
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        obj.delete()
        return api_success(
            "Module supprimé avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )


class ModuleSequencesAPIView(APIView):
    """Liste les séquences d'un module"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, module_id):
        try:
            module = get_filtered_object(Module, module_id, request, 'Module')
            sequences = Sequence.objects.filter(module=module).order_by('id')
            serializer = SequenceSerializer(sequences, many=True)
            
            return api_success(
                f"Séquences du module '{module}' récupérées avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des séquences",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ============================================================================
# SÉQUENCES
# ============================================================================

class SequenceListCreateAPIView(APIView):
    """Liste et création de séquences"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            qs = Sequence.objects.select_related(
                'module', 'institution', 'annee_scolaire'
            ).all()
            
            # Filtrage par rôle (Formateur voit uniquement séquences de SES cours)
            qs = filter_queryset_by_role(qs, request, 'Sequence')
            
            qs = qs.order_by('-id')
            serializer = SequenceSerializer(qs, many=True)
            
            return api_success(
                "Liste des séquences récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des séquences",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        serializer = SequenceSerializer(data=request.data)
        if serializer.is_valid():
            # Vérifier accès au module parent
            module_id = request.data.get('module')
            if module_id:
                try:
                    module = get_filtered_object(Module, module_id, request, 'Module')
                    if not can_create_in_context(request.user, module):
                        return api_error(
                            "Vous ne pouvez pas créer de séquence dans ce module",
                            http_status=status.HTTP_403_FORBIDDEN
                        )
                except:
                    return api_error(
                        "Module non trouvé ou accès refusé",
                        http_status=status.HTTP_404_NOT_FOUND
                    )
            
            obj = serializer.save()
            return api_success(
                "Séquence créée avec succès",
                SequenceSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class SequenceDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une séquence"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_object(Sequence, pk, request, 'Sequence')

    def _check_edit_permission(self, request, sequence):
        # ✅ IMPORTANT : vérif sur le module parent (comme dans POST)
        module = sequence.module
        if not can_create_in_context(request.user, module):
            return api_error(
                "Vous ne pouvez pas modifier/supprimer cette séquence",
                http_status=status.HTTP_403_FORBIDDEN
            )
        return None

    def get(self, request, pk):
        try:
            sequence = self.get_object(pk, request)
            serializer = SequenceDetailSerializer(sequence)
            return api_success("Séquence trouvée avec succès", serializer.data, status.HTTP_200_OK)

        except Http404:
            return api_error("Séquence introuvable", http_status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return api_error(
                "Erreur lors de la récupération de la séquence",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        try:
            sequence = self.get_object(pk, request)

            perm_error = self._check_edit_permission(request, sequence)
            if perm_error:
                return perm_error

            # ✅ Pour éviter les échecs si le frontend envoie partiel
            serializer = SequenceSerializer(sequence, data=request.data, partial=True)

            if serializer.is_valid():
                sequence = serializer.save()
                return api_success("Séquence mise à jour avec succès", SequenceSerializer(sequence).data, status.HTTP_200_OK)

            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

        except Http404:
            return api_error("Séquence introuvable", http_status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour de la séquence",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, pk):
        try:
            sequence = self.get_object(pk, request)

            perm_error = self._check_edit_permission(request, sequence)
            if perm_error:
                return perm_error

            serializer = SequenceSerializer(sequence, data=request.data, partial=True)
            if serializer.is_valid():
                sequence = serializer.save()
                return api_success(
                    "Séquence mise à jour partiellement avec succès",
                    SequenceSerializer(sequence).data,
                    status.HTTP_200_OK
                )

            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

        except Http404:
            return api_error("Séquence introuvable", http_status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour partielle de la séquence",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, pk):
        try:
            sequence = self.get_object(pk, request)

            perm_error = self._check_edit_permission(request, sequence)
            if perm_error:
                return perm_error

            titre = sequence.titre
            sequence.delete()

            return api_success(
                f"Séquence '{titre}' supprimée avec succès",
                data=None,
                http_status=status.HTTP_204_NO_CONTENT
            )

        except Http404:
            return api_error("Séquence introuvable", http_status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return api_error(
                "Erreur lors de la suppression de la séquence",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SequenceBlocsAPIView(APIView):
    """Liste les blocs de contenu d'une séquence"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, sequence_id):
        """Récupère les blocs de contenu d'une séquence"""
        try:
            context = get_user_context(request)
            sequence_qs = Sequence.objects.all()
            if context.get('institution_id'):
                sequence_qs = sequence_qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                sequence_qs = sequence_qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            sequence = get_object_or_404(sequence_qs, pk=sequence_id)
            blocs = BlocContenu.objects.filter(sequence=sequence).order_by('ordre')
            serializer = BlocContenuSerializer(blocs, many=True)
            return api_success(
                f"Blocs de contenu de la séquence '{sequence}' récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des blocs",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SequenceRessourcesAPIView(APIView):
    """Liste les ressources d'une séquence"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, sequence_id):
        """Récupère les ressources d'une séquence"""
        try:
            context = get_user_context(request)
            sequence_qs = Sequence.objects.all()
            if context.get('institution_id'):
                sequence_qs = sequence_qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                sequence_qs = sequence_qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            sequence = get_object_or_404(sequence_qs, pk=sequence_id)
            ressources = RessourceSequence.objects.filter(sequence=sequence).order_by('ordre')
            serializer = RessourceSequenceSerializer(ressources, many=True)
            return api_success(
                f"Ressources de la séquence '{sequence}' récupérées avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des ressources",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# BLOCS DE CONTENU
# ============================================================================

class BlocContenuListCreateAPIView(APIView):
    """Liste et création de blocs de contenu"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère les blocs de contenu filtrés"""
        try:
            context = get_user_context(request)
            blocs = BlocContenu.objects.select_related('sequence').all()
            
            # Filtrer par séquence si fourni
            sequence_id = request.query_params.get('sequence')
            if sequence_id:
                blocs = blocs.filter(sequence_id=sequence_id)
            
            # Filtrer par contexte via la séquence
            if context.get('institution_id'):
                blocs = blocs.filter(sequence__institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                blocs = blocs.filter(sequence__annee_scolaire_id=context['annee_scolaire_id'])
            
            blocs = blocs.order_by('sequence', 'ordre')
            serializer = BlocContenuSerializer(blocs, many=True)
            
            return api_success(
                "Liste des blocs de contenu récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des blocs",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée un nouveau bloc de contenu"""
        serializer = BlocContenuCreateSerializer(data=request.data)
        if serializer.is_valid():
            bloc = serializer.save()
            return api_success(
                "Bloc de contenu créé avec succès",
                BlocContenuSerializer(bloc).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class BlocContenuDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un bloc"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère un bloc par son ID avec filtrage contexte"""
        context = get_user_context(request)
        qs = BlocContenu.objects.select_related('sequence')
        
        if context.get('institution_id'):
            qs = qs.filter(sequence__institution_id=context['institution_id'])
        if context.get('annee_scolaire_id'):
            qs = qs.filter(sequence__annee_scolaire_id=context['annee_scolaire_id'])
        
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        """Récupère les détails d'un bloc"""
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc)
            return api_success(
                "Bloc de contenu trouvé avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération du bloc",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        """Met à jour complètement un bloc"""
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc, data=request.data)
            if serializer.is_valid():
                bloc = serializer.save()
                return api_success(
                    "Bloc de contenu mis à jour avec succès",
                    BlocContenuSerializer(bloc).data,
                    status.HTTP_200_OK
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, pk):
        """Met à jour partiellement un bloc"""
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc, data=request.data, partial=True)
            if serializer.is_valid():
                bloc = serializer.save()
                return api_success(
                    "Bloc de contenu mis à jour partiellement avec succès",
                    BlocContenuSerializer(bloc).data,
                    status.HTTP_200_OK
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, pk):
        """Supprime un bloc"""
        try:
            bloc = self.get_object(pk, request)
            bloc.delete()
            return api_success(
                "Bloc de contenu supprimé avec succès",
                None,
                status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la suppression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# RESSOURCES / PIÈCES JOINTES
# ============================================================================

class RessourceSequenceListCreateAPIView(APIView):
    """Liste et ajout de ressources/pièces jointes"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère les ressources filtrées"""
        try:
            context = get_user_context(request)
            ressources = RessourceSequence.objects.select_related(
                'sequence', 'ajoute_par'
            ).all()
            
            # Filtrer par séquence si fourni
            sequence_id = request.query_params.get('sequence')
            if sequence_id:
                ressources = ressources.filter(sequence_id=sequence_id)
            
            # Filtrer par type si fourni
            type_ressource = request.query_params.get('type')
            if type_ressource:
                ressources = ressources.filter(type_ressource=type_ressource)
            
            # Filtrer par contexte via la séquence
            if context.get('institution_id'):
                ressources = ressources.filter(sequence__institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                ressources = ressources.filter(sequence__annee_scolaire_id=context['annee_scolaire_id'])
            
            ressources = ressources.order_by('sequence', 'ordre')
            serializer = RessourceSequenceSerializer(ressources, many=True)
            
            return api_success(
                "Liste des ressources récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des ressources",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée une nouvelle ressource"""
        serializer = RessourceSequenceCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Ajouter l'utilisateur qui ajoute la ressource
            ressource = serializer.save(ajoute_par=request.user if hasattr(request.user, 'formateur') else None)
            return api_success(
                "Ressource créée avec succès",
                RessourceSequenceSerializer(ressource).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class RessourceSequenceDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une ressource"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère une ressource par son ID avec filtrage contexte"""
        context = get_user_context(request)
        qs = RessourceSequence.objects.select_related('sequence', 'ajoute_par')
        
        if context.get('institution_id'):
            qs = qs.filter(sequence__institution_id=context['institution_id'])
        if context.get('annee_scolaire_id'):
            qs = qs.filter(sequence__annee_scolaire_id=context['annee_scolaire_id'])
        
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        """Récupère les détails d'une ressource"""
        try:
            ressource = self.get_object(pk, request)
            serializer = RessourceSequenceSerializer(ressource)
            return api_success(
                "Ressource trouvée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération de la ressource",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        """Met à jour complètement une ressource"""
        try:
            ressource = self.get_object(pk, request)
            serializer = RessourceSequenceSerializer(ressource, data=request.data)
            if serializer.is_valid():
                ressource = serializer.save()
                return api_success(
                    "Ressource mise à jour avec succès",
                    RessourceSequenceSerializer(ressource).data,
                    status.HTTP_200_OK
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, pk):
        """Met à jour partiellement une ressource"""
        try:
            ressource = self.get_object(pk, request)
            serializer = RessourceSequenceSerializer(ressource, data=request.data, partial=True)
            if serializer.is_valid():
                ressource = serializer.save()
                return api_success(
                    "Ressource mise à jour partiellement avec succès",
                    RessourceSequenceSerializer(ressource).data,
                    status.HTTP_200_OK
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, pk):
        """Supprime une ressource"""
        try:
            ressource = self.get_object(pk, request)
            ressource.delete()
            return api_success(
                "Ressource supprimée avec succès",
                None,
                status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la suppression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RessourceTelechargementAPIView(APIView):
    """Gère le téléchargement des ressources"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Télécharge une ressource"""
        try:
            context = get_user_context(request)
            qs = RessourceSequence.objects.all()
            
            # Filtrer par contexte
            if context.get('institution_id'):
                qs = qs.filter(sequence__institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                qs = qs.filter(sequence__annee_scolaire_id=context['annee_scolaire_id'])
            
            ressource = get_object_or_404(qs, pk=pk)
            
            # Vérifier si le téléchargement est autorisé
            if not ressource.est_telechargeable:
                return api_error(
                    "Le téléchargement de cette ressource n'est pas autorisé",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            # Incrémenter le compteur de téléchargements
            ressource.nombre_telechargements += 1
            ressource.save(update_fields=['nombre_telechargements'])
            
            # Retourner le fichier
            if ressource.fichier:
                response = FileResponse(ressource.fichier.open('rb'))
                response['Content-Disposition'] = f'attachment; filename="{ressource.fichier.name}"'
                return response
            else:
                return api_error(
                    "Fichier non trouvé",
                    http_status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            return api_error(
                "Erreur lors du téléchargement",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# INSCRIPTIONS COURS
# ============================================================================

class InscriptionCoursListCreateAPIView(APIView):
    """Liste et création d'inscriptions aux cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des inscriptions filtrées par contexte"""
        try:
            context = get_user_context(request)
            qs = InscriptionCours.objects.select_related(
                'apprenant', 'cours', 'institution', 'annee_scolaire'
            ).all()
            
            if context.get('institution_id'):
                qs = qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            qs = qs.order_by('-date_inscription')
            serializer = InscriptionCoursSerializer(qs, many=True)
            return api_success(
                "Liste des inscriptions récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des inscriptions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée une nouvelle inscription"""
        serializer = InscriptionCoursSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Inscription créée avec succès",
                InscriptionCoursSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class InscriptionCoursDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une inscription"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère une inscription par son ID avec filtrage contexte"""
        context = get_user_context(request)
        qs = InscriptionCours.objects.select_related(
            'apprenant', 'cours', 'institution', 'annee_scolaire'
        )
        
        if context.get('institution_id'):
            qs = qs.filter(institution_id=context['institution_id'])
        if context.get('annee_scolaire_id'):
            qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
        
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success(
            "Inscription trouvée avec succès",
            InscriptionCoursSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = InscriptionCoursSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Inscription mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = InscriptionCoursSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Inscription mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success(
            "Inscription supprimée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )


# ============================================================================
# SUIVIS
# ============================================================================

class SuiviListCreateAPIView(APIView):
    """Liste et création de suivis"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des suivis filtrés par contexte"""
        try:
            context = get_user_context(request)
            qs = Suivi.objects.select_related(
                'apprenant', 'cours', 'institution', 'annee_scolaire'
            ).all()
            
            if context.get('institution_id'):
                qs = qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            qs = qs.order_by('-date_debut')
            serializer = SuiviSerializer(qs, many=True)
            return api_success(
                "Liste des suivis récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des suivis",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée un nouveau suivi"""
        serializer = SuiviSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Suivi créé avec succès",
                SuiviSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class SuiviDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un suivi"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère un suivi par son ID avec filtrage contexte"""
        context = get_user_context(request)
        qs = Suivi.objects.select_related(
            'apprenant', 'cours', 'institution', 'annee_scolaire'
        )
        
        if context.get('institution_id'):
            qs = qs.filter(institution_id=context['institution_id'])
        if context.get('annee_scolaire_id'):
            qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
        
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success(
            "Suivi trouvé avec succès",
            SuiviSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SuiviSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Suivi mis à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SuiviSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Suivi mis à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success(
            "Suivi supprimé avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )


# ============================================================================
# SESSIONS
# ============================================================================

class SessionListCreateAPIView(APIView):
    """Liste et création de sessions"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des sessions filtrées par contexte"""
        try:
            context = get_user_context(request)
            qs = Session.objects.select_related(
                'formateur', 'cours', 'institution', 'annee_scolaire'
            ).all()
            
            if context.get('institution_id'):
                qs = qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            qs = qs.order_by('-date_debut')
            serializer = SessionSerializer(qs, many=True)
            return api_success(
                "Liste des sessions récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des sessions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée une nouvelle session"""
        serializer = SessionSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Session créée avec succès",
                SessionSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class SessionDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une session"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère une session par son ID avec filtrage contexte"""
        context = get_user_context(request)
        qs = Session.objects.select_related(
            'formateur', 'cours', 'institution', 'annee_scolaire'
        )
        
        if context.get('institution_id'):
            qs = qs.filter(institution_id=context['institution_id'])
        if context.get('annee_scolaire_id'):
            qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
        
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success(
            "Session trouvée avec succès",
            SessionSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SessionSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Session mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SessionSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Session mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success(
            "Session supprimée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )


class SessionParticipantsAPIView(APIView):
    """Liste les participants d'une session"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Récupère les participants d'une session"""
        try:
            context = get_user_context(request)
            session_qs = Session.objects.all()
            if context.get('institution_id'):
                session_qs = session_qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                session_qs = session_qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            session = get_object_or_404(session_qs, pk=pk)
            participations = Participation.objects.filter(session=session).select_related('apprenant')
            serializer = ParticipationSerializer(participations, many=True)
            return api_success(
                f"Participants de la session '{session}' récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des participants",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# PARTICIPATIONS
# ============================================================================

class ParticipationListCreateAPIView(APIView):
    """Liste et création de participations"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des participations filtrées par contexte"""
        try:
            context = get_user_context(request)
            qs = Participation.objects.select_related(
                'session', 'apprenant', 'institution', 'annee_scolaire'
            ).all()
            
            if context.get('institution_id'):
                qs = qs.filter(institution_id=context['institution_id'])
            if context.get('annee_scolaire_id'):
                qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
            
            qs = qs.order_by('-created_at')
            serializer = ParticipationSerializer(qs, many=True)
            return api_success(
                "Liste des participations récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des participations",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        """Crée une nouvelle participation"""
        serializer = ParticipationSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Participation créée avec succès",
                ParticipationSerializer(obj).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )


class ParticipationDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une participation"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère une participation par son ID avec filtrage contexte"""
        context = get_user_context(request)
        qs = Participation.objects.select_related(
            'session', 'apprenant', 'institution', 'annee_scolaire'
        )
        
        if context.get('institution_id'):
            qs = qs.filter(institution_id=context['institution_id'])
        if context.get('annee_scolaire_id'):
            qs = qs.filter(annee_scolaire_id=context['annee_scolaire_id'])
        
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success(
            "Participation trouvée avec succès",
            ParticipationSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = ParticipationSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Participation mise à jour avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = ParticipationSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success(
                "Participation mise à jour partiellement avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success(
            "Participation supprimée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )


# ============================================================================
# PROGRESSION - BLOCS
# ============================================================================

class BlocProgressListAPIView(APIView):
    """Liste les progressions sur les blocs de contenu"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            if hasattr(request.user, "apprenant"):
                qs = BlocProgress.objects.filter(apprenant=request.user.apprenant)
            else:
                apprenant_id = request.query_params.get("apprenant")
                qs = BlocProgress.objects.filter(apprenant_id=apprenant_id) if apprenant_id else BlocProgress.objects.all()

            qs = qs.select_related("apprenant", "bloc").order_by("-updated_at")
            return api_success("Liste des progressions de blocs récupérée avec succès", BlocProgressSerializer(qs, many=True).data)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={"detail": str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BlocProgressToggleAPIView(APIView):
    """Marque un bloc comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, bloc_id):
        """Toggle le statut de progression d'un bloc"""
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error(
                    "Erreur de validation",
                    errors=serializer.errors,
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            # Récupérer ou créer la progression
            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error(
                    "Utilisateur non autorisé",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            progress, created = BlocProgress.objects.get_or_create(
                apprenant=apprenant,
                bloc_id=bloc_id,
                defaults={'est_termine': False}
            )
            
            # Mettre à jour le statut
            progress.est_termine = serializer.validated_data['est_termine']
            if progress.est_termine:
                progress.completed_at = timezone.now()
            else:
                progress.completed_at = None
            progress.save()
            
            return api_success(
                "Progression mise à jour avec succès",
                BlocProgressSerializer(progress).data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour de la progression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# PROGRESSION - SÉQUENCES
# ============================================================================

class SequenceProgressListAPIView(APIView):
    """Liste les progressions sur les séquences"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des progressions de séquences"""
        try:
            apprenant_id = request.query_params.get('apprenant')
            if apprenant_id:
                qs = SequenceProgress.objects.filter(apprenant_id=apprenant_id)
            else:
                if hasattr(request.user, 'apprenant'):
                    qs = SequenceProgress.objects.filter(apprenant=request.user.apprenant)
                else:
                    qs = SequenceProgress.objects.all()
            
            qs = qs.select_related('apprenant', 'sequence').order_by('-updated_at')
            serializer = SequenceProgressSerializer(qs, many=True)
            return api_success(
                "Liste des progressions de séquences récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SequenceProgressToggleAPIView(APIView):
    """Marque une séquence comme terminée ou non terminée"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, sequence_id):
        """Toggle le statut de progression d'une séquence"""
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error(
                    "Erreur de validation",
                    errors=serializer.errors,
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error(
                    "Utilisateur non autorisé",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            progress, created = SequenceProgress.objects.get_or_create(
                apprenant=apprenant,
                sequence_id=sequence_id,
                defaults={'est_termine': False}
            )
            
            progress.est_termine = serializer.validated_data['est_termine']
            if progress.est_termine:
                progress.completed_at = timezone.now()
            else:
                progress.completed_at = None
            progress.save()
            
            return api_success(
                "Progression mise à jour avec succès",
                SequenceProgressSerializer(progress).data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour de la progression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# PROGRESSION - MODULES
# ============================================================================

class ModuleProgressListAPIView(APIView):
    """Liste les progressions sur les modules"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des progressions de modules"""
        try:
            apprenant_id = request.query_params.get('apprenant')
            if apprenant_id:
                qs = ModuleProgress.objects.filter(apprenant_id=apprenant_id)
            else:
                if hasattr(request.user, 'apprenant'):
                    qs = ModuleProgress.objects.filter(apprenant=request.user.apprenant)
                else:
                    qs = ModuleProgress.objects.all()
            
            qs = qs.select_related('apprenant', 'module').order_by('-updated_at')
            serializer = ModuleProgressSerializer(qs, many=True)
            return api_success(
                "Liste des progressions de modules récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ModuleProgressToggleAPIView(APIView):
    """Marque un module comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, module_id):
        """Toggle le statut de progression d'un module"""
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error(
                    "Erreur de validation",
                    errors=serializer.errors,
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error(
                    "Utilisateur non autorisé",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            progress, created = ModuleProgress.objects.get_or_create(
                apprenant=apprenant,
                module_id=module_id,
                defaults={'est_termine': False}
            )
            
            progress.est_termine = serializer.validated_data['est_termine']
            if progress.est_termine:
                progress.completed_at = timezone.now()
            else:
                progress.completed_at = None
            progress.save()
            
            return api_success(
                "Progression mise à jour avec succès",
                ModuleProgressSerializer(progress).data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour de la progression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# PROGRESSION - COURS
# ============================================================================

class CoursProgressListAPIView(APIView):
    """Liste les progressions sur les cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste des progressions de cours"""
        try:
            apprenant_id = request.query_params.get('apprenant')
            if apprenant_id:
                qs = CoursProgress.objects.filter(apprenant_id=apprenant_id)
            else:
                if hasattr(request.user, 'apprenant'):
                    qs = CoursProgress.objects.filter(apprenant=request.user.apprenant)
                else:
                    qs = CoursProgress.objects.all()
            
            qs = qs.select_related('apprenant', 'cours').order_by('-updated_at')
            serializer = CoursProgressSerializer(qs, many=True)
            return api_success(
                "Liste des progressions de cours récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des progressions",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CoursProgressToggleAPIView(APIView):
    """Marque un cours comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, cours_id):
        """Toggle le statut de progression d'un cours"""
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error(
                    "Erreur de validation",
                    errors=serializer.errors,
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error(
                    "Utilisateur non autorisé",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            progress, created = CoursProgress.objects.get_or_create(
                apprenant=apprenant,
                cours_id=cours_id,
                defaults={'est_termine': False}
            )
            
            progress.est_termine = serializer.validated_data['est_termine']
            if progress.est_termine:
                progress.completed_at = timezone.now()
            else:
                progress.completed_at = None
            progress.save()
            
            return api_success(
                "Progression mise à jour avec succès",
                CoursProgressSerializer(progress).data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour de la progression",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )