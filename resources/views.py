from core.rbac import RBACPermission
from core.tenant import default_institution_id
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import Ressource, RessourceSupplementaire, PieceJointe, RessourcePieceJointe, RessourceSuppPieceJointe
from .serializers import (
    RessourceSerializer, RessourceSupplementaireSerializer, 
    PieceJointeSerializer, RessourcePieceJointeSerializer, 
    RessourceSuppPieceJointeSerializer
)

# ✅ SÉCURITÉ : ces endpoints étaient totalement anonymes (lecture + création,
# y compris upload de fichiers). Ils exigent désormais une authentification.
AUTH_REQUIRED = [permissions.IsAuthenticated]

# Ressource
class RessourceListCreateAPIView(APIView):
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        iid = default_institution_id()
        ressources = Ressource.objects.filter(sequence__module__cours__institution_id=iid)
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
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        iid = default_institution_id()
        ressources_supplementaires = RessourceSupplementaire.objects.filter(
            Q(sequence__module__cours__institution_id=iid) | Q(sequence__isnull=True)
        )
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
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        iid = default_institution_id()
        pieces_jointes = PieceJointe.objects.filter(
            Q(ressource__sequence__module__cours__institution_id=iid)
            | Q(ressource_supplementaire__sequence__module__cours__institution_id=iid)
            | Q(ressource__isnull=True, ressource_supplementaire__isnull=True)
        )
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
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        iid = default_institution_id()
        ressources_pieces_jointes = RessourcePieceJointe.objects.filter(
            ressource__sequence__module__cours__institution_id=iid
        )
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
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        iid = default_institution_id()
        ressources_supp_pieces_jointes = RessourceSuppPieceJointe.objects.filter(
            Q(ressource__sequence__module__cours__institution_id=iid)
            | Q(ressource__sequence__isnull=True)
        )
        serializer = RessourceSuppPieceJointeSerializer(ressources_supp_pieces_jointes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RessourceSuppPieceJointeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
