# courses/views.py

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import (
    Cours, 
    InscriptionCours, 
    Module, 
    Participation, 
    Sequence, 
    Session, 
    Suivi
)
from .serializers import (
    CoursSerializer, 
    InscriptionCoursSerializer, 
    ModuleSerializer, 
    ParticipationSerializer, 
    SequenceSerializer, 
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
    """Détails, mise à jour et suppression d'une séquence"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk):
        """Récupère une séquence par son ID"""
        return get_object_or_404(
            Sequence.objects.select_related('module'),
            pk=pk
        )

    def get(self, request, pk):
        """Récupère les détails d'une séquence"""
        obj = self.get_object(pk)
        return api_success(
            "Séquence trouvée avec succès",
            SequenceSerializer(obj).data,
            status.HTTP_200_OK
        )

    def put(self, request, pk):
        """Met à jour complètement une séquence"""
        obj = self.get_object(pk)
        serializer = SequenceSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Séquence mise à jour avec succès",
                SequenceSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        """Met à jour partiellement une séquence"""
        obj = self.get_object(pk)
        serializer = SequenceSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Séquence mise à jour partiellement avec succès",
                SequenceSerializer(obj).data,
                status.HTTP_200_OK
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        """Supprime une séquence"""
        obj = self.get_object(pk)
        obj.delete()
        return api_success(
            "Séquence supprimée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT
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