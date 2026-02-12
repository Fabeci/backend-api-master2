from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum

# ❌ NE PAS importer ici
# from analytics.models import ...


class RecommendationEngine:
    SEUIL_TEMPS_EXCESSIF = 900  # 15 minutes
    SEUIL_ECHECS_QUESTION = 2
    SEUIL_SCORE_FAIBLE = 0.5
    
    def __init__(self, apprenant):
        self.apprenant = apprenant
    
    def analyser_et_recommander(self):
        """
        Analyse globale et génère des recommandations
        """
        # ✅ Lazy imports
        from analytics.models import BlocAnalytics, QuestionAnalytics
        
        recommandations = []
        
        # 1. Détecter blocs difficiles
        blocs_difficiles = self._detecter_blocs_difficiles()
        for bloc_analytics in blocs_difficiles:
            reco = self._generer_reco_bloc_difficile(bloc_analytics)
            if reco:
                recommandations.append(reco)
        
        # 2. Détecter questions fragiles
        questions_fragiles = self._detecter_questions_fragiles()
        for question_analytics in questions_fragiles:
            reco = self._generer_reco_question_fragile(question_analytics)
            if reco:
                recommandations.append(reco)
        
        # 3. Détecter fatigue
        if self._detecter_fatigue():
            reco = self._generer_reco_pause()
            recommandations.append(reco)
        
        return recommandations
    
    def _detecter_blocs_difficiles(self):
        from analytics.models import BlocAnalytics
        
        return BlocAnalytics.objects.filter(
            apprenant=self.apprenant,
            temps_total_secondes__gte=self.SEUIL_TEMPS_EXCESSIF,
            bloc__est_visible=True
        ).select_related('bloc')
    
    def _generer_reco_bloc_difficile(self, bloc_analytics):
        from analytics.models import RecommandationPedagogique, ContenuGenere
        
        bloc = bloc_analytics.bloc
        
        # Vérifier si recommandation existe déjà
        if RecommandationPedagogique.objects.filter(
            apprenant=self.apprenant,
            bloc_cible=bloc,
            est_vue=False
        ).exists():
            return None
        
        # Vérifier si contenu alternatif existe
        contenu_existant = ContenuGenere.objects.filter(
            apprenant=self.apprenant,
            bloc_source=bloc,
            type_generation='alternative'
        ).first()
        
        if not contenu_existant:
            message = f"Vous semblez avoir des difficultés avec '{bloc.titre}'. Nous préparons une explication alternative pour vous !"
        else:
            message = f"Vous avez passé beaucoup de temps sur '{bloc.titre}'. Essayez cette approche différente !"
        
        return RecommandationPedagogique.objects.create(
            apprenant=self.apprenant,
            type_recommandation='changement_approche',
            message=message,
            bloc_cible=bloc,
            contenu_genere=contenu_existant,
            priorite=2,
            date_expiration=timezone.now() + timedelta(days=7)
        )
    
    def _detecter_questions_fragiles(self):
        from analytics.models import QuestionAnalytics
        
        return QuestionAnalytics.objects.filter(
            apprenant=self.apprenant,
            nombre_echecs__gte=self.SEUIL_ECHECS_QUESTION
        ).select_related('question')
    
    def _generer_reco_question_fragile(self, question_analytics):
        from analytics.models import RecommandationPedagogique
        
        question = question_analytics.question
        
        # Trouver le bloc source
        if question.quiz:
            bloc_source = question.quiz.sequence.blocs_contenu.first()
        else:
            bloc_source = None
        
        if not bloc_source:
            return None
        
        return RecommandationPedagogique.objects.create(
            apprenant=self.apprenant,
            type_recommandation='bloc_revoir',
            message=f"Vous avez des difficultés avec ce concept. Revoyons-le avec une autre approche !",
            bloc_cible=bloc_source,
            priorite=1,
            date_expiration=timezone.now() + timedelta(days=5)
        )
    
    def _detecter_fatigue(self):
        from analytics.models import BlocAnalytics
        
        derniere_heure = timezone.now() - timedelta(hours=1)
        activite = BlocAnalytics.objects.filter(
            apprenant=self.apprenant,
            derniere_visite__gte=derniere_heure
        ).aggregate(total=Sum('temps_total_secondes'))
        
        return activite['total'] and activite['total'] > 3600  # 1h+
    
    def _generer_reco_pause(self):
        from analytics.models import RecommandationPedagogique
        
        return RecommandationPedagogique.objects.create(
            apprenant=self.apprenant,
            type_recommandation='pause',
            message="Vous travaillez beaucoup ! Une pause de 10 minutes améliorerait votre concentration 🧘",
            priorite=3,
            date_expiration=timezone.now() + timedelta(hours=2)
        )