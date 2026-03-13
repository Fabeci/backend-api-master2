# courses/views.py
# ✅ CORRECTIONS :
# #1 BlocContenuListCreateAPIView — filtre institution/annee_scolaire conditionnel
# #2 SequenceBlocsAPIView — filtre conditionnel sur la séquence
# #3 SequenceRessourcesAPIView — filtre conditionnel sur la séquence
# #4 BlocContenuDetailAPIView — filtre conditionnel sur get_object
# #5 RessourceSequenceListCreateAPIView — filtre conditionnel
# #6 RessourceSequenceDetailAPIView — filtre conditionnel
# #7 RessourceTelechargementAPIView — filtre conditionnel
#
# RÈGLE APPLIQUÉE PARTOUT :
#   On n'applique filter(X=val) QUE si au moins un objet dans le QS courant
#   possède ce champ renseigné. Sinon on suppose que le backend a déjà filtré
#   par séquence/cours et on laisse passer.
#   Cela évite que les séquences/blocs sans institution_id soient silencieusement exclus.

import os
import uuid

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from django.http import FileResponse, Http404
from django.core.files.storage import default_storage
from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework.decorators import action
from academics.models import Inscription
from django.db.models import Sum
from rest_framework.parsers import MultiPartParser, FormParser

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


def _apply_context_filter(qs, context, field_institution='institution_id', field_annee='annee_scolaire_id'):
    """
    Applique les filtres institution/annee_scolaire de façon conditionnelle.
    Détecte automatiquement le bon champ selon le modèle du queryset.
    """
    if context.get('bypass'):
        return qs

    institution_id = context.get('institution_id')
    annee_id = context.get('annee_scolaire_id')

    if institution_id:
        # ✅ Vérifie que le champ institution_id existe directement sur le modèle
        model = qs.model
        field_names = [f.name for f in model._meta.get_fields()]

        if 'institution' in field_names or 'institution_id' in field_names:
            # Filtre conditionnel : seulement si au moins un objet a institution renseigné
            if qs.filter(institution_id__isnull=False).exists():
                qs = qs.filter(institution_id=institution_id)
        # Si le modèle n'a pas de champ institution direct, on laisse passer

    if annee_id:
        model = qs.model
        field_names = [f.name for f in model._meta.get_fields()]
        if 'annee_scolaire' in field_names or 'annee_scolaire_id' in field_names:
            if qs.filter(annee_scolaire_id__isnull=False).exists():
                qs = qs.filter(annee_scolaire_id=annee_id)

    return qs

def _apply_sequence_context_filter(qs, context):
    """
    ✅ Variante pour les QuerySets dont institution/annee_scolaire
    sont portés par la relation sequence (BlocContenu, RessourceSequence…).
    """
    if context.get('institution_id'):
        if qs.filter(sequence__institution_id__isnull=False).exists():
            qs = qs.filter(sequence__institution_id=context['institution_id'])

    if context.get('annee_scolaire_id'):
        if qs.filter(sequence__annee_scolaire_id__isnull=False).exists():
            qs = qs.filter(sequence__annee_scolaire_id=context['annee_scolaire_id'])

    return qs


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

            qs = filter_queryset_by_role(qs, request, 'Cours')
            qs = qs.order_by("-id")
            data = CoursSerializer(qs, many=True).data

            return api_success("Liste des cours récupérée avec succès", data, status.HTTP_200_OK)
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

            if not user.is_superuser:
                if 'institution' not in request.data and user.institution:
                    serializer.validated_data['institution'] = user.institution

                if 'annee_scolaire' not in request.data and user.annee_scolaire_active:
                    serializer.validated_data['annee_scolaire'] = user.annee_scolaire_active

                role_name = user.role.name if user.role else None
                if role_name == 'Formateur' and 'enseignant' not in request.data:
                    serializer.validated_data['enseignant'] = user

            obj = serializer.save()
            return api_success("Cours créé avec succès", CoursSerializer(obj).data, status.HTTP_201_CREATED)

        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class CoursDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_object(Cours, pk, request, 'Cours')

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Cours trouvé avec succès", CoursSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_create_in_context(request.user, obj):
            return api_error("Vous ne pouvez pas modifier ce cours", http_status=status.HTTP_403_FORBIDDEN)

        serializer = CoursSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Cours mis à jour avec succès", CoursSerializer(obj).data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_create_in_context(request.user, obj):
            return api_error("Vous ne pouvez pas modifier ce cours", http_status=status.HTTP_403_FORBIDDEN)

        serializer = CoursSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Cours mis à jour partiellement avec succès", CoursSerializer(obj).data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)

        if not can_create_in_context(request.user, obj):
            return api_error("Vous ne pouvez pas supprimer ce cours", http_status=status.HTTP_403_FORBIDDEN)

        obj.delete()
        return api_success("Cours supprimé avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)


class CoursModulesAPIView(APIView):
    """Liste les modules d'un cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, cours_id):
        try:
            cours = get_filtered_object(Cours, cours_id, request, 'Cours')
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
            qs = Module.objects.select_related('cours', 'institution', 'annee_scolaire').all()
            qs = filter_queryset_by_role(qs, request, 'Module')
            qs = qs.order_by('-id')
            serializer = ModuleSerializer(qs, many=True)

            return api_success("Liste des modules récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des modules",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        serializer = ModuleSerializer(data=request.data)
        if serializer.is_valid():
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
                    return api_error("Cours non trouvé ou accès refusé", http_status=status.HTTP_404_NOT_FOUND)

            obj = serializer.save()
            return api_success("Module créé avec succès", ModuleSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class ModuleDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un module"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_object(Module, pk, request, 'Module')

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Module trouvé avec succès", ModuleSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        if not can_create_in_context(request.user, obj):
            return api_error("Vous ne pouvez pas modifier ce module", http_status=status.HTTP_403_FORBIDDEN)

        serializer = ModuleSerializer(obj, data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Module mis à jour avec succès", ModuleSerializer(obj).data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        if not can_create_in_context(request.user, obj):
            return api_error("Vous ne pouvez pas modifier ce module", http_status=status.HTTP_403_FORBIDDEN)

        serializer = ModuleSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Module mis à jour partiellement avec succès", ModuleSerializer(obj).data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        if not can_create_in_context(request.user, obj):
            return api_error("Vous ne pouvez pas supprimer ce module", http_status=status.HTTP_403_FORBIDDEN)

        obj.delete()
        return api_success("Module supprimé avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)


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
            qs = Sequence.objects.select_related('module', 'institution', 'annee_scolaire').all()
            qs = filter_queryset_by_role(qs, request, 'Sequence')
            qs = qs.order_by('-id')
            serializer = SequenceSerializer(qs, many=True)

            return api_success("Liste des séquences récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des séquences",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        serializer = SequenceSerializer(data=request.data)
        if serializer.is_valid():
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
                    return api_error("Module non trouvé ou accès refusé", http_status=status.HTTP_404_NOT_FOUND)

            obj = serializer.save()
            return api_success("Séquence créée avec succès", SequenceSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class SequenceDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une séquence"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        return get_filtered_object(Sequence, pk, request, 'Sequence')

    def _check_edit_permission(self, request, sequence):
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

            # ✅ #2 FIX : filtre conditionnel sur la séquence
            sequence_qs = Sequence.objects.all()
            sequence_qs = _apply_context_filter(sequence_qs, context)
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

            # ✅ #3 FIX : filtre conditionnel sur la séquence
            sequence_qs = Sequence.objects.all()
            sequence_qs = _apply_context_filter(sequence_qs, context)
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
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Récupère les blocs de contenu filtrés — avec debug temporaire"""
        try:
            context = get_user_context(request)
            blocs = BlocContenu.objects.select_related('sequence').all()

            sequence_id = request.query_params.get('sequence')

            print(f"\n[BLOCS DEBUG] =============================")
            print(f"[BLOCS DEBUG] user={request.user} (pk={request.user.pk})")
            print(f"[BLOCS DEBUG] sequence_id={sequence_id}")
            print(f"[BLOCS DEBUG] context={context}")
            print(f"[BLOCS DEBUG] blocs total avant tout filtre: {blocs.count()}")

            if sequence_id:
                blocs = blocs.filter(sequence_id=sequence_id)

            print(f"[BLOCS DEBUG] après filter(sequence_id={sequence_id}): {blocs.count()}")

            has_institution = blocs.filter(sequence__institution_id__isnull=False).exists()
            has_annee = blocs.filter(sequence__annee_scolaire_id__isnull=False).exists()
            print(f"[BLOCS DEBUG] has_institution={has_institution}, has_annee={has_annee}")

            blocs = _apply_sequence_context_filter(blocs, context)

            print(f"[BLOCS DEBUG] après _apply_sequence_context_filter: {blocs.count()}")
            print(f"[BLOCS DEBUG] =============================\n")

            blocs = blocs.order_by('sequence', 'ordre')
            serializer = BlocContenuSerializer(blocs, many=True)

            return api_success("Liste des blocs de contenu récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            print(f"[BLOCS DEBUG] EXCEPTION: {e}")
            return api_error("Erreur lors de la récupération des blocs", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        serializer = BlocContenuCreateSerializer(data=request.data)
        if serializer.is_valid():
            bloc = serializer.save()
            return api_success("Bloc de contenu créé avec succès", BlocContenuSerializer(bloc).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class BlocContenuDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un bloc"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        """Récupère un bloc par son ID avec filtrage contexte conditionnel"""
        context = get_user_context(request)
        qs = BlocContenu.objects.select_related('sequence')

        # ✅ #4 FIX : filtre conditionnel
        qs = _apply_sequence_context_filter(qs, context)

        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc)
            return api_success("Bloc de contenu trouvé avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération du bloc",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc, data=request.data)
            if serializer.is_valid():
                bloc = serializer.save()
                return api_success("Bloc de contenu mis à jour avec succès", BlocContenuSerializer(bloc).data, status.HTTP_200_OK)
            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, pk):
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc, data=request.data, partial=True)
            if serializer.is_valid():
                bloc = serializer.save()
                return api_success("Bloc de contenu mis à jour partiellement avec succès", BlocContenuSerializer(bloc).data, status.HTTP_200_OK)
            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        try:
            bloc = self.get_object(pk, request)
            bloc.delete()
            return api_success("Bloc de contenu supprimé avec succès", None, status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return api_error("Erreur lors de la suppression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# UPLOAD FICHIERS BLOCS CONTENU
# ============================================================================

class BlocContenuUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    ALLOWED_EXTENSIONS = {
        'image':       ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'],
        'video':       ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv'],
        'audio':       ['.mp3', '.wav', '.ogg', '.aac', '.m4a', '.flac'],
        'pdf':         ['.pdf'],
        'word':        ['.doc', '.docx'],
        'excel':       ['.xls', '.xlsx'],
        'powerpoint':  ['.ppt', '.pptx'],
        'archive':     ['.zip', '.rar', '.7z', '.tar', '.gz'],
        'texte':       ['.txt', '.csv'],
    }

    MAX_SIZE = {
        'image':       10  * 1024 * 1024,
        'video':       500 * 1024 * 1024,
        'audio':       100 * 1024 * 1024,
        'pdf':         50  * 1024 * 1024,
        'word':        50  * 1024 * 1024,
        'excel':       50  * 1024 * 1024,
        'powerpoint':  100 * 1024 * 1024,
        'archive':     200 * 1024 * 1024,
        'texte':       10  * 1024 * 1024,
    }

    UPLOAD_SUBDIR = {
        'image':       'images',
        'video':       'videos',
        'audio':       'audios',
        'pdf':         'pdfs',
        'word':        'documents',
        'excel':       'documents',
        'powerpoint':  'documents',
        'archive':     'archives',
        'texte':       'documents',
    }

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        kind = request.data.get('kind', '').strip().lower()

        if not file_obj:
            return Response({'error': 'Aucun fichier fourni.'}, status=status.HTTP_400_BAD_REQUEST)

        if kind not in self.ALLOWED_EXTENSIONS:
            allowed = ', '.join(self.ALLOWED_EXTENSIONS.keys())
            return Response(
                {'error': f"Type invalide : '{kind}'. Valeurs autorisées : {allowed}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        _, ext = os.path.splitext(file_obj.name.lower())
        if ext not in self.ALLOWED_EXTENSIONS[kind]:
            allowed = ', '.join(self.ALLOWED_EXTENSIONS[kind])
            return Response(
                {'error': f"Extension '{ext}' non autorisée pour '{kind}'. Autorisées : {allowed}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if file_obj.size > self.MAX_SIZE[kind]:
            max_mb = self.MAX_SIZE[kind] // (1024 * 1024)
            return Response(
                {'error': f"Fichier trop volumineux. Maximum autorisé : {max_mb} Mo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        unique_name = f"{uuid.uuid4().hex}{ext}"
        subdir = self.UPLOAD_SUBDIR[kind]
        upload_path = f"blocs_contenu/{subdir}/{unique_name}"

        try:
            saved_path = default_storage.save(upload_path, ContentFile(file_obj.read()))
        except Exception as e:
            return Response(
                {'error': f"Erreur lors de la sauvegarde : {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            file_url = default_storage.url(saved_path)
            if file_url.startswith('/'):
                scheme = 'https' if request.is_secure() else 'http'
                file_url = f"{scheme}://{request.get_host()}{file_url}"
        except Exception:
            file_url = f"{request.scheme}://{request.get_host()}{settings.MEDIA_URL}{saved_path}"

        return Response({'url': file_url}, status=status.HTTP_201_CREATED)


# ============================================================================
# RESSOURCES / PIÈCES JOINTES
# ============================================================================

class RessourceSequenceListCreateAPIView(APIView):
    """Liste et ajout de ressources/pièces jointes"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            context = get_user_context(request)
            ressources = RessourceSequence.objects.select_related('sequence', 'ajoute_par').all()

            sequence_id = request.query_params.get('sequence')
            if sequence_id:
                ressources = ressources.filter(sequence_id=sequence_id)

            type_ressource = request.query_params.get('type')
            if type_ressource:
                ressources = ressources.filter(type_ressource=type_ressource)

            # ✅ #5 FIX : filtre conditionnel
            ressources = _apply_sequence_context_filter(ressources, context)

            ressources = ressources.order_by('sequence', 'ordre')
            serializer = RessourceSequenceSerializer(ressources, many=True)

            return api_success("Liste des ressources récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des ressources",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        serializer = RessourceSequenceCreateSerializer(data=request.data)
        if serializer.is_valid():
            ressource = serializer.save(ajoute_par=request.user if hasattr(request.user, 'formateur') else None)
            return api_success(
                "Ressource créée avec succès",
                RessourceSequenceSerializer(ressource).data,
                status.HTTP_201_CREATED
            )
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class RessourceSequenceDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une ressource"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = RessourceSequence.objects.select_related('sequence', 'ajoute_par')

        # ✅ #6 FIX : filtre conditionnel
        qs = _apply_sequence_context_filter(qs, context)

        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        try:
            ressource = self.get_object(pk, request)
            return api_success("Ressource trouvée avec succès", RessourceSequenceSerializer(ressource).data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération de la ressource", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        try:
            ressource = self.get_object(pk, request)
            serializer = RessourceSequenceSerializer(ressource, data=request.data)
            if serializer.is_valid():
                ressource = serializer.save()
                return api_success("Ressource mise à jour avec succès", RessourceSequenceSerializer(ressource).data, status.HTTP_200_OK)
            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, pk):
        try:
            ressource = self.get_object(pk, request)
            serializer = RessourceSequenceSerializer(ressource, data=request.data, partial=True)
            if serializer.is_valid():
                ressource = serializer.save()
                return api_success("Ressource mise à jour partiellement avec succès", RessourceSequenceSerializer(ressource).data, status.HTTP_200_OK)
            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        try:
            ressource = self.get_object(pk, request)
            ressource.delete()
            return api_success("Ressource supprimée avec succès", None, status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return api_error("Erreur lors de la suppression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RessourceTelechargementAPIView(APIView):
    """Gère le téléchargement des ressources"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            context = get_user_context(request)
            qs = RessourceSequence.objects.all()

            # ✅ #7 FIX : filtre conditionnel
            qs = _apply_sequence_context_filter(qs, context)

            ressource = get_object_or_404(qs, pk=pk)

            if not ressource.est_telechargeable:
                return api_error(
                    "Le téléchargement de cette ressource n'est pas autorisé",
                    http_status=status.HTTP_403_FORBIDDEN
                )

            ressource.nombre_telechargements += 1
            ressource.save(update_fields=['nombre_telechargements'])

            if ressource.fichier:
                response = FileResponse(ressource.fichier.open('rb'))
                response['Content-Disposition'] = f'attachment; filename="{ressource.fichier.name}"'
                return response
            else:
                return api_error("Fichier non trouvé", http_status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return api_error("Erreur lors du téléchargement", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# INSCRIPTIONS COURS
# ============================================================================

class InscriptionCoursListCreateAPIView(APIView):
    """Liste et création d'inscriptions aux cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        print("=== DEBUG InscriptionCoursListCreateAPIView ===")
        print("user:", request.user)
        print("user pk:", request.user.pk)
        print("user type:", type(request.user))
        print("role raw:", getattr(request.user, "role", None))
        try:
            role_name = getattr(getattr(request.user, "role", None), "name", None)
            print("role_name:", role_name)

            qs = InscriptionCours.objects.select_related(
                "apprenant", "cours", "institution", "annee_scolaire"
            ).all()

            print("count avant filtre:", qs.count())

            qs = filter_queryset_by_role(qs, request, "InscriptionCours")

            print("count après filtre:", qs.count())
            print("ids après filtre:", list(qs.values_list("id", flat=True)[:20]))

            qs = qs.order_by("-date_inscription")
            serializer = InscriptionCoursSerializer(qs, many=True, context={"request": request})
            return api_success(
                "Liste des inscriptions récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK,
            )

        except Exception as e:
            print("❌ DEBUG ERROR:", str(e))
            return api_error(
                "Erreur lors de la récupération des inscriptions",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        serializer = InscriptionCoursSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Inscription créée avec succès",
                InscriptionCoursSerializer(obj, context={"request": request}).data,
                status.HTTP_201_CREATED,
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST,
        )


class InscriptionCoursDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une inscription"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        try:
            return InscriptionCours.objects.select_related(
                'apprenant', 'cours', 'institution', 'annee_scolaire'
            ).get(pk=pk)
        except InscriptionCours.DoesNotExist:
            raise Http404(f"Inscription {pk} introuvable.")

    def get(self, request, pk):
        try:
            obj = self.get_object(pk, request)
            return api_success("Inscription trouvée avec succès", InscriptionCoursSerializer(obj).data, status.HTTP_200_OK)
        except Http404:
            return api_error("Inscription introuvable.", http_status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        try:
            obj = self.get_object(pk, request)
            serializer = InscriptionCoursSerializer(obj, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return api_success("Inscription mise à jour avec succès", serializer.data, status.HTTP_200_OK)
            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return api_error("Inscription introuvable.", http_status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        try:
            obj = self.get_object(pk, request)
            serializer = InscriptionCoursSerializer(obj, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return api_success("Inscription mise à jour partiellement avec succès", serializer.data, status.HTTP_200_OK)
            return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)
        except Http404:
            return api_error("Inscription introuvable.", http_status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            obj = self.get_object(pk, request)
            obj.delete()
            return api_success("Inscription supprimée avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)
        except Http404:
            return api_error("Inscription introuvable.", http_status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# SUIVIS
# ============================================================================

class SuiviListCreateAPIView(APIView):
    """Liste et création de suivis"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            context = get_user_context(request)
            qs = Suivi.objects.select_related('apprenant', 'cours', 'institution', 'annee_scolaire').all()
            qs = _apply_context_filter(qs, context)
            qs = qs.order_by('-date_debut')
            serializer = SuiviSerializer(qs, many=True)
            return api_success("Liste des suivis récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des suivis", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        serializer = SuiviSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Suivi créé avec succès", SuiviSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class SuiviDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un suivi"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = Suivi.objects.select_related('apprenant', 'cours', 'institution', 'annee_scolaire')
        qs = _apply_context_filter(qs, context)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Suivi trouvé avec succès", SuiviSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SuiviSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Suivi mis à jour avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SuiviSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Suivi mis à jour partiellement avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success("Suivi supprimé avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# SESSIONS
# ============================================================================

class SessionListCreateAPIView(APIView):
    """Liste et création de sessions"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            context = get_user_context(request)
            qs = Session.objects.select_related('formateur', 'cours', 'institution', 'annee_scolaire').all()
            qs = _apply_context_filter(qs, context)
            qs = qs.order_by('-date_debut')
            serializer = SessionSerializer(qs, many=True)
            return api_success("Liste des sessions récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des sessions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        serializer = SessionSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Session créée avec succès", SessionSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class SessionDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une session"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = Session.objects.select_related('formateur', 'cours', 'institution', 'annee_scolaire')
        qs = _apply_context_filter(qs, context)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Session trouvée avec succès", SessionSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SessionSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Session mise à jour avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = SessionSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Session mise à jour partiellement avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success("Session supprimée avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)


class SessionParticipantsAPIView(APIView):
    """Liste les participants d'une session"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            context = get_user_context(request)
            session_qs = Session.objects.all()
            session_qs = _apply_context_filter(session_qs, context)
            session = get_object_or_404(session_qs, pk=pk)
            participations = Participation.objects.filter(session=session).select_related('apprenant')
            serializer = ParticipationSerializer(participations, many=True)
            return api_success(
                f"Participants de la session '{session}' récupérés avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Exception as e:
            return api_error("Erreur lors de la récupération des participants", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PARTICIPATIONS
# ============================================================================

class ParticipationListCreateAPIView(APIView):
    """Liste et création de participations"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            context = get_user_context(request)
            qs = Participation.objects.select_related('session', 'apprenant', 'institution', 'annee_scolaire').all()
            qs = _apply_context_filter(qs, context)
            qs = qs.order_by('-created_at')
            serializer = ParticipationSerializer(qs, many=True)
            return api_success("Liste des participations récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des participations", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        serializer = ParticipationSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Participation créée avec succès", ParticipationSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class ParticipationDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une participation"""
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = Participation.objects.select_related('session', 'apprenant', 'institution', 'annee_scolaire')
        qs = _apply_context_filter(qs, context)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Participation trouvée avec succès", ParticipationSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = ParticipationSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Participation mise à jour avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        serializer = ParticipationSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Participation mise à jour partiellement avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        obj.delete()
        return api_success("Participation supprimée avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)


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
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error("Utilisateur non autorisé", http_status=status.HTTP_403_FORBIDDEN)

            progress, created = BlocProgress.objects.get_or_create(
                apprenant=apprenant,
                bloc_id=bloc_id,
                defaults={'est_termine': False}
            )

            progress.est_termine = serializer.validated_data['est_termine']
            if progress.est_termine:
                progress.completed_at = timezone.now()
            else:
                progress.completed_at = None
            progress.save()

            return api_success("Progression mise à jour avec succès", BlocProgressSerializer(progress).data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour de la progression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PROGRESSION - SÉQUENCES
# ============================================================================

class SequenceProgressListAPIView(APIView):
    """Liste les progressions sur les séquences"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
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
            return api_success("Liste des progressions de séquences récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SequenceProgressToggleAPIView(APIView):
    """Marque une séquence comme terminée ou non terminée"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, sequence_id):
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error("Utilisateur non autorisé", http_status=status.HTTP_403_FORBIDDEN)

            progress, created = SequenceProgress.objects.get_or_create(
                apprenant=apprenant,
                sequence_id=sequence_id,
                defaults={'est_termine': False}
            )

            progress.est_termine = serializer.validated_data['est_termine']
            progress.completed_at = timezone.now() if progress.est_termine else None
            progress.save()

            return api_success("Progression mise à jour avec succès", SequenceProgressSerializer(progress).data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour de la progression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PROGRESSION - MODULES
# ============================================================================

class ModuleProgressListAPIView(APIView):
    """Liste les progressions sur les modules"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
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
            return api_success("Liste des progressions de modules récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ModuleProgressToggleAPIView(APIView):
    """Marque un module comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, module_id):
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error("Utilisateur non autorisé", http_status=status.HTTP_403_FORBIDDEN)

            progress, created = ModuleProgress.objects.get_or_create(
                apprenant=apprenant,
                module_id=module_id,
                defaults={'est_termine': False}
            )

            progress.est_termine = serializer.validated_data['est_termine']
            progress.completed_at = timezone.now() if progress.est_termine else None
            progress.save()

            return api_success("Progression mise à jour avec succès", ModuleProgressSerializer(progress).data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour de la progression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PROGRESSION - COURS
# ============================================================================

class CoursProgressListAPIView(APIView):
    """Liste les progressions sur les cours"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
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
            return api_success("Liste des progressions de cours récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CoursProgressToggleAPIView(APIView):
    """Marque un cours comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, cours_id):
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

            apprenant = request.user.apprenant if hasattr(request.user, 'apprenant') else None
            if not apprenant:
                return api_error("Utilisateur non autorisé", http_status=status.HTTP_403_FORBIDDEN)

            progress, created = CoursProgress.objects.get_or_create(
                apprenant=apprenant,
                cours_id=cours_id,
                defaults={'est_termine': False}
            )

            progress.est_termine = serializer.validated_data['est_termine']
            progress.completed_at = timezone.now() if progress.est_termine else None
            progress.save()

            return api_success("Progression mise à jour avec succès", CoursProgressSerializer(progress).data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour de la progression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class CoursIndicateursAPIView(APIView):
    """
    GET /api/cours/<id>/indicateurs/?apprenant=<apprenant_id>
    Retourne les indicateurs du cours pour un apprenant donné,
    ou les indicateurs globaux (sessions) si apprenant absent.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            cours = get_filtered_object(Cours, pk, request, 'Cours')
        except Http404:
            return api_error("Cours introuvable", http_status=status.HTTP_404_NOT_FOUND)

        volume_horaire_heures  = cours.volume_horaire or 0
        # volume_horaire_heures  = round(volume_horaire_minutes / 60, 2) if volume_horaire_minutes else 0

        apprenant_id = request.query_params.get('apprenant')

        # ── Indicateurs globaux (pas d'apprenant) ─────────────────────────
        if not apprenant_id:
            return Response({
                'success': True,
                'data': {
                    'volume_horaire':   volume_horaire_heures,
                    'heures_realisees': getattr(cours, 'total_heures_realisees', 0) or 0,
                    'taux_execution':   getattr(cours, 'taux_execution', 0) or 0,
                    'progression_pct':  0,
                    'blocs_termines':   0,
                    'total_blocs':      0,
                    'source':           'sessions',
                }
            })

        apprenant_id = int(apprenant_id)

        # ── 1. Progression blocs ───────────────────────────────────────────
        total_blocs = BlocContenu.objects.filter(
            sequence__module__cours=cours,
            est_visible=True,
        ).count()

        blocs_termines = BlocProgress.objects.filter(
            apprenant_id=apprenant_id,
            bloc__sequence__module__cours=cours,
            est_termine=True,
        ).count()

        progression_pct = round(
            (blocs_termines / total_blocs * 100) if total_blocs > 0 else 0, 1
        )

        # ── 2. Heures réalisées ────────────────────────────────────────────
        heures_realisees = 0.0
        try:
            from analytics.models import BlocSession
            total_sec = BlocSession.objects.filter(
                apprenant_id=apprenant_id,
                bloc__sequence__module__cours=cours,
            ).aggregate(total=Sum('duree_secondes'))['total'] or 0
            heures_realisees = round(total_sec / 3600, 2)
        except ImportError:
            try:
                from analytics.models import BlocAnalyticsSummary
                total_sec = BlocAnalyticsSummary.objects.filter(
                    apprenant_id=apprenant_id,
                    bloc__sequence__module__cours=cours,
                ).aggregate(total=Sum('duree_totale_sec'))['total'] or 0
                heures_realisees = round(total_sec / 3600, 2)
            except ImportError:
                # Fallback : durée estimée des blocs terminés
                blocs_ids = BlocProgress.objects.filter(
                    apprenant_id=apprenant_id,
                    bloc__sequence__module__cours=cours,
                    est_termine=True,
                ).values_list('bloc_id', flat=True)
                total_minutes = BlocContenu.objects.filter(
                    id__in=blocs_ids
                ).aggregate(total=Sum('duree_estimee_minutes'))['total'] or 0
                heures_realisees = round(total_minutes / 60, 2)

        return Response({
            'success': True,
            'data': {
                'volume_horaire':   volume_horaire_heures,
                'heures_realisees': heures_realisees,
                'taux_execution':   progression_pct,   # % blocs terminés
                'progression_pct':  progression_pct,
                'blocs_termines':   blocs_termines,
                'total_blocs':      total_blocs,
                'source':           'apprenant',
            }
        })