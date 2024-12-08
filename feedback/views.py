from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Feedback, Progression, HistoriqueProgression, PlanAction
from .serializers import FeedbackSerializer, ProgressionSerializer, HistoriqueProgressionSerializer, PlanActionSerializer

# Feedback
class FeedbackListCreateAPIView(APIView):
    def get(self, request):
        feedbacks = Feedback.objects.all()
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
    def get(self, request):
        progressions = Progression.objects.all()
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
    def get(self, request):
        historique = HistoriqueProgression.objects.all()
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
    def get(self, request):
        plans = PlanAction.objects.all()
        serializer = PlanActionSerializer(plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PlanActionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
