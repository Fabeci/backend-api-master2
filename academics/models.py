# -*- coding: utf-8 -*-
from django.db import models
from django.core.exceptions import ValidationError
from locations.models import Pays


# ============================================================================
# INSTITUTION
# ============================================================================

class Institution(models.Model):
    nom = models.CharField(max_length=200)
    pays = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name="etablissements")
    adresse = models.CharField(max_length=255, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    telephone_1 = models.CharField(max_length=15, null=True, blank=True)
    telephone_2 = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    logo = models.ImageField(upload_to="institution_logos/", null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    statut = models.CharField(
        max_length=50,
        choices=[("active", "Active"), ("inactive", "Inactive")],
        default="active",
    )
    type_institution = models.CharField(max_length=100, null=True, blank=True)
    nombre_etudiants = models.IntegerField(null=True, blank=True)
    site_web = models.URLField(null=True, blank=True)
    accreditations = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.nom


# ============================================================================
# OBJETS "VIVANTS" (par institution + année scolaire)
# ============================================================================

class AnneeScolaire(models.Model):
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="annees_scolaires",
        related_query_name="annee_scolaire",
        null=True,
        blank=True,
    )
    annee_format_classique = models.CharField(
        max_length=9,
        null=True,
        blank=True,
        help_text="Format classique (ex: 2025-2026)",
    )
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    est_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Année scolaire"
        verbose_name_plural = "Années scolaires"
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "annee_format_classique"],
                name="uniq_annee_scolaire_par_institution",
            )
        ]

    def save(self, *args, **kwargs):
        # Une seule année active par institution
        if self.est_active:
            AnneeScolaire.objects.filter(
                institution=self.institution, est_active=True
            ).exclude(pk=self.pk).update(est_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.annee_format_classique:
            return f"Année scolaire {self.annee_format_classique}"
        return f"Année scolaire du {self.date_debut} au {self.date_fin}"


class Classe(models.Model):
    """
    Classe = cohorte pour une année scolaire (vivant).
    Ex: "L1 Informatique 2025-2026"
    """
    nom = models.CharField(max_length=255)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="classes",
        null=True,
        blank=True,
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="classes",
        null=True,
        blank=True,
    )
    description = models.TextField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    # Programmes / référentiels (institution-only)
    filieres = models.ManyToManyField("academics.Filiere", related_name="classes", blank=True)
    matieres = models.ManyToManyField("academics.Matiere", related_name="classes", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["nom", "institution", "annee_scolaire"],
                name="uniq_classe_par_inst_annee",
            )
        ]

    def clean(self):
        # Cohérence institution/année
        if self.annee_scolaire and self.annee_scolaire.institution_id != self.institution_id:
            raise ValidationError("L'année scolaire ne correspond pas à l'institution de la classe.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        nom = self.nom or "Classe"
        inst = getattr(self.institution, "nom", None) or "Institution ?"
        annee = str(self.annee_scolaire) if self.annee_scolaire else "Année ?"
        return f"{nom} - {inst} ({annee})"


class Groupe(models.Model):
    """
    Groupe = répartition annuelle d'une classe (vivant).
    Ex: "Groupe A" dans "L1 Info 2025-2026"
    """
    nom = models.CharField(max_length=100)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="groupes",
        null=True,
        blank=True,
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="groupes",
        help_text="Année scolaire du groupe",
        null=True,
        blank=True,
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.CASCADE,
        related_name="groupes",
        null=True,
        blank=True,
    )
    enseignants = models.ManyToManyField(
        "users.Formateur",
        related_name="academics_groupes",
        blank=True
    )
    description = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["nom", "institution", "annee_scolaire", "classe"],
                name="uniq_groupe_par_inst_annee_classe",
            )
        ]

    def clean(self):
        # Cohérence institution/année avec classe et année scolaire
        if self.classe:
            if self.classe.institution_id != self.institution_id:
                raise ValidationError("Le groupe et sa classe doivent appartenir à la même institution.")
            if self.classe.annee_scolaire_id != self.annee_scolaire_id:
                raise ValidationError("Le groupe et sa classe doivent appartenir à la même année scolaire.")
        if self.annee_scolaire and self.annee_scolaire.institution_id != self.institution_id:
            raise ValidationError("L'année scolaire du groupe ne correspond pas à son institution.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        nom_groupe = self.nom or "Groupe"
        nom_classe = getattr(self.classe, "nom", None) or "Classe ?"
        nom_annee = str(self.annee_scolaire) if self.annee_scolaire else "Année ?"
        return f"{nom_groupe} - {nom_classe} ({nom_annee})"


class Inscription(models.Model):
    apprenant = models.ForeignKey(
        "users.Apprenant",
        on_delete=models.CASCADE,
        related_name="inscriptions_scolaires",
        related_query_name="inscription_scolaire",
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="inscriptions",
        null=True,
        blank=True,
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="inscriptions",
        null=True,
        blank=True,
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.SET_NULL,
        related_name="inscriptions",
        null=True,
        blank=True,
    )

    statut = models.CharField(
        max_length=20,
        choices=[
            ("actif", "Actif"),
            ("diplome", "Diplômé"),
            ("retire", "Retiré"),
        ],
        default="actif",
    )
    statut_paiement = models.CharField(
        max_length=20,
        choices=[
            ("en_attente", "En attente"),
            ("paye", "Payé"),
            ("annule", "Annulé"),
        ],
        default="en_attente",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["apprenant", "institution", "annee_scolaire"],
                name="uniq_inscription_inst_annee",
            )
        ]

    def clean(self):
        # Cohérence inscription vs institution/année
        if self.annee_scolaire and self.annee_scolaire.institution_id != self.institution_id:
            raise ValidationError("L'année scolaire de l'inscription ne correspond pas à l'institution.")

        if self.classe:
            if self.classe.institution_id != self.institution_id:
                raise ValidationError("La classe choisie n'appartient pas à la même institution que l'inscription.")
            if self.classe.annee_scolaire_id != self.annee_scolaire_id:
                raise ValidationError("La classe choisie n'appartient pas à la même année scolaire que l'inscription.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.apprenant} - {self.classe} - {self.annee_scolaire}"


# ============================================================================
# RÉFÉRENTIELS "STABLES" (institution-only)
# ============================================================================

class Departement(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="departements",
        null=True,
        blank=True,
    )
    responsable_academique = models.ForeignKey(
        "users.ResponsableAcademique",
        on_delete=models.CASCADE,
        related_name="departements",
    )
    est_actif = models.BooleanField(default=True)
    date_debut_validite = models.DateField(null=True, blank=True)
    date_fin_validite = models.DateField(null=True, blank=True)

    def clean(self):
        inst_user = getattr(self.responsable_academique, "institution", None)
        if inst_user and inst_user != self.institution:
            raise ValidationError(
                "Le responsable académique doit appartenir à la même institution que le département."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class DomaineEtude(models.Model):
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="domaines_etude",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    date_debut_validite = models.DateField(null=True, blank=True)
    date_fin_validite = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "nom"],
                name="uniq_domaine_etude_par_institution",
            )
        ]
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Filiere(models.Model):
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="filieres",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=255)
    domaine_etude = models.ForeignKey(
        DomaineEtude,
        on_delete=models.CASCADE,
        related_name="filieres"
    )
    description = models.TextField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=50,
        choices=[("actif", "Actif"), ("en_pause", "En pause"), ("archive", "Archivée")],
        default="actif",
    )
    est_actif = models.BooleanField(default=True)
    date_debut_validite = models.DateField(null=True, blank=True)
    date_fin_validite = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "nom"],
                name="uniq_filiere_par_institution",
            )
        ]
        ordering = ["nom"]

    def clean(self):
        if self.domaine_etude and self.domaine_etude.institution_id != self.institution_id:
            raise ValidationError("La filière et son domaine d'étude doivent appartenir à la même institution.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Matiere(models.Model):
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="matieres",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    date_debut_validite = models.DateField(null=True, blank=True)
    date_fin_validite = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "nom"],
                name="uniq_matiere_par_institution",
            )
        ]
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Specialite(models.Model):
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="specialites",
        related_query_name="specialite",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    est_actif = models.BooleanField(default=True)
    date_debut_validite = models.DateField(null=True, blank=True)
    date_fin_validite = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "nom"],
                name="uniq_specialite_par_institution",
            )
        ]
        ordering = ["nom"]

    def __str__(self):
        return self.nom
