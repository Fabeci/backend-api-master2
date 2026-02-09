# courses/views.py

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
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
# COURS
# ============================================================================

class CoursListCreateAPIView(APIView):
    """Liste et création de cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste de tous les cours"""
        try:
            qs = Cours.objects.select_related(
                "groupe", 
                "matiere", 
                "enseignant"
            ).all().order_by("-id")
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

    def get_object(self, pk):
        """Récupère un cours par son ID"""
        return get_object_or_404(
            Cours.objects.select_related("groupe", "matiere", "enseignant"),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'un cours"""
        obj = self.get_object(pk)
        return api_success(
            "Cours trouvé avec succès", 
            CoursSerializer(obj).data, 
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement un cours"""
        obj = self.get_object(pk)
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
        """Met à jour partiellement un cours"""
        obj = self.get_object(pk)
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
        """Supprime un cours"""
        obj = self.get_object(pk)
        obj.delete()
        return api_success(
            "Cours supprimé avec succès", 
            data=None, 
            http_status=status.HTTP_204_NO_CONTENT
        )


# ============================================================================
# SEQUENCES
# ============================================================================

class SequenceListCreateAPIView(APIView):
    """Liste et création de séquences"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste de toutes les séquences"""
        try:
            sequences = Sequence.objects.select_related('module').all().order_by('-id')
            serializer = SequenceSerializer(sequences, many=True)
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
        """Crée une nouvelle séquence"""
        serializer = SequenceSerializer(data=request.data)
        if serializer.is_valid():
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
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """
        Récupère une séquence par son ID avec optimisation des requêtes
        """
        return get_object_or_404(
            Sequence.objects
                .select_related('module', 'module__cours')
                .prefetch_related('blocs_contenu', 'ressources_sequences'),
            pk=pk
        )
    
    def get(self, request, pk):
        try:
            sequence = self.get_object(pk)
            serializer = SequenceDetailSerializer(sequence)
            return api_success(
                "Séquence trouvée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération de la séquence",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request, pk):
        try:
            sequence = self.get_object(pk)
            serializer = SequenceSerializer(sequence, data=request.data)
            
            if serializer.is_valid():
                sequence = serializer.save()
                return api_success(
                    "Séquence mise à jour avec succès",
                    SequenceSerializer(sequence).data,
                    status.HTTP_200_OK
                )
            
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour de la séquence",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def patch(self, request, pk):
        try:
            sequence = self.get_object(pk)
            serializer = SequenceSerializer(sequence, data=request.data, partial=True)
            
            if serializer.is_valid():
                sequence = serializer.save()
                return api_success(
                    "Séquence mise à jour partiellement avec succès",
                    SequenceSerializer(sequence).data,
                    status.HTTP_200_OK
                )
            
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour partielle de la séquence",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def delete(self, request, pk):
        try:
            sequence = self.get_object(pk)
            titre = sequence.titre
            sequence.delete()
            
            return api_success(
                f"Séquence '{titre}' supprimée avec succès",
                data=None,
                http_status=status.HTTP_204_NO_CONTENT
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la suppression de la séquence",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BlocContenuListCreateAPIView(APIView):
    """Liste et création de blocs de contenu"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère les blocs de contenu (filtrés par séquence)"""
        try:
            blocs = BlocContenu.objects.select_related('sequence').all()
            
            # Filtrer par séquence si fourni
            sequence_id = request.query_params.get('sequence')
            if sequence_id:
                blocs = blocs.filter(sequence_id=sequence_id)
            
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

    def get(self, request, pk):
        """Récupère les détails d'un bloc"""
        try:
            bloc = get_object_or_404(BlocContenu, pk=pk)
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
            bloc = get_object_or_404(BlocContenu, pk=pk)
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
            bloc = get_object_or_404(BlocContenu, pk=pk)
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
            bloc = get_object_or_404(BlocContenu, pk=pk)
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
# VUES RESSOURCES / PIÈCES JOINTES
# ============================================================================

class RessourceSequenceListCreateAPIView(APIView):
    """Liste et ajout de ressources/pièces jointes"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère les ressources (filtrées par séquence)"""
        try:
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
        """Ajoute une nouvelle ressource"""
        serializer = RessourceSequenceCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Associer l'utilisateur actuel
            ressource = serializer.save(ajoute_par=request.user)
            return api_success(
                "Ressource ajoutée avec succès",
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

    def get(self, request, pk):
        """Récupère les détails d'une ressource"""
        try:
            ressource = get_object_or_404(RessourceSequence, pk=pk)
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

    def patch(self, request, pk):
        """Met à jour une ressource"""
        try:
            ressource = get_object_or_404(RessourceSequence, pk=pk)
            serializer = RessourceSequenceSerializer(ressource, data=request.data, partial=True)
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

    def delete(self, request, pk):
        """Supprime une ressource"""
        try:
            ressource = get_object_or_404(RessourceSequence, pk=pk)
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
    """Télécharger une ressource (incrémente le compteur)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Télécharge une ressource et incrémente le compteur"""
        try:
            from django.http import FileResponse
            
            ressource = get_object_or_404(RessourceSequence, pk=pk)
            
            if not ressource.est_telechargeable:
                return api_error(
                    "Cette ressource n'est pas téléchargeable",
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            # Incrémenter le compteur
            ressource.incrementer_telechargements()
            
            # Retourner le fichier
            return FileResponse(
                ressource.fichier.open('rb'),
                as_attachment=True,
                filename=ressource.fichier.name
            )
        except Exception as e:
            return api_error(
                "Erreur lors du téléchargement",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# MODIFICATION DE SequenceDetailAPIView
# ============================================================================

class SequenceDetailAPIView(APIView):
    """Détails complets d'une séquence avec blocs et ressources"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        """Récupère les détails complets d'une séquence"""
        try:
            sequence = get_object_or_404(
                Sequence.objects.select_related('module')
                                .prefetch_related('blocs_contenu', 'ressources_sequences'),
                pk=pk
            )
            serializer = SequenceDetailSerializer(sequence)
            return api_success(
                "Séquence trouvée avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération de la séquence",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ... autres méthodes (put, patch, delete) restent identiques


# ============================================================================
# VUE POUR BLOCS D'UNE SÉQUENCE
# ============================================================================

class SequenceBlocsAPIView(APIView):
    """
    /sequences/<id_sequence>/blocs/
    - GET : liste des blocs d'une séquence
    - POST: créer un bloc dans cette séquence
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, sequence_id):
        """Liste les blocs d'une séquence"""
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            blocs = sequence.blocs_contenu.all().order_by('ordre')
            serializer = BlocContenuSerializer(blocs, many=True)
            return api_success(
                "Blocs de la séquence récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des blocs",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, sequence_id):
        """Crée un bloc dans cette séquence"""
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            
            payload = dict(request.data)
            payload['sequence'] = sequence.id
            
            serializer = BlocContenuCreateSerializer(data=payload)
            if serializer.is_valid():
                bloc = serializer.save()
                return api_success(
                    "Bloc créé dans la séquence avec succès",
                    BlocContenuSerializer(bloc).data,
                    status.HTTP_201_CREATED
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la création du bloc",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# VUE POUR RESSOURCES D'UNE SÉQUENCE
# ============================================================================

class SequenceRessourcesAPIView(APIView):
    """
    /sequences/<id_sequence>/ressources/
    - GET : liste des ressources d'une séquence
    - POST: ajouter une ressource à cette séquence
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, sequence_id):
        """Liste les ressources d'une séquence"""
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            ressources = sequence.ressources_sequences.all().order_by('ordre')
            serializer = RessourceSequenceSerializer(ressources, many=True)
            return api_success(
                "Ressources de la séquence récupérées avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des ressources",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request, sequence_id):
        """Ajoute une ressource à cette séquence"""
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            
            payload = dict(request.data)
            payload['sequence'] = sequence.id
            
            serializer = RessourceSequenceCreateSerializer(data=payload)
            if serializer.is_valid():
                ressource = serializer.save(ajoute_par=request.user)
                return api_success(
                    "Ressource ajoutée à la séquence avec succès",
                    RessourceSequenceSerializer(ressource).data,
                    status.HTTP_201_CREATED
                )
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return api_error(
                "Erreur lors de l'ajout de la ressource",
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
        """Récupère la liste de tous les modules"""
        try:
            modules = Module.objects.select_related('cours').all().order_by('-id')
            serializer = ModuleSerializer(modules, many=True)
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
        """Crée un nouveau module"""
        serializer = ModuleSerializer(data=request.data)
        if serializer.is_valid():
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

    def get_object(self, pk):
        """Récupère un module par son ID"""
        return get_object_or_404(
            Module.objects.select_related('cours'),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'un module"""
        obj = self.get_object(pk)
        return api_success(
            "Module trouvé avec succès",
            ModuleSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement un module"""
        obj = self.get_object(pk)
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
        """Met à jour partiellement un module"""
        obj = self.get_object(pk)
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
        """Supprime un module"""
        obj = self.get_object(pk)
        obj.delete()
        return api_success(
            "Module supprimé avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )
    

class SessionParticipantsAPIView(APIView):
    """
    Liste des participants (participations) d'une session.
    GET /api/sessions/<pk>/participants/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            session = get_object_or_404(
                Session.objects.select_related("cours", "formateur"),
                pk=pk
            )

            qs = (
                Participation.objects
                .select_related("session", "session__cours", "session__formateur", "apprenant")
                .filter(session=session)
                .order_by("-created_at")
            )

            data = {
                "session": {
                    "id": session.id,
                    "titre": session.titre,
                    "date_debut": session.date_debut,
                    "date_fin": session.date_fin,
                    "cours": session.cours_id,
                    "formateur": session.formateur_id,
                },
                "participants_count": qs.count(),
                "participants": ParticipationSerializer(qs, many=True).data,
            }

            return api_success(
                "Liste des participants récupérée avec succès",
                data,
                status.HTTP_200_OK
            )

        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des participants",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# INSCRIPTIONS COURS
# ============================================================================

class InscriptionCoursListCreateAPIView(APIView):
    """Liste et création d'inscriptions aux cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste de toutes les inscriptions"""
        try:
            inscriptions = InscriptionCours.objects.select_related(
                'apprenant', 
                'cours'
            ).all().order_by('-date_inscription')
            serializer = InscriptionCoursSerializer(inscriptions, many=True)
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

    def get_object(self, pk):
        """Récupère une inscription par son ID"""
        return get_object_or_404(
            InscriptionCours.objects.select_related('apprenant', 'cours'),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'une inscription"""
        obj = self.get_object(pk)
        return api_success(
            "Inscription trouvée avec succès",
            InscriptionCoursSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement une inscription"""
        obj = self.get_object(pk)
        serializer = InscriptionCoursSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Inscription mise à jour avec succès",
                InscriptionCoursSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        """Met à jour partiellement une inscription"""
        obj = self.get_object(pk)
        serializer = InscriptionCoursSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Inscription mise à jour partiellement avec succès",
                InscriptionCoursSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        """Supprime une inscription"""
        obj = self.get_object(pk)
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
        """Récupère la liste de tous les suivis"""
        try:
            suivis = Suivi.objects.select_related(
                'apprenant', 
                'cours'
            ).all().order_by('-date_debut')
            serializer = SuiviSerializer(suivis, many=True)
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

    def get_object(self, pk):
        """Récupère un suivi par son ID"""
        return get_object_or_404(
            Suivi.objects.select_related('apprenant', 'cours'),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'un suivi"""
        obj = self.get_object(pk)
        return api_success(
            "Suivi trouvé avec succès",
            SuiviSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement un suivi"""
        obj = self.get_object(pk)
        serializer = SuiviSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Suivi mis à jour avec succès",
                SuiviSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        """Met à jour partiellement un suivi"""
        obj = self.get_object(pk)
        serializer = SuiviSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Suivi mis à jour partiellement avec succès",
                SuiviSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        """Supprime un suivi"""
        obj = self.get_object(pk)
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
        """Récupère la liste de toutes les sessions"""
        try:
            sessions = Session.objects.select_related(
                'cours', 
                'formateur'
            ).all().order_by('-date_debut')
            serializer = SessionSerializer(sessions, many=True)
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

    def get_object(self, pk):
        """Récupère une session par son ID"""
        return get_object_or_404(
            Session.objects.select_related('cours', 'formateur'),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'une session"""
        obj = self.get_object(pk)
        return api_success(
            "Session trouvée avec succès",
            SessionSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement une session"""
        obj = self.get_object(pk)
        serializer = SessionSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Session mise à jour avec succès",
                SessionSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        """Met à jour partiellement une session"""
        obj = self.get_object(pk)
        serializer = SessionSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Session mise à jour partiellement avec succès",
                SessionSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        """Supprime une session"""
        obj = self.get_object(pk)
        obj.delete()
        return api_success(
            "Session supprimée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )


# ============================================================================
# PARTICIPATIONS
# ============================================================================

class ParticipationListCreateAPIView(APIView):
    """Liste et création de participations"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère la liste de toutes les participations"""
        try:
            participations = Participation.objects.select_related(
                'session', 
                'apprenant'
            ).all().order_by('-created_at')
            serializer = ParticipationSerializer(participations, many=True)
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

    def get_object(self, pk):
        """Récupère une participation par son ID"""
        return get_object_or_404(
            Participation.objects.select_related('session', 'apprenant'),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'une participation"""
        obj = self.get_object(pk)
        return api_success(
            "Participation trouvée avec succès",
            ParticipationSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement une participation"""
        obj = self.get_object(pk)
        serializer = ParticipationSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Participation mise à jour avec succès",
                ParticipationSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        """Met à jour partiellement une participation"""
        obj = self.get_object(pk)
        serializer = ParticipationSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Participation mise à jour partiellement avec succès",
                ParticipationSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        """Supprime une participation"""
        obj = self.get_object(pk)
        obj.delete()
        return api_success(
            "Participation supprimée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
        )
    

class CoursModulesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, cours_id):
        cours = get_object_or_404(Cours, pk=cours_id)
        qs = cours.modules.all().order_by("id")
        data = ModuleSerializer(qs, many=True).data
        return api_success("Modules du cours", data, status.HTTP_200_OK)

    def post(self, request, cours_id):
        cours = get_object_or_404(Cours, pk=cours_id)

        payload = dict(request.data)
        payload["cours"] = cours.id  # on impose le cours depuis l'URL

        serializer = ModuleSerializer(data=payload)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Module créé dans le cours", ModuleSerializer(obj).data, status.HTTP_201_CREATED)

        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class ModuleSequencesAPIView(APIView):
    """
    /modules/<id_module>/sequences/
    - GET : liste des séquences d'un module
    - POST: créer une séquence dans ce module (module forcé par l'URL)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, module_id):
        module = get_object_or_404(Module, pk=module_id)
        qs = module.sequences.all().order_by("id")
        data = SequenceSerializer(qs, many=True).data
        return api_success("Séquences du module", data, status.HTTP_200_OK)

    def post(self, request, module_id):
        module = get_object_or_404(Module, pk=module_id)

        payload = dict(request.data)
        payload["module"] = module.id  # on impose le module depuis l'URL

        serializer = SequenceSerializer(data=payload)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Séquence créée dans le module", SequenceSerializer(obj).data, status.HTTP_201_CREATED)

        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    

class SequenceContentAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, sequence_id: int):
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            contenu = getattr(sequence, "contenu", None)

            if not contenu:
                return api_error(
                    "Aucun contenu pour cette séquence.",
                    errors={"detail": "contenu introuvable"},
                    http_status=status.HTTP_404_NOT_FOUND,
                )

            data = SequenceContentSerializer(contenu).data
            return api_success(
                "Contenu de la séquence récupéré avec succès",
                data,
                status.HTTP_200_OK,
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération du contenu de la séquence",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request, sequence_id: int):
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)

            # Empêcher double contenu (OneToOne)
            if hasattr(sequence, "contenu"):
                return api_error(
                    "Le contenu existe déjà pour cette séquence. Utilisez PATCH pour le modifier.",
                    errors={"detail": "contenu déjà existant"},
                    http_status=status.HTTP_400_BAD_REQUEST,
                )

            payload = dict(request.data)
            payload["sequence"] = sequence.id

            serializer = SequenceContentSerializer(data=payload)
            if serializer.is_valid():
                obj = serializer.save()
                return api_success(
                    "Contenu créé avec succès",
                    SequenceContentSerializer(obj).data,
                    status.HTTP_201_CREATED,
                )

            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            return api_error(
                "Erreur lors de la création du contenu",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    def put(self, request, sequence_id: int):
        """Met à jour complètement le contenu d'une séquence"""
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            contenu = getattr(sequence, "contenu", None)

            if not contenu:
                return api_error(
                    "Aucun contenu à modifier. Créez-le d'abord avec POST.",
                    errors={"detail": "contenu introuvable"},
                    http_status=status.HTTP_404_NOT_FOUND,
                )

            serializer = SequenceContentSerializer(contenu, data=request.data)
            if serializer.is_valid():
                obj = serializer.save()
                return api_success(
                    "Contenu mis à jour avec succès",
                    SequenceContentSerializer(obj).data,
                    status.HTTP_200_OK,
                )

            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour du contenu",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, sequence_id: int):
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            contenu = getattr(sequence, "contenu", None)

            if not contenu:
                return api_error(
                    "Aucun contenu à modifier. Créez-le d'abord avec POST.",
                    errors={"detail": "contenu introuvable"},
                    http_status=status.HTTP_404_NOT_FOUND,
                )

            serializer = SequenceContentSerializer(contenu, data=request.data, partial=True)
            if serializer.is_valid():
                obj = serializer.save()
                return api_success(
                    "Contenu mis à jour avec succès",
                    SequenceContentSerializer(obj).data,
                    status.HTTP_200_OK,
                )

            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            return api_error(
                "Erreur lors de la mise à jour du contenu",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request, sequence_id: int):
        try:
            sequence = get_object_or_404(Sequence, pk=sequence_id)
            contenu = getattr(sequence, "contenu", None)

            if not contenu:
                return api_success(
                    "Aucun contenu à supprimer (déjà absent).",
                    data=None,
                    http_status=status.HTTP_204_NO_CONTENT,
                )

            contenu.delete()
            return api_success(
                "Contenu supprimé avec succès",
                data=None,
                http_status=status.HTTP_204_NO_CONTENT,
            )

        except Exception as e:
            return api_error(
                "Erreur lors de la suppression du contenu",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
class BlocProgressListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /courses/progress/blocs/?sequence=<id>
        """
        apprenant = get_apprenant_from_request(request)

        sequence_id = request.query_params.get("sequence")
        qs = BlocProgress.objects.filter(apprenant=apprenant)

        if sequence_id:
            qs = qs.filter(bloc__sequence_id=sequence_id)

        data = BlocProgressSerializer(qs.order_by("-updated_at"), many=True).data
        return api_success("Progression des blocs", data, status.HTTP_200_OK)


class BlocProgressToggleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, bloc_id: int):
        """
        PUT /courses/progress/blocs/<bloc_id>/
        body: { "est_termine": true/false }
        """
        apprenant = get_apprenant_from_request(request)
        bloc = get_object_or_404(BlocContenu, pk=bloc_id)

        # Vérifie inscription (même règle que clean() mais ici on évite de crash)
        cours = bloc.sequence.module.cours
        if not InscriptionCours.objects.filter(apprenant=apprenant, cours=cours).exists():
            return api_error(
                "L'apprenant n'est pas inscrit à ce cours.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        payload = ProgressToggleSerializer(data=request.data)
        if not payload.is_valid():
            return api_error("Erreur de validation", errors=payload.errors, http_status=status.HTTP_400_BAD_REQUEST)

        done = payload.validated_data["est_termine"]

        bp, _ = BlocProgress.objects.get_or_create(apprenant=apprenant, bloc=bloc)
        _mark_completed_fields(bp, done)

        # ✅ Cascade: sequence -> module -> cours
        sequence = bloc.sequence
        module = sequence.module
        cours = module.cours

        recompute_sequence_progress(apprenant, sequence)
        recompute_module_progress(apprenant, module)
        recompute_cours_progress(apprenant, cours)

        return api_success("Progression bloc mise à jour", BlocProgressSerializer(bp).data, status.HTTP_200_OK)

        
def get_apprenant_from_request(request):
    """
    Robust: selon ton auth, request.user peut être:
    - Apprenant directement
    - User avec attribut .apprenant
    """
    u = request.user
    if hasattr(u, "apprenant") and u.apprenant:
        return u.apprenant
    # fallback si Apprenant est ton user model
    return u


def _mark_completed_fields(instance, done: bool):
    if done:
        instance.est_termine = True
        if not instance.completed_at:
            instance.completed_at = timezone.now()
    else:
        instance.est_termine = False
        instance.completed_at = None
    instance.save(update_fields=["est_termine", "completed_at", "updated_at"])


def recompute_sequence_progress(apprenant, sequence):
    """
    Sequence terminée si tous les blocs visibles & obligatoires de la séquence sont terminés.
    """
    blocs = sequence.blocs_contenu.filter(est_visible=True, est_obligatoire=True)
    total = blocs.count()

    # Si pas de blocs obligatoires, on considère non terminée (tu peux changer à True si tu préfères)
    if total == 0:
        done = False
    else:
        done_count = BlocProgress.objects.filter(
            apprenant=apprenant,
            bloc__in=blocs,
            est_termine=True
        ).count()
        done = (done_count == total)

    sp, _ = SequenceProgress.objects.get_or_create(apprenant=apprenant, sequence=sequence)
    _mark_completed_fields(sp, done)
    return done


def recompute_module_progress(apprenant, module):
    """
    Module terminé si toutes ses séquences sont terminées.
    """
    seqs = module.sequences.all()
    total = seqs.count()
    if total == 0:
        done = False
    else:
        done_count = SequenceProgress.objects.filter(
            apprenant=apprenant,
            sequence__in=seqs,
            est_termine=True
        ).count()
        done = (done_count == total)

    mp, _ = ModuleProgress.objects.get_or_create(apprenant=apprenant, module=module)
    _mark_completed_fields(mp, done)
    return done


def recompute_cours_progress(apprenant, cours):
    """
    Cours terminé si tous ses modules sont terminés.
    """
    mods = cours.modules.all()
    total = mods.count()
    if total == 0:
        done = False
    else:
        done_count = ModuleProgress.objects.filter(
            apprenant=apprenant,
            module__in=mods,
            est_termine=True
        ).count()
        done = (done_count == total)

    cp, _ = CoursProgress.objects.get_or_create(apprenant=apprenant, cours=cours)
    _mark_completed_fields(cp, done)
    return done

class SequenceProgressListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /courses/progress/sequences/?module=<id>
        """
        apprenant = get_apprenant_from_request(request)

        module_id = request.query_params.get("module")
        qs = SequenceProgress.objects.filter(apprenant=apprenant)

        if module_id:
            qs = qs.filter(sequence__module_id=module_id)

        data = SequenceProgressSerializer(qs.order_by("-updated_at"), many=True).data
        return api_success("Progression des séquences", data, status.HTTP_200_OK)


class SequenceProgressToggleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, sequence_id: int):
        """
        PUT /courses/progress/sequences/<sequence_id>/
        body: { "est_termine": true/false }
        """
        apprenant = get_apprenant_from_request(request)
        sequence = get_object_or_404(Sequence, pk=sequence_id)

        cours = sequence.module.cours
        if not InscriptionCours.objects.filter(apprenant=apprenant, cours=cours).exists():
            return api_error("Non inscrit au cours.", http_status=status.HTTP_403_FORBIDDEN)

        payload = ProgressToggleSerializer(data=request.data)
        if not payload.is_valid():
            return api_error("Erreur de validation", errors=payload.errors, http_status=status.HTTP_400_BAD_REQUEST)

        done = payload.validated_data["est_termine"]

        sp, _ = SequenceProgress.objects.get_or_create(apprenant=apprenant, sequence=sequence)
        _mark_completed_fields(sp, done)

        # si on force une séquence terminée, on peut (optionnel) marquer tous ses blocs terminés
        # 👉 je le laisse désactivé pour éviter les surprises.

        # ✅ Cascade module -> cours
        recompute_module_progress(apprenant, sequence.module)
        recompute_cours_progress(apprenant, sequence.module.cours)

        return api_success("Progression séquence mise à jour", SequenceProgressSerializer(sp).data, status.HTTP_200_OK)


class ModuleProgressListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /courses/progress/modules/?cours=<id>
        """
        apprenant = get_apprenant_from_request(request)

        cours_id = request.query_params.get("cours")
        qs = ModuleProgress.objects.filter(apprenant=apprenant)

        if cours_id:
            qs = qs.filter(module__cours_id=cours_id)

        data = ModuleProgressSerializer(qs.order_by("-updated_at"), many=True).data
        return api_success("Progression des modules", data, status.HTTP_200_OK)


class ModuleProgressToggleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, module_id: int):
        """
        PUT /courses/progress/modules/<module_id>/
        body: { "est_termine": true/false }
        """
        apprenant = get_apprenant_from_request(request)
        module = get_object_or_404(Module, pk=module_id)

        cours = module.cours
        if not InscriptionCours.objects.filter(apprenant=apprenant, cours=cours).exists():
            return api_error("Non inscrit au cours.", http_status=status.HTTP_403_FORBIDDEN)

        payload = ProgressToggleSerializer(data=request.data)
        if not payload.is_valid():
            return api_error("Erreur de validation", errors=payload.errors, http_status=status.HTTP_400_BAD_REQUEST)

        done = payload.validated_data["est_termine"]

        mp, _ = ModuleProgress.objects.get_or_create(apprenant=apprenant, module=module)
        _mark_completed_fields(mp, done)

        # ✅ Cascade cours
        recompute_cours_progress(apprenant, cours)

        return api_success("Progression module mise à jour", ModuleProgressSerializer(mp).data, status.HTTP_200_OK)


class CoursProgressListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        GET /courses/progress/cours/?cours=<id>
        (retourne 0 ou 1 item)
        """
        apprenant = get_apprenant_from_request(request)
        cours_id = request.query_params.get("cours")

        qs = CoursProgress.objects.filter(apprenant=apprenant)
        if cours_id:
            qs = qs.filter(cours_id=cours_id)

        data = CoursProgressSerializer(qs.order_by("-updated_at"), many=True).data
        return api_success("Progression du cours", data, status.HTTP_200_OK)


class CoursProgressToggleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, cours_id: int):
        """
        PUT /courses/progress/cours/<cours_id>/
        body: { "est_termine": true/false }
        """
        apprenant = get_apprenant_from_request(request)
        cours = get_object_or_404(Cours, pk=cours_id)

        if not InscriptionCours.objects.filter(apprenant=apprenant, cours=cours).exists():
            return api_error("Non inscrit au cours.", http_status=status.HTTP_403_FORBIDDEN)

        payload = ProgressToggleSerializer(data=request.data)
        if not payload.is_valid():
            return api_error("Erreur de validation", errors=payload.errors, http_status=status.HTTP_400_BAD_REQUEST)

        done = payload.validated_data["est_termine"]

        cp, _ = CoursProgress.objects.get_or_create(apprenant=apprenant, cours=cours)
        _mark_completed_fields(cp, done)

        return api_success("Progression cours mise à jour", CoursProgressSerializer(cp).data, status.HTTP_200_OK)


    
