# courses/views.py
import logging
import os
import uuid

logger = logging.getLogger(__name__)


def _int_param(request, name):
    """Retourne (valeur_entière, None) ou (None, Response_erreur) pour un query param entier."""
    raw = request.query_params.get(name)
    if raw is None:
        return None, None
    try:
        return int(raw), None
    except (ValueError, TypeError):
        from users.views import api_error
        return None, api_error(
            f"Le paramètre '{name}' doit être un entier.",
            http_status=400,
        )

from django.utils import timezone
from django.shortcuts import get_object_or_404
from core.rbac import RBACPermission
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.core.files.storage import default_storage
from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework.decorators import action
from academics.models import Inscription
from django.db.models import Count, Q, Sum
from rest_framework.parsers import MultiPartParser, FormParser

from courses.utils import (INSCRIPTION_ACTIVE_STATUSES, can_create_in_context, can_manage_cours, filter_queryset_by_role,
                            get_filtered_object, get_user_context, is_supervision_admin)
from users.access_control import accessible_apprenants, resolve_apprenant
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


def _cours_ids_inscrits(user):
    """✅ Identifiants des cours où cet apprenant est inscrit."""
    try:
        return list(
            InscriptionCours.objects.filter(apprenant=user, statut__in=INSCRIPTION_ACTIVE_STATUSES)
            .values_list('cours_id', flat=True)
        )
    except Exception:
        return []


def _restreindre_eleve(qs, request, cours_lookup=None, apprenant_lookup=None):
    """✅ PÉRIMÈTRE : restreint un queryset à celui de l'apprenant / du parent.

    - Apprenant : seulement ses cours (`cours_lookup`) ou ses enregistrements
      (`apprenant_lookup`) — jamais ceux d'un autre ;
    - Parent : seulement ses enfants ;
    - autres rôles : inchangé (leur périmètre est déjà filtré en amont).
    """
    role = _role_name(request)
    if role == 'Apprenant':
        if cours_lookup:
            qs = qs.filter(**{f"{cours_lookup}__in": _cours_ids_inscrits(request.user)})
        if apprenant_lookup:
            qs = qs.filter(**{apprenant_lookup: request.user})
    elif role == 'Parent':
        try:
            from users.access_control import accessible_apprenants
            allowed = accessible_apprenants(request.user)
            if allowed is not None and apprenant_lookup:
                qs = qs.filter(**{f"{apprenant_lookup}__in": allowed})
        except Exception:
            pass
    return qs


def _encadrant_du_cours(user, cours) -> bool:
    """True si `user` encadre réellement ce cours (enseignant direct ou via un
    groupe de ce cours). Sert au contrôle de PÉRIMÈTRE sur les ressources."""
    if cours is None:
        return False
    try:
        from .utils import can_manage_cours
        return bool(can_manage_cours(user, cours))
    except Exception:
        return False


def _role_name(request):
    try:
        return (get_user_context(request) or {}).get("role_name")
    except Exception:
        return None

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        """Liste les cours selon le rôle"""
        try:
            qs = Cours.objects.select_related(
                "groupe", "matiere", "enseignant", "institution", "annee_scolaire", "departement"
            ).all()

            qs = filter_queryset_by_role(qs, request, 'Cours')

            # ✅ Anti-N+1 : compteurs annotés + sessions préchargées.
            qs = qs.annotate(
                nb_modules=Count("modules", distinct=True),
                nb_inscrits=Count(
                    "inscriptions",
                    filter=Q(inscriptions__statut__in=INSCRIPTION_ACTIVE_STATUSES),
                    distinct=True,
                ),
            ).prefetch_related("sessions").order_by("-id")
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
        user = request.user
        role_name = user.role.name if getattr(user, 'role', None) else None
        data = request.data
        if role_name == 'Formateur':
            # ✅ L'enseignant est TOUJOURS le formateur connecté. On l'injecte
            #    AVANT la validation : le champ requis est satisfait sans que le
            #    client puisse désigner un autre formateur (anti-usurpation).
            data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            data['enseignant'] = user.pk
        serializer = CoursSerializer(data=data)
        if serializer.is_valid():
            user = request.user

            # ✅ MONO-ÉTABLISSEMENT : forcer l'institution et l'année de référence
            from core.tenant import default_institution, default_annee_scolaire
            inst = default_institution()
            annee = default_annee_scolaire()
            if inst:
                serializer.validated_data['institution'] = inst
            if annee:
                serializer.validated_data['annee_scolaire'] = annee

            if not user.is_superuser:
                role_name = user.role.name if user.role else None
                if role_name == 'Formateur':
                    # Force toujours l'enseignant = formateur connecté (anti-usurpation)
                    formateur = getattr(user, 'formateur_profile', None) or getattr(user, 'formateur', None)
                    if formateur:
                        serializer.validated_data['enseignant'] = formateur

                        # ✅ AFFECTATION : un formateur ne crée QUE les cours qui
                        #    lui ont été confiés (Admin/Responsable).
                        from academics.models import AffectationEnseignement
                        groupe  = serializer.validated_data.get('groupe')
                        matiere = serializer.validated_data.get('matiere')
                        annee   = serializer.validated_data.get('annee_scolaire')
                        qs_aff = AffectationEnseignement.objects.filter(
                            formateur=formateur, groupe=groupe, matiere=matiere, est_actif=True,
                        )
                        if annee is not None:
                            qs_aff = qs_aff.filter(annee_scolaire=annee)
                        if not qs_aff.exists():
                            return api_error(
                                "Ce cours ne vous a pas été affecté. Demandez au responsable "
                                "de vous affecter ce groupe et cette matière.",
                                http_status=status.HTTP_403_FORBIDDEN,
                            )

            obj = serializer.save()
            return api_success("Cours créé avec succès", CoursSerializer(obj).data, status.HTTP_201_CREATED)

        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class CoursDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un cours"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        return get_filtered_object(Cours, pk, request, 'Cours')

    def get(self, request, pk):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, cours_id):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            cours = get_filtered_object(Cours, cours_id, request, 'Cours')
            if _cours_non_ouvert(request, cours):
                return api_error(
                    "Ce cours n'a pas encore commencé. Son contenu sera accessible à partir de sa date de début.",
                    http_status=status.HTTP_403_FORBIDDEN,
                )
            modules = Module.objects.filter(cours=cours).order_by('id')
            # ✅ Structure : on garde les modules non publiés/programmés (verrouillés)
            #    pour que l'apprenant voie le plan du cours.
            modules = filter_queryset_by_role(modules, request, 'Module', inclure_indisponibles=True)
            serializer = ModuleSerializer(modules, many=True)
            data = list(serializer.data)

            appr = _get_own_apprenant(request.user)
            if appr is not None:
                from .publication import module_disponible
                for item, mod in zip(data, modules):
                    dispo = module_disponible(mod)
                    item['disponible'] = dispo
                    if not dispo:
                        item['raison_indisponible'] = 'Bientôt disponible'

            return api_success(
                f"Modules du cours '{cours}' récupérés avec succès",
                data,
                status.HTTP_200_OK
            )
        except Http404:
            raise
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
                except Exception:
                    return api_error("Cours non trouvé ou accès refusé", http_status=status.HTTP_404_NOT_FOUND)

            obj = serializer.save()
            return api_success("Module créé avec succès", ModuleSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class ModuleDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un module"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, module_id):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            # ✅ Structure : le module non publié reste accessible en lecture pour
            #    afficher ses séquences verrouillées (contenu bloqué ailleurs).
            module_qs = filter_queryset_by_role(
                Module.objects.all(), request, 'Module', inclure_indisponibles=True
            )
            module = get_object_or_404(module_qs, pk=module_id)
            if _cours_non_ouvert(request, module.cours):
                return api_error(
                    "Ce cours n'a pas encore commencé. Son contenu sera accessible à partir de sa date de début.",
                    http_status=status.HTTP_403_FORBIDDEN,
                )
            sequences = Sequence.objects.filter(module=module).order_by('id')
            sequences = filter_queryset_by_role(sequences, request, 'Sequence', inclure_indisponibles=True)
            serializer = SequenceSerializer(sequences, many=True)
            data = list(serializer.data)

            appr = _get_own_apprenant(request.user)
            if appr is not None:
                from .publication import sequence_disponible
                for item, seq in zip(data, sequences):
                    dispo = sequence_disponible(seq)
                    item['disponible'] = dispo
                    if not dispo:
                        item['raison_indisponible'] = 'Bientôt disponible'

            return api_success(
                f"Séquences du module '{module}' récupérées avec succès",
                data,
                status.HTTP_200_OK
            )
        except Http404:
            raise
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
                except Exception:
                    return api_error("Module non trouvé ou accès refusé", http_status=status.HTTP_404_NOT_FOUND)

            obj = serializer.save()
            return api_success("Séquence créée avec succès", SequenceSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class SequenceDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une séquence"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, sequence_id):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            # ✅ Structure : on garde la séquence et ses blocs même non publiés
            #    (affichés verrouillés) — le CONTENU reste masqué plus bas.
            seq_qs = filter_queryset_by_role(
                Sequence.objects.all(), request, 'Sequence', inclure_indisponibles=True
            )
            sequence = get_object_or_404(seq_qs, pk=sequence_id)
            if _cours_non_ouvert(request, sequence.module.cours):
                return api_error(
                    "Ce cours n'a pas encore commencé.",
                    http_status=status.HTTP_403_FORBIDDEN,
                )

            blocs = BlocContenu.objects.filter(
                sequence=sequence
            ).order_by('ordre')
            blocs = filter_queryset_by_role(blocs, request, 'BlocContenu', inclure_indisponibles=True)

            blocs = list(blocs)
            data = list(BlocContenuSerializer(blocs, many=True).data)

            # ✅ SÉCURITÉ — pour un apprenant : masquer le contenu des blocs
            #    verrouillés ou non publiés (ils restent listés pour afficher le
            #    cadenas / « Bientôt disponible » côté frontend).
            appr = _get_own_apprenant(request.user)
            if appr is not None:
                from .publication import bloc_disponible
                from .parcours_engine import build_parcours
                SENSITIVE = (
                    'contenu_texte', 'contenu_html', 'contenu_markdown', 'code_source',
                    'video_url', 'audio_url', 'lien_externe',
                )
                dispo_par_id = {b.pk: bloc_disponible(b) for b in blocs}
                locked_ids = set()
                try:
                    parc = build_parcours(appr, sequence.module.cours)
                    locked_ids = {
                        b['bloc_id']
                        for m in parc['modules'] for s in m['sequences'] for b in s['blocs']
                        if b['verrouille']
                    }
                except Exception:
                    pass
                for item, bloc in zip(data, blocs):
                    dispo = dispo_par_id.get(bloc.pk, False)
                    item['disponible'] = dispo
                    verrou = (not dispo) or (item.get('id') in locked_ids)
                    if verrou:
                        item['verrouille'] = True
                        if not dispo:
                            item['raison_indisponible'] = 'Bientôt disponible'
                        for f in SENSITIVE:
                            if f in item:
                                item[f] = None

            return api_success(
                f"Blocs de contenu récupérés avec succès",
                data,
                status.HTTP_200_OK
            )
        except Http404:
            raise
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des blocs",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SequenceRessourcesAPIView(APIView):
    """Liste les ressources d'une séquence"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, sequence_id):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        """Récupère les ressources d'une séquence"""
        try:
            context = get_user_context(request)

            # ✅ #3 FIX : filtre conditionnel sur la séquence
            sequence_qs = Sequence.objects.all()
            sequence_qs = _apply_context_filter(sequence_qs, context)
            sequence_qs = filter_queryset_by_role(sequence_qs, request, 'Sequence')
            sequence = get_object_or_404(sequence_qs, pk=sequence_id)

            ressources = RessourceSequence.objects.filter(sequence=sequence).order_by('ordre')
            serializer = RessourceSequenceSerializer(ressources, many=True)
            return api_success(
                f"Ressources de la séquence '{sequence}' récupérées avec succès",
                serializer.data,
                status.HTTP_200_OK
            )
        except Http404:
            raise
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            qs = BlocContenu.objects.select_related('sequence').all()

            sequence_id, err = _int_param(request, 'sequence')
            if err:
                return err
            if sequence_id:
                qs = qs.filter(sequence_id=sequence_id)

            qs = filter_queryset_by_role(qs, request, 'BlocContenu')

            qs = qs.order_by('sequence', 'ordre')
            serializer = BlocContenuSerializer(qs, many=True)

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
        serializer = BlocContenuCreateSerializer(data=request.data)
        if serializer.is_valid():
            # ✅ Propriété (permissive) : un Formateur ne crée un bloc que sur
            # un cours qu'il enseigne (lui ou l'un de ses groupes).
            sequence = serializer.validated_data.get('sequence')
            cours = getattr(getattr(sequence, 'module', None), 'cours', None)
            if cours is not None and not can_manage_cours(request.user, cours):
                return api_error("Action réservée au formateur du cours.",
                                 http_status=status.HTTP_403_FORBIDDEN)
            bloc = serializer.save()
            return api_success("Bloc de contenu créé avec succès", BlocContenuSerializer(bloc).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class BlocContenuDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un bloc"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        """Récupère un bloc par son ID avec filtrage contexte conditionnel"""
        context = get_user_context(request)
        qs = BlocContenu.objects.select_related('sequence__module__cours')

        # ✅ #4 FIX : filtre conditionnel
        qs = _apply_sequence_context_filter(qs, context)
        # ✅ PÉRIMÈTRE : l'apprenant n'accède qu'aux blocs de SES cours
        qs = _restreindre_eleve(qs, request, cours_lookup='sequence__module__cours_id')

        bloc = get_object_or_404(qs, pk=pk)

        # ✅ DISPONIBILITÉ (apprenant uniquement) : un bloc non publié /
        # programmé / parent indisponible n'est PAS accessible.
        appr = _get_own_apprenant(request.user)
        if appr is not None:
            from rest_framework.exceptions import PermissionDenied

            from .publication import bloc_disponible, cours_commence

            # Le cours lui-même doit avoir commencé.
            if not cours_commence(bloc.sequence.module.cours):
                raise PermissionDenied("Ce cours n'a pas encore commencé.")

            if not bloc_disponible(bloc):
                raise Http404("Bloc non disponible.")

        # ✅ SÉCURITÉ — un apprenant ne peut pas atteindre un bloc verrouillé
        if appr is not None:
            from .parcours_engine import is_bloc_unlocked_for
            ok, raison = is_bloc_unlocked_for(appr, bloc)
            if not ok:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(raison or 'Bloc verrouillé.')
        return bloc

    def get(self, request, pk):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            bloc = self.get_object(pk, request)
            serializer = BlocContenuSerializer(bloc)
            return api_success("Bloc de contenu trouvé avec succès", serializer.data, status.HTTP_200_OK)
        except (Http404, PermissionDenied):
            raise
        except Http404:
            raise
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération du bloc",
                errors={'detail': str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def put(self, request, pk):
        try:
            bloc = self.get_object(pk, request)
            cours = getattr(getattr(getattr(bloc, 'sequence', None), 'module', None), 'cours', None)
            if cours is not None and not can_manage_cours(request.user, cours):
                return api_error("Action réservée au formateur du cours.", http_status=status.HTTP_403_FORBIDDEN)
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
            cours = getattr(getattr(getattr(bloc, 'sequence', None), 'module', None), 'cours', None)
            if cours is not None and not can_manage_cours(request.user, cours):
                return api_error("Action réservée au formateur du cours.", http_status=status.HTTP_403_FORBIDDEN)
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
            cours = getattr(getattr(getattr(bloc, 'sequence', None), 'module', None), 'cours', None)
            if cours is not None and not can_manage_cours(request.user, cours):
                return api_error("Action réservée au formateur du cours.", http_status=status.HTTP_403_FORBIDDEN)
            bloc.delete()
            return api_success("Bloc de contenu supprimé avec succès", None, status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return api_error("Erreur lors de la suppression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BlocContenuEstimerAPIView(APIView):
    """POST /blocs-contenu/<pk>/estimer/ — recalcule la durée estimée d'un bloc."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        try:
            bloc = BlocContenuDetailAPIView().get_object(pk, request)
            ancienne = bloc.duree_estimee_minutes
            nouvelle = bloc.calculer_duree_estimee()
            bloc.duree_estimee_minutes = nouvelle
            bloc.save(update_fields=['duree_estimee_minutes'])
            return api_success(
                "Durée estimée recalculée.",
                {'id': bloc.pk, 'duree_estimee_minutes': nouvelle, 'ancienne': ancienne},
                status.HTTP_200_OK,
            )
        except (Http404, PermissionDenied):
            raise
        except Exception as e:
            return api_error("Erreur lors de l'estimation", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# UPLOAD FICHIERS BLOCS CONTENU
# ============================================================================

class BlocContenuUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    ALLOWED_EXTENSIONS = {
        # ✅ SÉCURITÉ : '.svg' retiré (XSS stocké via SVG).
        'image':       ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
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

        # ✅ SÉCURITÉ : vérifie que le contenu est une vraie image (pas un
        # fichier déguisé par son extension).
        if kind == 'image':
            try:
                from PIL import Image
                Image.open(file_obj).verify()
                file_obj.seek(0)
            except Exception:
                return Response(
                    {'error': "Image invalide ou corrompue."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        unique_name = f"{uuid.uuid4().hex}{ext}"
        subdir = self.UPLOAD_SUBDIR[kind]
        upload_path = f"blocs_contenu/{subdir}/{unique_name}"

        try:
            # ✅ On transmet le fichier (streamé sur disque) au lieu de le
            # charger entièrement en RAM via ContentFile(file_obj.read()).
            saved_path = default_storage.save(upload_path, file_obj)
        except Exception:
            logger.exception("Échec de sauvegarde d'un fichier de bloc de contenu")
            return Response(
                {'error': "Erreur lors de la sauvegarde du fichier."},
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            context = get_user_context(request)
            ressources = RessourceSequence.objects.select_related(
                'sequence', 'sequence__module', 'sequence__module__cours', 'ajoute_par'
            ).all()

            sequence_id, err = _int_param(request, 'sequence')
            if err:
                return err
            if sequence_id:
                ressources = ressources.filter(sequence_id=sequence_id)

            cours_id, err = _int_param(request, 'cours')
            if err:
                return err
            if cours_id:
                ressources = ressources.filter(sequence__module__cours_id=cours_id)

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
        # ✅ PÉRIMÈTRE vérifié AVANT toute validation : sinon un corps invalide
        #    renverrait 400 et court-circuiterait le contrôle de droits.
        if _role_name(request) == 'Formateur':
            seq_id = (request.data or {}).get('sequence')
            seq = Sequence.objects.filter(pk=seq_id).first() if seq_id else None
            cours = getattr(getattr(seq, 'module', None), 'cours', None)
            if not _encadrant_du_cours(request.user, cours):
                return api_error("Vous ne pouvez gérer que les ressources de vos cours.",
                                 http_status=status.HTTP_403_FORBIDDEN)
        serializer = RessourceSequenceCreateSerializer(data=request.data)
        if serializer.is_valid():
            # ✅ `ajoute_par` est une FK vers `Formateur` : on transmet l'ID
            #    (passer l'instance `User` provoquait un 500 ValueError).
            ajoute_par_id = request.user.pk if _role_name(request) == 'Formateur' else None
            ressource = serializer.save(ajoute_par_id=ajoute_par_id)
            return api_success(
                "Ressource créée avec succès",
                RessourceSequenceSerializer(ressource).data,
                status.HTTP_201_CREATED
            )
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class RessourceSequenceDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une ressource"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = RessourceSequence.objects.select_related('sequence', 'ajoute_par')

        # ✅ #6 FIX : filtre conditionnel
        qs = _apply_sequence_context_filter(qs, context)
        # ✅ PÉRIMÈTRE : l'apprenant n'accède qu'aux ressources de ses cours
        qs = _restreindre_eleve(qs, request, cours_lookup='sequence__module__cours_id')

        obj = get_object_or_404(qs, pk=pk)

        # ✅ PÉRIMÈTRE : un formateur n'agit que sur les ressources de ses cours
        if _role_name(request) == 'Formateur':
            cours = getattr(getattr(obj.sequence, 'module', None), 'cours', None)
            if not _encadrant_du_cours(request.user, cours):
                raise Http404("Ressource introuvable.")
        return obj

    def get(self, request, pk):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, pk):
        try:
            context = get_user_context(request)
            qs = RessourceSequence.objects.all()

            # ✅ #7 FIX : filtre conditionnel
            qs = _apply_sequence_context_filter(qs, context)
            # ✅ PÉRIMÈTRE : l'apprenant ne télécharge que les ressources de SES cours
            qs = _restreindre_eleve(qs, request, cours_lookup='sequence__module__cours_id')

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            qs = InscriptionCours.objects.select_related(
                "apprenant", "cours", "institution", "annee_scolaire"
            ).all()

            qs = filter_queryset_by_role(qs, request, "InscriptionCours")

            cours_id = request.query_params.get('cours')
            if cours_id:
                qs = qs.filter(cours_id=cours_id)

            apprenant_id = request.query_params.get('apprenant')
            if apprenant_id:
                qs = qs.filter(apprenant_id=apprenant_id)

            qs = qs.order_by("-date_inscription")
            serializer = InscriptionCoursSerializer(qs, many=True, context={"request": request})
            return api_success(
                "Liste des inscriptions récupérée avec succès",
                serializer.data,
                status.HTTP_200_OK,
            )

        except Exception as e:
            return api_error(
                "Erreur lors de la récupération des inscriptions",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def post(self, request):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        # ✅ RÈGLE MÉTIER : les inscriptions administratives relèvent de
        #    l'administration (Admin / SuperAdmin / Responsable) — PAS du formateur.
        if _role_name(request) not in ('Admin', 'Responsable'):
            return api_error("Seule l'administration peut gérer les inscriptions.",
                             http_status=status.HTTP_403_FORBIDDEN)
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    # ✅ RBAC : lecture (STAFF + Apprenant/Parent), écriture STAFF uniquement.
    rbac_resource = "inscriptions"

    def get_object(self, pk, request):
        # ✅ Scoping : l'objet doit être dans le périmètre du demandeur
        # (établissement / année / département / ses cours / soi-même). Sans
        # ce filtre, toute inscription était accessible par identifiant (IDOR).
        qs = InscriptionCours.objects.select_related(
            'apprenant', 'cours', 'institution', 'annee_scolaire'
        )
        qs = filter_queryset_by_role(qs, request, "InscriptionCours")
        try:
            return qs.get(pk=pk)
        except InscriptionCours.DoesNotExist:
            raise Http404(f"Inscription {pk} introuvable.")

    def get(self, request, pk):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
        try:
            obj = self.get_object(pk, request)
            return api_success("Inscription trouvée avec succès", InscriptionCoursSerializer(obj).data, status.HTTP_200_OK)
        except Http404:
            return api_error("Inscription introuvable.", http_status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
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
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
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
        if is_supervision_admin(request.user):
            return api_error("Accès non autorisé pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        try:
            context = get_user_context(request)
            qs = Suivi.objects.select_related('apprenant', 'cours', 'institution', 'annee_scolaire').all()
            qs = _apply_context_filter(qs, context)
            # ✅ PÉRIMÈTRE : un apprenant ne voit que SON suivi pédagogique
            qs = _restreindre_eleve(qs, request, apprenant_lookup='apprenant')

            cours_id = request.query_params.get('cours')
            if cours_id:
                qs = qs.filter(cours_id=cours_id)

            apprenant_id = request.query_params.get('apprenant')
            if apprenant_id:
                qs = qs.filter(apprenant_id=apprenant_id)

            qs = qs.order_by('-date_debut')
            serializer = SuiviSerializer(qs, many=True)
            return api_success("Liste des suivis récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des suivis", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        if not can_create_in_context(request.user, None, allow_admin=True):
            return api_error("Vous n'avez pas la permission de créer un suivi.", http_status=status.HTTP_403_FORBIDDEN)
        # ✅ PÉRIMÈTRE : le suivi ne peut viser qu'un apprenant accessible
        appr_id = (request.data or {}).get('apprenant')
        if appr_id not in (None, ''):
            from users.access_control import user_can_access_apprenant
            from users.models import Apprenant
            cible = Apprenant.objects.filter(pk=appr_id).first()
            if cible is None or not user_can_access_apprenant(request.user, cible):
                return api_error("Apprenant hors de votre périmètre.", http_status=status.HTTP_403_FORBIDDEN)
        serializer = SuiviSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Suivi créé avec succès", SuiviSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class SuiviDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'un suivi"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = Suivi.objects.select_related('apprenant', 'cours', 'institution', 'annee_scolaire')
        qs = _apply_context_filter(qs, context)
        # ✅ PÉRIMÈTRE : restreint aux apprenants accessibles
        try:
            from users.access_control import accessible_apprenants
            allowed = accessible_apprenants(request.user)
            if allowed is not None:
                qs = qs.filter(apprenant__in=allowed)
        except Exception:
            pass
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

class SessionCalendrierAPIView(APIView):
    """GET /sessions/calendrier/?debut=YYYY-MM-DD&fin=YYYY-MM-DD

    Calendrier global, filtré par le périmètre de rôle (établissement, cours,
    enfants pour un parent) via `filter_queryset_by_role`.
    """
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    rbac_resource = "sessions"

    def get(self, request):
        from datetime import timedelta

        from django.utils import timezone
        from django.utils.dateparse import parse_date

        debut = parse_date(request.query_params.get("debut") or "")
        fin = parse_date(request.query_params.get("fin") or "")
        today = timezone.localdate()

        if debut is None:
            debut = today.replace(day=1)
        if fin is None:
            if debut.month == 12:
                fin = debut.replace(year=debut.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                fin = debut.replace(month=debut.month + 1, day=1) - timedelta(days=1)

        if fin < debut:
            return api_error("La date de fin doit être postérieure au début.",
                             http_status=status.HTTP_400_BAD_REQUEST)
        if (fin - debut).days > 400:
            return api_error("Période trop large (max 400 jours).",
                             http_status=status.HTTP_400_BAD_REQUEST)

        try:
            qs = (
                Session.objects
                .select_related("formateur", "cours", "institution", "annee_scolaire")
                .filter(date_debut__date__gte=debut, date_debut__date__lte=fin)
            )
            qs = filter_queryset_by_role(qs, request, "Session").order_by("date_debut")
            return api_success(
                "Calendrier récupéré.",
                SessionSerializer(qs, many=True, context={"request": request}).data,
                status.HTTP_200_OK,
            )
        except Exception as e:
            return api_error(
                "Erreur lors de la récupération du calendrier",
                errors={"detail": str(e)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SessionListCreateAPIView(APIView):
    """Liste et création de sessions"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        try:
            context = get_user_context(request)
            qs = Session.objects.select_related('formateur', 'cours', 'institution', 'annee_scolaire').all()
            qs = _apply_context_filter(qs, context)
            # ✅ PÉRIMÈTRE : l'apprenant ne voit que les séances de ses cours
            qs = _restreindre_eleve(qs, request, cours_lookup='cours_id')

            cours_id = request.query_params.get('cours')
            if cours_id:
                qs = qs.filter(cours_id=cours_id)

            formateur_id = request.query_params.get('formateur')
            if formateur_id:
                qs = qs.filter(formateur_id=formateur_id)

            qs = qs.order_by('-date_debut')
            serializer = SessionSerializer(qs, many=True, context={'request': request})
            return api_success("Liste des sessions récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des sessions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        serializer = SessionSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # ✅ Propriété (permissive) : un Formateur ne crée une séance que
            # sur un cours qu'il enseigne (lui ou l'un de ses groupes).
            cours = serializer.validated_data.get('cours')
            if cours is not None and not can_manage_cours(request.user, cours):
                return api_error("Action réservée au formateur du cours.",
                                 http_status=status.HTTP_403_FORBIDDEN)
            generer = serializer.validated_data.pop('generer_lien_auto', False)
            obj = serializer.save()
            self._generer_lien_visio(obj, generer)
            return api_success("Session créée avec succès", SessionSerializer(obj, context={'request': request}).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _generer_lien_visio(session, generer):
        """Génère automatiquement le lien de visio à la création (optionnel)."""
        if not generer:
            return
        provider = getattr(session, 'visio_provider', 'aucune')
        try:
            if provider == 'google_meet':
                from courses import meet_service
                if meet_service.is_configured():
                    ev = meet_service.creer_pour_session(session)
                    session.lien_visio = ev.get('join_url', '')
                    session.meet_space_name = ev.get('meeting_code', '')
                    session.save(update_fields=['lien_visio', 'meet_space_name'])
            elif provider == 'jitsi':
                import secrets
                from django.conf import settings
                domain = getattr(settings, 'SESSION_JITSI_DOMAIN', 'meet.jit.si')
                session.lien_jitsi = f"https://{domain}/SOMAPRO-{session.id}-{secrets.token_urlsafe(6)}"
                session.save(update_fields=['lien_jitsi'])
            elif provider == 'teams':
                from courses import teams_service
                if teams_service.is_configured():
                    reunion = teams_service.creer_reunion(session.titre, session.date_debut, session.date_fin)
                    session.teams_join_url = reunion.get('join_url', '')
                    session.teams_meeting_id = reunion.get('id', '')
                    session.save(update_fields=['teams_join_url', 'teams_meeting_id'])
        except Exception:
            logger.exception("Échec génération du lien visio (session=%s, provider=%s)", session.id, provider)


class SessionDetailAPIView(APIView):
    """Détails, mise à jour et suppression d'une session"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get_object(self, pk, request):
        context = get_user_context(request)
        qs = Session.objects.select_related('formateur', 'cours', 'institution', 'annee_scolaire')
        qs = _apply_context_filter(qs, context)
        # ✅ PÉRIMÈTRE : l'apprenant n'accède qu'aux séances de ses cours
        qs = _restreindre_eleve(qs, request, cours_lookup='cours_id')
        return get_object_or_404(qs, pk=pk)

    def _check_owner(self, request, obj):
        """✅ Un Formateur ne modifie/supprime que les séances de SON cours."""
        if not can_manage_cours(request.user, getattr(obj, 'cours', None)):
            return api_error("Action réservée au formateur du cours.",
                             http_status=status.HTTP_403_FORBIDDEN)
        return None

    def get(self, request, pk):
        obj = self.get_object(pk, request)
        return api_success("Session trouvée avec succès", SessionSerializer(obj, context={'request': request}).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk, request)
        denied = self._check_owner(request, obj)
        if denied:
            return denied
        serializer = SessionSerializer(obj, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return api_success("Session mise à jour avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk, request)
        # Le changement de statut est autorisé au formateur du cours (idem ci-dessus).
        denied = self._check_owner(request, obj)
        if denied:
            return denied
        serializer = SessionSerializer(obj, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return api_success("Session mise à jour partiellement avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk, request)
        denied = self._check_owner(request, obj)
        if denied:
            return denied
        obj.delete()
        return api_success("Session supprimée avec succès", data=None, http_status=status.HTTP_204_NO_CONTENT)


class SessionParticipantsAPIView(APIView):
    """Liste les participants d'une session"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, pk):
        try:
            context = get_user_context(request)
            session_qs = Session.objects.all()
            session_qs = _apply_context_filter(session_qs, context)
            session_qs = _restreindre_eleve(session_qs, request, cours_lookup='cours_id')
            session = get_object_or_404(session_qs, pk=pk)
            participations = Participation.objects.filter(session=session).select_related('apprenant')
            # ✅ PÉRIMÈTRE : un apprenant ne voit que SA ligne de présence
            participations = _restreindre_eleve(participations, request, apprenant_lookup='apprenant')
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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    # ✅ RBAC : lecture élargie, écriture réservée aux créateurs de contenu.
    rbac_resource = "participations"

    def get(self, request):
        try:
            context = get_user_context(request)
            qs = Participation.objects.select_related('session', 'apprenant', 'institution', 'annee_scolaire').all()
            qs = _apply_context_filter(qs, context)
            # ✅ PÉRIMÈTRE : un apprenant ne voit que ses propres présences
            qs = _restreindre_eleve(qs, request, apprenant_lookup='apprenant')

            session_id = request.query_params.get('session')
            if session_id:
                qs = qs.filter(session_id=session_id)

            cours_id = request.query_params.get('cours')
            if cours_id:
                qs = qs.filter(session__cours_id=cours_id)

            apprenant_id = request.query_params.get('apprenant')
            if apprenant_id:
                qs = qs.filter(apprenant_id=apprenant_id)

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    rbac_resource = "participations"

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        try:
            # ✅ Scoping : on ne renvoie QUE les progressions des apprenants
            # accessibles au demandeur (établissement / ses élèves / ses enfants).
            apprenant_id, err = _int_param(request, 'apprenant')
            if err:
                return err

            if apprenant_id:
                apprenant = resolve_apprenant(request, apprenant_id)
                if apprenant is None:
                    return api_error("Apprenant non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
                qs = BlocProgress.objects.filter(apprenant=apprenant)
            else:
                allowed = accessible_apprenants(request.user)
                qs = BlocProgress.objects.all() if allowed is None else BlocProgress.objects.filter(apprenant__in=allowed)

            qs = qs.select_related("apprenant", "bloc").order_by("-updated_at")
            return api_success("Liste des progressions de blocs récupérée avec succès", BlocProgressSerializer(qs, many=True).data)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={"detail": str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BlocProgressToggleAPIView(APIView):
    """Marque un bloc comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def put(self, request, bloc_id):
        try:
            serializer = ProgressToggleSerializer(data=request.data)
            if not serializer.is_valid():
                return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

            if hasattr(request.user, 'apprenant'):
                apprenant = request.user.apprenant
            else:
                # ✅ Staff (Admin/Responsable/Formateur) peut cibler un apprenant,
                # MAIS uniquement dans son périmètre (établissement / ses élèves).
                apprenant_id, err = _int_param(request, 'apprenant')
                if err:
                    return err
                if not apprenant_id:
                    return api_error("Paramètre apprenant requis pour ce rôle.", http_status=status.HTTP_400_BAD_REQUEST)
                apprenant = resolve_apprenant(request, apprenant_id)
                if apprenant is None:
                    return api_error("Apprenant non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
            if not apprenant:
                return api_error("Utilisateur non autorisé", http_status=status.HTTP_403_FORBIDDEN)

            # ✅ SÉCURITÉ : un apprenant ne peut marquer/valider qu'un bloc débloqué.
            if hasattr(request.user, 'apprenant'):
                from .parcours_engine import is_bloc_unlocked_for
                try:
                    bloc_obj = BlocContenu.objects.select_related('sequence__module__cours').get(pk=bloc_id)
                except BlocContenu.DoesNotExist:
                    return api_error("Bloc introuvable.", http_status=status.HTTP_404_NOT_FOUND)
                ok, raison = is_bloc_unlocked_for(apprenant, bloc_obj)
                if not ok:
                    return api_error(raison or 'Bloc verrouillé.', http_status=status.HTTP_403_FORBIDDEN)

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

            # ── Synchronisation avec le système `progress` ──────────────────
            # Le lecteur écrit dans courses.BlocProgress ; on répercute sur
            # progress.ProgressionApprenant (blocs terminés / total).
            try:
                from progress.models import ProgressionApprenant
                from courses.models import InscriptionCours
                cours = progress.bloc.sequence.module.cours
                if InscriptionCours.objects.filter(apprenant=apprenant, cours=cours).exists():
                    pa, _ = ProgressionApprenant.objects.get_or_create(
                        apprenant=apprenant, cours=cours
                    )
                    pa.recalculer_depuis_blocs()
            except Exception:
                pass

            return api_success("Progression mise à jour avec succès", BlocProgressSerializer(progress).data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la mise à jour de la progression", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PROGRESSION - SÉQUENCES
# ============================================================================

class SequenceProgressListAPIView(APIView):
    """Liste les progressions sur les séquences"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        try:
            apprenant_id, err = _int_param(request, 'apprenant')
            if err:
                return err
            if apprenant_id:
                apprenant = resolve_apprenant(request, apprenant_id)
                if apprenant is None:
                    return api_error("Apprenant non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
                qs = SequenceProgress.objects.filter(apprenant=apprenant)
            else:
                allowed = accessible_apprenants(request.user)
                qs = SequenceProgress.objects.all() if allowed is None else SequenceProgress.objects.filter(apprenant__in=allowed)

            qs = qs.select_related('apprenant', 'sequence').order_by('-updated_at')
            serializer = SequenceProgressSerializer(qs, many=True)
            return api_success("Liste des progressions de séquences récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SequenceProgressToggleAPIView(APIView):
    """Marque une séquence comme terminée ou non terminée"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        try:
            apprenant_id, err = _int_param(request, 'apprenant')
            if err:
                return err
            if apprenant_id:
                apprenant = resolve_apprenant(request, apprenant_id)
                if apprenant is None:
                    return api_error("Apprenant non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
                qs = ModuleProgress.objects.filter(apprenant=apprenant)
            else:
                allowed = accessible_apprenants(request.user)
                qs = ModuleProgress.objects.all() if allowed is None else ModuleProgress.objects.filter(apprenant__in=allowed)

            qs = qs.select_related('apprenant', 'module').order_by('-updated_at')
            serializer = ModuleProgressSerializer(qs, many=True)
            return api_success("Liste des progressions de modules récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ModuleProgressToggleAPIView(APIView):
    """Marque un module comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request):
        try:
            apprenant_id, err = _int_param(request, 'apprenant')
            if err:
                return err
            if apprenant_id:
                apprenant = resolve_apprenant(request, apprenant_id)
                if apprenant is None:
                    return api_error("Apprenant non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
                qs = CoursProgress.objects.filter(apprenant=apprenant)
            else:
                allowed = accessible_apprenants(request.user)
                qs = CoursProgress.objects.all() if allowed is None else CoursProgress.objects.filter(apprenant__in=allowed)

            qs = qs.select_related('apprenant', 'cours').order_by('-updated_at')
            serializer = CoursProgressSerializer(qs, many=True)
            return api_success("Liste des progressions de cours récupérée avec succès", serializer.data, status.HTTP_200_OK)
        except Exception as e:
            return api_error("Erreur lors de la récupération des progressions", errors={'detail': str(e)}, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CoursProgressToggleAPIView(APIView):
    """Marque un cours comme terminé ou non terminé"""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

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

    Retourne deux domaines distincts :
      enseignement — volume pédagogique dispensé par le formateur (source : séances)
      apprentissage — temps et progression de l'apprenant (source : BlocAnalytics)

    Rétrocompatibilité : les anciens champs plats (volume_horaire, heures_realisees,
    taux_execution, progression_pct, blocs_termines, total_blocs, source) sont
    conservés au niveau racine du data pour ne pas casser les consommateurs existants.
    """
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _temps_apprentissage_apprenant(apprenant_id, cours):
        """Retourne le temps d'apprentissage en secondes depuis BlocAnalytics."""
        try:
            from analytics.models import BlocAnalytics
            total_sec = BlocAnalytics.objects.filter(
                apprenant_id=apprenant_id,
                bloc__sequence__module__cours=cours,
            ).aggregate(total=Sum('duree_secondes'))['total'] or 0
            return int(total_sec)
        except Exception:
            pass
        try:
            from analytics.models import BlocAnalyticsSummary
            total_sec = BlocAnalyticsSummary.objects.filter(
                apprenant_id=apprenant_id,
                bloc__sequence__module__cours=cours,
            ).aggregate(total=Sum('duree_totale_sec'))['total'] or 0
            return int(total_sec)
        except Exception:
            return 0

    # ── View ──────────────────────────────────────────────────────────────────

    def get(self, request, pk):
        try:
            cours = get_filtered_object(Cours, pk, request, 'Cours')
        except Http404:
            return api_error("Cours introuvable", http_status=status.HTTP_404_NOT_FOUND)

        # ── Bloc enseignement (toujours présent, source = séances formateur) ──
        enseignement = cours.indicateurs_enseignement()

        apprenant_id_raw = request.query_params.get('apprenant')

        # ── Sans apprenant : indicateurs globaux enseignement uniquement ──────
        if not apprenant_id_raw:
            data = {
                **enseignement,                             # spread enseignement au niveau racine
                'enseignement': enseignement,
                'apprentissage': None,
                # ── compat ──
                'volume_horaire':   enseignement['volume_prevu_h'],
                'heures_realisees': enseignement['volume_realise_h'],
                'taux_execution':   enseignement['taux_execution_pct'],
                'progression_pct':  0,
                'blocs_termines':   0,
                'total_blocs':      0,
                'source':           'sessions',
            }
            return Response({'success': True, 'data': data})

        # ✅ Scoping : l'apprenant demandé doit être accessible au requérant
        # (soi-même, ses élèves, ses enfants, l'établissement) — évite l'IDOR.
        apprenant = resolve_apprenant(request, apprenant_id_raw)
        if apprenant is None:
            return api_error("Apprenant non autorisé.", http_status=status.HTTP_403_FORBIDDEN)
        apprenant_id = apprenant.pk

        # ── Progression blocs apprenant ────────────────────────────────────────
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

        # ── Temps d'apprentissage apprenant ────────────────────────────────────
        temps_total_sec = self._temps_apprentissage_apprenant(apprenant_id, cours)
        temps_total_h   = round(temps_total_sec / 3600, 2)

        # Durée estimée totale du cours (somme des blocs)
        duree_estimee_sec = (
            BlocContenu.objects.filter(
                sequence__module__cours=cours,
                est_visible=True,
            ).aggregate(total=Sum('duree_estimee_minutes'))['total'] or 0
        ) * 60

        apprentissage = {
            'temps_total_sec':     temps_total_sec,
            'temps_total_h':       temps_total_h,
            'duree_estimee_h':     round(duree_estimee_sec / 3600, 2),
            'progression_pct':     progression_pct,
            'blocs_termines':      blocs_termines,
            'total_blocs':         total_blocs,
        }

        data = {
            'enseignement':     enseignement,
            'apprentissage':    apprentissage,
            # ── compat : anciens champs plats ──
            'volume_horaire':   enseignement['volume_prevu_h'],
            'heures_realisees': enseignement['volume_realise_h'],
            'taux_execution':   enseignement['taux_execution_pct'],
            'progression_pct':  progression_pct,
            'blocs_termines':   blocs_termines,
            'total_blocs':      total_blocs,
            'source':           'apprenant',
        }
        return Response({'success': True, 'data': data})

# ============================================================================
# PARCOURS — déblocage progressif, reprise, validation (sécurisé)
# ============================================================================

def _get_own_apprenant(user):
    from users.access_control import get_own_apprenant
    return get_own_apprenant(user)


def _cours_non_ouvert(request, cours) -> bool:
    """True si l'utilisateur est un apprenant et que le cours n'a pas commencé."""
    from .publication import cours_commence
    appr = _get_own_apprenant(request.user)
    return appr is not None and not cours_commence(cours)


class ParcoursAPIView(APIView):
    """GET /api/v1/cours/<cours_id>/parcours/ — arbre + états + verrous + reprise."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, cours_id):
        from .parcours_engine import build_parcours, build_parcours_staff, resume_position
        try:
            cours = get_object_or_404(
                filter_queryset_by_role(Cours.objects.all(), request, 'Cours'), pk=cours_id,
            )
            appr = _get_own_apprenant(request.user)
            if appr is None:
                return api_success("Parcours (lecture)", build_parcours_staff(cours), status.HTTP_200_OK)
            from .publication import cours_commence
            if not cours_commence(cours):
                return api_error(
                    "Ce cours n'a pas encore commencé.",
                    http_status=status.HTTP_403_FORBIDDEN,
                )
            data = build_parcours(appr, cours)
            data['resume'] = resume_position(appr, cours)
            return api_success("Parcours", data, status.HTTP_200_OK)
        except Http404:
            return api_error("Cours introuvable.", http_status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return api_error("Erreur parcours.", errors={'detail': str(e)},
                             http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResumeAPIView(APIView):
    """GET /api/v1/cours/<cours_id>/resume/ — position de reprise."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, cours_id):
        from .parcours_engine import resume_position
        appr = _get_own_apprenant(request.user)
        if appr is None:
            return api_error("Réservé aux apprenants.", http_status=status.HTTP_400_BAD_REQUEST)
        try:
            cours = get_object_or_404(
                filter_queryset_by_role(Cours.objects.all(), request, 'Cours'), pk=cours_id,
            )
            from .publication import cours_commence
            if not cours_commence(cours):
                return api_error(
                    "Ce cours n'a pas encore commencé.",
                    http_status=status.HTTP_403_FORBIDDEN,
                )
            return api_success("Reprise", resume_position(appr, cours), status.HTTP_200_OK)
        except Http404:
            return api_error("Cours introuvable.", http_status=status.HTTP_404_NOT_FOUND)


class BlocValiderAPIView(APIView):
    """POST /api/v1/progress/blocs/<bloc_id>/valider/ — valide un bloc (idempotent)."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, bloc_id):
        from .parcours_engine import validate_block
        appr = _get_own_apprenant(request.user)
        if appr is None:
            return api_error("Réservé aux apprenants.", http_status=status.HTTP_400_BAD_REQUEST)
        try:
            bloc = BlocContenu.objects.select_related('sequence__module__cours').get(pk=bloc_id)
        except BlocContenu.DoesNotExist:
            return api_error("Bloc introuvable.", http_status=status.HTTP_404_NOT_FOUND)
        cours = bloc.sequence.module.cours
        from .models import InscriptionCours
        if not InscriptionCours.objects.filter(apprenant=appr, cours=cours).exists():
            return api_error("Accès refusé.", http_status=status.HTTP_403_FORBIDDEN)
        from .publication import cours_commence
        if not cours_commence(cours):
            return api_error(
                "Ce cours n'a pas encore commencé.",
                http_status=status.HTTP_403_FORBIDDEN,
            )
        res = validate_block(appr, bloc)
        if not res.get('ok'):
            return api_error(res.get('raison', 'Bloc verrouillé.'), http_status=status.HTTP_403_FORBIDDEN)
        return api_success("Bloc validé.", res, status.HTTP_200_OK)


# ============================================================================
# DUPLICATION DE MODULES vers une autre année scolaire
# ============================================================================

class ModuleCopyAPIView(APIView):
    """Copie des modules (et tout leur contenu) dans un cours cible d'une
    année postérieure, du même formateur."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request):
        from .duplication import copier_module
        from .utils import can_manage_cours

        ids      = request.data.get("module_ids") or []
        cible_id = request.data.get("cours_cible")
        if not ids or not cible_id:
            return api_error("`module_ids` et `cours_cible` sont requis.")
        try:
            ids = [int(i) for i in ids]
        except (TypeError, ValueError):
            return api_error("`module_ids` doit être une liste d'identifiants.")

        modules = list(Module.objects.filter(id__in=ids).select_related("cours", "cours__annee_scolaire"))
        if not modules:
            return api_error("Aucun module trouvé.", http_status=status.HTTP_404_NOT_FOUND)

        cours_source = modules[0].cours
        if any(m.cours_id != cours_source.id for m in modules):
            return api_error("Tous les modules doivent appartenir au même cours.")

        try:
            cours_cible = Cours.objects.select_related("annee_scolaire", "enseignant").get(pk=cible_id)
        except Cours.DoesNotExist:
            return api_error("Cours cible introuvable.", http_status=status.HTTP_404_NOT_FOUND)

        if not can_manage_cours(request.user, cours_source) or not can_manage_cours(request.user, cours_cible):
            return api_error("Action réservée au formateur du cours.", http_status=status.HTTP_403_FORBIDDEN)

        # ✅ Même formateur
        if cours_cible.enseignant_id != cours_source.enseignant_id:
            return api_error("Le cours cible doit être du même formateur que le cours source.")

        # ✅ Année POSTÉRIEURE
        src_annee = getattr(cours_source, "annee_scolaire", None)
        tgt_annee = getattr(cours_cible, "annee_scolaire", None)
        if not src_annee or not tgt_annee:
            return api_error("Les cours source et cible doivent avoir une année scolaire.")
        if src_annee.id == tgt_annee.id:
            return api_error("Le cours cible doit être dans une année différente.")
        if src_annee.date_debut and tgt_annee.date_debut and tgt_annee.date_debut <= src_annee.date_debut:
            return api_error("L'année cible doit être postérieure à l'année source.")

        new_ids = [copier_module(m, cours_cible).id for m in modules]
        return api_success(
            f"{len(new_ids)} module(s) copié(s) dans « {cours_cible} ».",
            {"module_ids": new_ids, "cours_cible": cours_cible.id},
            status.HTTP_201_CREATED,
        )
