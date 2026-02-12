from django.contrib import admin
from .models import BlocAnalytics, QuestionAnalytics, ContenuGenere, RecommandationPedagogique

@admin.register(BlocAnalytics)
class BlocAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('apprenant', 'bloc', 'temps_total_secondes', 'nombre_visites', 'score_comprehension')
    list_filter = ('difficulte_percue', 'derniere_visite')
    search_fields = ('apprenant__nom', 'bloc__titre')
    readonly_fields = ('premiere_visite', 'derniere_visite')

@admin.register(QuestionAnalytics)
class QuestionAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('apprenant', 'question', 'nombre_tentatives', 'nombre_echecs')
    list_filter = ('derniere_tentative',)
    search_fields = ('apprenant__nom', 'question__enonce_texte')

@admin.register(ContenuGenere)
class ContenuGenereAdmin(admin.ModelAdmin):
    list_display = ('titre', 'apprenant', 'type_generation', 'a_ete_consulte', 'date_generation')
    list_filter = ('type_generation', 'a_ete_consulte', 'a_aide')
    search_fields = ('titre', 'apprenant__nom')
    readonly_fields = ('date_generation',)

@admin.register(RecommandationPedagogique)
class RecommandationAdmin(admin.ModelAdmin):
    list_display = ('apprenant', 'type_recommandation', 'priorite', 'est_vue', 'est_suivie', 'date_creation')
    list_filter = ('type_recommandation', 'priorite', 'est_vue', 'est_suivie')
    search_fields = ('apprenant__nom', 'message')
    readonly_fields = ('date_creation',)