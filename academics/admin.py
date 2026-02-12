# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    Institution, Departement, DomaineEtude, Filiere,
    Matiere, Groupe, Classe, Specialite, AnneeScolaire, Inscription
)


class InscriptionInline(admin.TabularInline):
    model = Inscription
    extra = 0
    autocomplete_fields = ["apprenant", "institution", "annee_scolaire"]


# ✅ Inline pour gérer les Groupes dans une Classe
class GroupeInline(admin.TabularInline):
    model = Groupe
    extra = 0
    autocomplete_fields = ["institution", "annee_scolaire"]
    filter_horizontal = ("enseignants",)  # M2M


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "pays", "statut", "type_institution", "nombre_etudiants")
    list_filter = ("statut", "type_institution", "pays")
    search_fields = ("nom", "email", "site_web")


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "responsable_academique")
    list_filter = ("institution",)
    search_fields = ("nom", "institution__nom", "responsable_academique__nom", "responsable_academique__prenom")
    autocomplete_fields = ("institution", "responsable_academique")


@admin.register(DomaineEtude)
class DomaineEtudeAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "est_actif")
    search_fields = ("nom", "institution__nom")
    list_filter = ("institution", "est_actif")
    autocomplete_fields = ("institution",)


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "domaine_etude", "statut", "date_creation", "est_actif")
    list_filter = ("institution", "statut", "domaine_etude", "est_actif")
    search_fields = ("nom", "domaine_etude__nom", "institution__nom")
    autocomplete_fields = ("institution", "domaine_etude")


@admin.register(Matiere)
class MatiereAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "est_actif")
    search_fields = ("nom", "institution__nom")
    list_filter = ("institution", "est_actif")
    autocomplete_fields = ("institution",)


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "annee_scolaire", "classe")
    search_fields = ("nom", "institution__nom", "classe__nom", "annee_scolaire__annee_format_classique")
    list_filter = ("institution", "annee_scolaire")
    filter_horizontal = ("enseignants",)
    autocomplete_fields = ("institution", "annee_scolaire", "classe")


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "annee_scolaire", "date_creation")
    search_fields = ("nom", "institution__nom", "annee_scolaire__annee_format_classique")
    list_filter = ("institution", "annee_scolaire")
    filter_horizontal = ("filieres", "matieres")
    autocomplete_fields = ("institution", "annee_scolaire", "filieres", "matieres")
    inlines = [GroupeInline, InscriptionInline]  # ✅ groupes gérés ici


@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display = ("id", "nom", "institution", "est_actif")
    search_fields = ("nom", "institution__nom")
    list_filter = ("institution", "est_actif")
    autocomplete_fields = ("institution",)


@admin.register(AnneeScolaire)
class AnneeScolaireAdmin(admin.ModelAdmin):
    list_display = ("id", "annee_format_classique", "institution", "date_debut", "date_fin", "est_active")
    search_fields = ("annee_format_classique", "institution__nom")
    list_filter = ("institution", "est_active")
    date_hierarchy = "date_debut"
    autocomplete_fields = ("institution",)


@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "apprenant", "institution", "annee_scolaire", "classe", "statut", "statut_paiement")
    list_filter = ("statut", "statut_paiement", "institution", "annee_scolaire")
    search_fields = (
        "apprenant__email", "apprenant__nom", "apprenant__prenom",
        "institution__nom", "annee_scolaire__annee_format_classique", "classe__nom"
    )
    autocomplete_fields = ("apprenant", "institution", "annee_scolaire", "classe")
