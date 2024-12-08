from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Ressource, RessourceSupplementaire, PieceJointe, RessourcePieceJointe, RessourceSuppPieceJointe
from .serializers import (
    RessourceSerializer, RessourceSupplementaireSerializer, 
    PieceJointeSerializer, RessourcePieceJointeSerializer, 
    RessourceSuppPieceJointeSerializer
)

# Ressource
class RessourceListCreateAPIView(APIView):
    def get(self, request):
        ressources = Ressource.objects.all()
        serializer = RessourceSerializer(ressources, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RessourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# RessourceSupplementaire
class RessourceSupplementaireListCreateAPIView(APIView):
    def get(self, request):
        ressources_supplementaires = RessourceSupplementaire.objects.all()
        serializer = RessourceSupplementaireSerializer(ressources_supplementaires, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RessourceSupplementaireSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# PieceJointe
class PieceJointeListCreateAPIView(APIView):
    def get(self, request):
        pieces_jointes = PieceJointe.objects.all()
        serializer = PieceJointeSerializer(pieces_jointes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PieceJointeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# RessourcePieceJointe
class RessourcePieceJointeListCreateAPIView(APIView):
    def get(self, request):
        ressources_pieces_jointes = RessourcePieceJointe.objects.all()
        serializer = RessourcePieceJointeSerializer(ressources_pieces_jointes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RessourcePieceJointeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# RessourceSuppPieceJointe
class RessourceSuppPieceJointeListCreateAPIView(APIView):
    def get(self, request):
        ressources_supp_pieces_jointes = RessourceSuppPieceJointe.objects.all()
        serializer = RessourceSuppPieceJointeSerializer(ressources_supp_pieces_jointes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RessourceSuppPieceJointeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
