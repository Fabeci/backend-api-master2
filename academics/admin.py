# academics/admin.py
from django.contrib import admin
from .models import (
    Institution, Departement, DomaineEtude, Filiere,
    Matiere, Groupe, Classe, Specialite, AnneeScolaire, Inscription
)


class InscriptionInline(admin.TabularInline):
    model = Inscription
    extra = 0
    autocomplete_fields = ["apprenant", "institution", "annee_scolaire"]

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "pays", "statut", "type_institution", "nombre_etudiants")
    list_filter = ("statut", "type_institution", "pays")
    search_fields = ("nom", "email", "site_web")
    # tu peux aussi mettre autocomplete_fields si tu préfères :
    # autocomplete_fields = ("formateurs",)


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "responsable_academique")
    list_filter = ("institution",)
    search_fields = ("nom", "institution__nom", "responsable_academique__nom", "responsable_academique__prenom")
    autocomplete_fields = ("institution", "responsable_academique")


@admin.register(DomaineEtude)
class DomaineEtudeAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "domaine_etude", "statut", "date_creation")
    list_filter = ("statut", "domaine_etude")
    search_fields = ("nom", "domaine_etude__nom")


@admin.register(Matiere)
class MatiereAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)
    filter_horizontal = ("enseignants",)  # ManyToMany Formateurs
    # ou autocomplete_fields = ("enseignants",) si tu préfères


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "date_creation")
    search_fields = ("nom",)
    inlines = [InscriptionInline]
    list_filter = ("date_creation",)
    filter_horizontal = ("filieres", "matieres")
    autocomplete_fields = ["groupes"]


@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display = ("id", "nom")
    search_fields = ("nom",)


@admin.register(AnneeScolaire)
class AnneeScolaireAdmin(admin.ModelAdmin):
    list_display = ("id", "annee_format_classique", "date_debut", "date_fin")
    search_fields = ("annee_format_classique",)
    date_hierarchy = "date_debut"


@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "institution", "annee_scolaire", "statut", "statut_paiement")
    list_filter = ("statut", "statut_paiement", "institution", "annee_scolaire")
    search_fields = (
        "apprenant__email", "apprenant__nom", "apprenant__prenom",
        "institution__nom", "annee_scolaire__annee_format_classique"
    )
    autocomplete_fields = ("apprenant", "institution", "annee_scolaire")
