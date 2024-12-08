from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, status
from academics.models import AnneeScolaire, Classe, DomaineEtude, Filiere, Groupe, Inscription, Matiere, Specialite
from academics.serializers import AnneeScolaireSerializer, ClasseSerializer, FiliereSerializer, GroupeSerializer, InscriptionSerializer, InstitutionSerializer, DomaineEtudeSerializer, MatiereSerializer, SpecialiteSerializer

# Create your views here.
class InstitutionCreateAPIView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = InstitutionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class DomaineEtudeViewSet(viewsets.ModelViewSet):
    queryset = DomaineEtude.objects.all()
    serializer_class = DomaineEtudeSerializer
    

class MatiereViewSet(viewsets.ModelViewSet):
    queryset = Matiere.objects.all()
    serializer_class = MatiereSerializer
    
    
class SpecialiteViewSet(viewsets.ModelViewSet):
    queryset = Specialite.objects.all()
    serializer_class = SpecialiteSerializer
    
    
class AnneeScolaireViewSet(viewsets.ModelViewSet):
    queryset = AnneeScolaire.objects.all()
    serializer_class = AnneeScolaireSerializer
    
    
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