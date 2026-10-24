from django.db.models import Q
from core.tenant import default_institution_id
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import Feedback, Progression, HistoriqueProgression, PlanAction
from .serializers import FeedbackSerializer, ProgressionSerializer, HistoriqueProgressionSerializer, PlanActionSerializer

# ✅ SÉCURITÉ : app legacy non routée, mais on ferme l'accès anonyme par défaut
# au cas où elle serait rebranchée.
AUTH_REQUIRED = [permissions.IsAuthenticated]

# Feedback
class FeedbackListCreateAPIView(APIView):
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        iid = default_institution_id()
        feedbacks = Feedback.objects.filter(
            Q(cours__institution_id=iid) | Q(evaluation__cours__institution_id=iid)
            | Q(cours__isnull=True, evaluation__isnull=True)
        )
        serializer = FeedbackSerializer(feedbacks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = FeedbackSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Progression
class ProgressionListCreateAPIView(APIView):
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        progressions = Progression.objects.filter(cours__institution_id=default_institution_id())
        serializer = ProgressionSerializer(progressions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProgressionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# HistoriqueProgression
class HistoriqueProgressionListCreateAPIView(APIView):
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        historique = HistoriqueProgression.objects.filter(progression__cours__institution_id=default_institution_id())
        serializer = HistoriqueProgressionSerializer(historique, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = HistoriqueProgressionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# PlanAction
class PlanActionListCreateAPIView(APIView):
    permission_classes = AUTH_REQUIRED

    def get(self, request):
        plans = PlanAction.objects.filter(progression__cours__institution_id=default_institution_id())
        serializer = PlanActionSerializer(plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PlanActionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
