from ast import Module
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import InscriptionCours, Participation, Sequence, Session, Suivi
from .serializers import InscriptionCoursSerializer, ModuleSerializer, ParticipationSerializer, SequenceSerializer, SessionSerializer, SuiviSerializer


# Create your views here.
class SequenceListCreateAPIView(APIView):
    def get(self, request):
        sequences = Sequence.objects.all()
        serializer = SequenceSerializer(sequences, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SequenceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class ModuleListCreateAPIView(APIView):
    def get(self, request):
        modules = Module.objects.all()
        serializer = ModuleSerializer(modules, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ModuleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class InscriptionCoursListCreateAPIView(APIView):
    def get(self, request):
        inscriptions = InscriptionCours.objects.all()
        serializer = InscriptionCoursSerializer(inscriptions, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = InscriptionCoursSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class SuiviListCreateAPIView(APIView):
    def get(self, request):
        suivis = Suivi.objects.all()
        serializer = SuiviSerializer(suivis, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SuiviSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class SessionListCreateAPIView(APIView):
    def get(self, request):
        sessions = Session.objects.all()
        serializer = SessionSerializer(sessions, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = SessionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class ParticipationListCreateAPIView(APIView):
    def get(self, request):
        participations = Participation.objects.all()
        serializer = ParticipationSerializer(participations, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ParticipationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)