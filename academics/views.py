import secrets
import string
import uuid
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, status
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import BaseUserManager
from academics.models import Classe, Departement, Filiere, Groupe, Inscription, Institution
from academics.serializers import ClasseSerializer, DepartementSerializer, FiliereSerializer, GroupeSerializer, InscriptionSerializer, InstitutionSerializer
from users.models import Admin, UserRole
from rest_framework import status as drf_status


def custom_404_handler(request, exception=None):
    return Response({
        "status": 404,
        "success": False,
        "message": "Ressource non trouvée. Vérifiez l'URL.",
        "data": None
    }, status=404)

def api_success(message: str, data=None, http_status=drf_status.HTTP_200_OK):
    return Response(
        {
            "success": True,
            "status": http_status,
            "message": message,
            "data": data,
        },
        status=http_status,
    )

def api_error(message: str, errors=None, http_status=drf_status.HTTP_400_BAD_REQUEST, data=None):
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
        "data": data,
    }
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# Create your views here.
class InstitutionAPIView(APIView):

    def get(self, request, pk=None):
        if pk:
            institution = get_object_or_404(Institution, pk=pk)
            serializer = InstitutionSerializer(institution)
            return api_success("Institution trouvée", serializer.data, status.HTTP_200_OK)

        institutions = Institution.objects.all()
        serializer = InstitutionSerializer(institutions, many=True)
        return api_success("Liste des institutions", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        serializer = InstitutionSerializer(data=request.data)
        if serializer.is_valid():
            institution = serializer.save()
            return api_success(
                "Institution créée avec succès",
                InstitutionSerializer(institution).data,
                status.HTTP_201_CREATED
            )
        return api_error(
            "Erreur de validation des données de l'établissement",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST
        )

    def put(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        serializer = InstitutionSerializer(institution, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Institution mise à jour avec succès", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        serializer = InstitutionSerializer(institution, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Institution mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        institution.delete()
        return api_success("Institution supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)

    
class FiliereListCreateAPIView(APIView):
    def get(self, request):
        filieres = Filiere.objects.all()
        serializer = FiliereSerializer(filieres, many=True)
        return api_success("Liste des filières", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        serializer = FiliereSerializer(data=request.data)
        if serializer.is_valid():
            filiere = serializer.save()
            return api_success("Filière créée avec succès", FiliereSerializer(filiere).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class FiliereDetailAPIView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Filiere, pk=pk)

    def get(self, request, pk):
        filiere = self.get_object(pk)
        serializer = FiliereSerializer(filiere)
        return api_success("Filière trouvée", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        filiere = self.get_object(pk)
        serializer = FiliereSerializer(filiere, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Filière mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        filiere = self.get_object(pk)
        serializer = FiliereSerializer(filiere, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Filière mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        filiere = self.get_object(pk)
        filiere.delete()
        return api_success("Filière supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)


class GroupeListCreateAPIView(APIView):
    def get(self, request):
        groupes = Groupe.objects.all().prefetch_related("enseignants")
        serializer = GroupeSerializer(groupes, many=True)
        return api_success("Liste des groupes", serializer.data, status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request):
        serializer = GroupeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        groupe = serializer.save()
        return api_success("Groupe créé avec succès", GroupeSerializer(groupe).data, status.HTTP_201_CREATED)


class GroupeDetailAPIView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Groupe, pk=pk)

    def get(self, request, pk):
        groupe = self.get_object(pk)
        serializer = GroupeSerializer(groupe)
        return api_success("Groupe trouvé", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        groupe = self.get_object(pk)
        serializer = GroupeSerializer(groupe, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Groupe mis à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        groupe = self.get_object(pk)
        serializer = GroupeSerializer(groupe, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Groupe mis à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        groupe = self.get_object(pk)
        groupe.delete()
        return api_success("Groupe supprimé", data=None, http_status=status.HTTP_204_NO_CONTENT)



class ClasseListCreateAPIView(APIView):
    def get(self, request):
        classes = Classe.objects.all()
        serializer = ClasseSerializer(classes, many=True)
        return api_success("Liste des classes", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        serializer = ClasseSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Classe créée avec succès", ClasseSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class ClasseDetailAPIView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Classe, pk=pk)

    def get(self, request, pk):
        classe = self.get_object(pk)
        serializer = ClasseSerializer(classe)
        return api_success("Classe trouvée", serializer.data, status.HTTP_200_OK)

    def put(self, request, pk):
        classe = self.get_object(pk)
        serializer = ClasseSerializer(classe, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Classe mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        classe = self.get_object(pk)
        serializer = ClasseSerializer(classe, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Classe mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        classe = self.get_object(pk)
        classe.delete()
        return api_success("Classe supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)
    

class DepartementListCreateAPIView(APIView):
    def get(self, request):
        departements = Departement.objects.select_related("institution", "responsable_academique")
        serializer = DepartementSerializer(departements, many=True)
        return api_success("Liste des départements", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        serializer = DepartementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return api_success("Département créé avec succès", DepartementSerializer(obj).data, status.HTTP_201_CREATED)


class DepartementDetailAPIView(APIView):
    def get_object(self, pk):
        return get_object_or_404(
            Departement.objects.select_related("institution", "responsable_academique"),
            pk=pk
        )

    def get(self, request, pk):
        obj = self.get_object(pk)
        return api_success("Département trouvé", DepartementSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk)
        serializer = DepartementSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success("Département mis à jour", serializer.data, status.HTTP_200_OK)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        serializer = DepartementSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success("Département mis à jour partiellement", serializer.data, status.HTTP_200_OK)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        obj.delete()
        return api_success("Département supprimé", data=None, http_status=status.HTTP_204_NO_CONTENT)
    
    
class InscriptionListCreateAPIView(APIView):
    def get(self, request):
        inscriptions = Inscription.objects.all()
        serializer = InscriptionSerializer(inscriptions, many=True)
        return api_success("Liste des inscriptions", serializer.data, status.HTTP_200_OK)

    def post(self, request):
        serializer = InscriptionSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success("Inscription créée avec succès", InscriptionSerializer(obj).data, status.HTTP_201_CREATED)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)


class InscriptionDetailAPIView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Inscription, pk=pk)

    def get(self, request, pk):
        obj = self.get_object(pk)
        return api_success("Inscription trouvée", InscriptionSerializer(obj).data, status.HTTP_200_OK)

    def put(self, request, pk):
        obj = self.get_object(pk)
        serializer = InscriptionSerializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return api_success("Inscription mise à jour", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        serializer = InscriptionSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return api_success("Inscription mise à jour partiellement", serializer.data, status.HTTP_200_OK)
        return api_error("Erreur de validation", errors=serializer.errors, http_status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        obj.delete()
        return api_success("Inscription supprimée", data=None, http_status=status.HTTP_204_NO_CONTENT)
