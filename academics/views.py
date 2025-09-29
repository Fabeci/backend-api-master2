import secrets
import string
import uuid
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, status
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import BaseUserManager
from academics.models import Classe, Filiere, Groupe, Inscription, Institution
from academics.serializers import ClasseSerializer, FiliereSerializer, GroupeSerializer, InscriptionSerializer, InstitutionSerializer
from users.models import Admin, UserRole


def custom_404_handler(request, exception=None):
    return Response({
        "status": 404,
        "success": False,
        "message": "Ressource non trouvée. Vérifiez l'URL.",
        "data": None
    }, status=404)


# Create your views here.
class InstitutionAPIView(APIView):

    def get(self, request, pk=None):
        if pk:
            institution = get_object_or_404(Institution, pk=pk)
            serializer = InstitutionSerializer(institution)
            return Response({"status": 200, "success": True, "message": "Institution trouvée", "data": serializer.data})
        else:
            institutions = Institution.objects.all()
            serializer = InstitutionSerializer(institutions, many=True)
            return Response({"status": 200, "success": True, "message": "Liste des institutions", "data": serializer.data})

    def post(self, request):
        # Sérialisation des données de la requête
        serializer = InstitutionSerializer(data=request.data)
        
        if serializer.is_valid():
            # Si les données sont valides, crée l'institution et l'administrateur
            institution = serializer.save()

            # Retourne une réponse avec succès
            return Response({
                "status": 201,
                "success": True,
                "message": "Institution et administrateur créés avec succès",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        # Si la validation échoue, retourne les erreurs
        return Response({
            "status": 400,
            "success": False,
            "message": "Erreur de validation des données de l'établissement",
            "data": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        serializer = InstitutionSerializer(institution, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"status": 200, "success": True, "message": "Institution mise à jour avec succès", "data": serializer.data})
        return Response({"status": 400, "success": False, "message": "Erreur de validation", "data": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        serializer = InstitutionSerializer(institution, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"status": 200, "success": True, "message": "Institution mise à jour partiellement", "data": serializer.data})
        return Response({"status": 400, "success": False, "message": "Erreur de validation", "data": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        institution.delete()
        return Response({"status": 204, "success": True, "message": "Institution supprimée"}, status=status.HTTP_204_NO_CONTENT)
    
    
class FiliereListCreateAPIView(APIView):
    def get(self, request):
        filieres = Filiere.objects.all()
        serializer = FiliereSerializer(filieres, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = FiliereSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FiliereDetailAPIView(APIView):
    def get_object(self, pk):
        try:
            return Filiere.objects.get(pk=pk)
        except Filiere.DoesNotExist:
            return None

    def get(self, request, pk):
        filiere = self.get_object(pk)
        if filiere:
            serializer = FiliereSerializer(filiere)
            return Response(serializer.data)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        filiere = self.get_object(pk)
        if filiere:
            serializer = FiliereSerializer(filiere, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        filiere = self.get_object(pk)
        if filiere:
            filiere.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class GroupeListCreateAPIView(APIView):
    def get(self, request):
        groupes = Groupe.objects.all()
        serializer = GroupeSerializer(groupes, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = GroupeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GroupeDetailAPIView(APIView):
    def get_object(self, pk):
        try:
            return Groupe.objects.get(pk=pk)
        except Groupe.DoesNotExist:
            return None

    def get(self, request, pk):
        groupe = self.get_object(pk)
        if groupe:
            serializer = GroupeSerializer(groupe)
            return Response(serializer.data)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        groupe = self.get_object(pk)
        if groupe:
            serializer = GroupeSerializer(groupe, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        groupe = self.get_object(pk)
        if groupe:
            groupe.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class ClasseListCreateAPIView(APIView):
    def get(self, request):
        classes = Classe.objects.all()
        serializer = ClasseSerializer(classes, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ClasseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ClasseDetailAPIView(APIView):
    def get_object(self, pk):
        try:
            return Classe.objects.get(pk=pk)
        except Classe.DoesNotExist:
            return None

    def get(self, request, pk):
        classe = self.get_object(pk)
        if classe:
            serializer = ClasseSerializer(classe)
            return Response(serializer.data)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        classe = self.get_object(pk)
        if classe:
            serializer = ClasseSerializer(classe, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        classe = self.get_object(pk)
        if classe:
            classe.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    
    
class InscriptionListCreateAPIView(APIView):
    def get(self, request):
        inscriptions = Inscription.objects.all()
        serializer = InscriptionSerializer(inscriptions, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = InscriptionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InscriptionDetailAPIView(APIView):
    def get_object(self, pk):
        try:
            return Inscription.objects.get(pk=pk)
        except Inscription.DoesNotExist:
            return None

    def get(self, request, pk):
        inscription = self.get_object(pk)
        if inscription:
            serializer = InscriptionSerializer(inscription)
            return Response(serializer.data)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        inscription = self.get_object(pk)
        if inscription:
            serializer = InscriptionSerializer(inscription, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        inscription = self.get_object(pk)
        if inscription:
            inscription.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)