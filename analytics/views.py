from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import BlocAnalytics, RecommandationPedagogique, ContenuGenere
from .serializers import BlocAnalyticsSerializer, RecommandationSerializer, ContenuGenereSerializer
from django.db import models

class BlocAnalyticsViewSet(viewsets.ModelViewSet):
    serializer_class = BlocAnalyticsSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return BlocAnalytics.objects.filter(apprenant=self.request.user.apprenant)
    
    @action(detail=False, methods=['post'])
    def track_interaction(self, request):
        """
        Endpoint pour tracker l'interaction avec un bloc
        Body: {
            "bloc_id": 123,
            "temps_passe_secondes": 60,
            "pourcentage_scroll": 75,
            "interactions": {}
        }
        """
        apprenant = request.user.apprenant
        bloc_id = request.data.get('bloc_id')
        temps_passe = request.data.get('temps_passe_secondes', 0)
        pourcentage_scroll = request.data.get('pourcentage_scroll', 0)
        interactions = request.data.get('interactions', {})
        
        analytics, created = BlocAnalytics.objects.get_or_create(
            apprenant=apprenant,
            bloc_id=bloc_id
        )
        
        analytics.temps_total_secondes += temps_passe
        if created:
            analytics.nombre_visites = 1
        else:
            analytics.nombre_visites += 1
        
        analytics.pourcentage_scroll = max(analytics.pourcentage_scroll, pourcentage_scroll)
        analytics.interactions = interactions
        analytics.save()
        
        # Déclencher analyse si seuils dépassés
        if analytics.temps_total_secondes > 900:  # 15 min
            from services.recommendation_engine import RecommendationEngine
            engine = RecommendationEngine(apprenant)
            engine._generer_reco_bloc_difficile(analytics)
        
        return Response({
            'status': 'tracked',
            'total_time': analytics.temps_total_secondes,
            'visits': analytics.nombre_visites
        })


class RecommandationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecommandationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return RecommandationPedagogique.objects.filter(
            apprenant=self.request.user.apprenant,
            est_vue=False
        ).filter(
            models.Q(date_expiration__isnull=True) | 
            models.Q(date_expiration__gt=timezone.now())
        ).order_by('priorite', '-date_creation')
    
    @action(detail=True, methods=['post'])
    def marquer_vue(self, request, pk=None):
        reco = self.get_object()
        reco.est_vue = True
        reco.date_vue = timezone.now()
        reco.save()
        return Response({'status': 'marked_as_seen'})
    
    @action(detail=True, methods=['post'])
    def marquer_suivie(self, request, pk=None):
        reco = self.get_object()
        reco.est_suivie = True
        reco.save()
        return Response({'status': 'followed'})


class ContenuGenereViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ContenuGenereSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ContenuGenere.objects.filter(apprenant=self.request.user.apprenant)
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.a_ete_consulte = True
        instance.nombre_consultations += 1
        instance.date_derniere_consultation = timezone.now()
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def feedback(self, request, pk=None):
        """Body: {"a_aide": true/false}"""
        contenu = self.get_object()
        contenu.a_aide = request.data.get('a_aide')
        contenu.save()
        return Response({'status': 'feedback_saved'})