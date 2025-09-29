from django.db import models
from locations.models import Pays
# from users.models import ResponsableAcademique, Apprenant, Formateur


# Create your models here.
class Institution(models.Model):
    nom = models.CharField(max_length=200)
    pays = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name='etablissements')
    formateurs = models.ManyToManyField('users.Formateur', related_name='institutions_academics')
    adresse = models.CharField(max_length=255, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now=True)
    telephone_1 = models.CharField(max_length=15, null=True, blank=True)
    telephone_2 = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    logo = models.ImageField(upload_to='institution_logos/', null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    statut = models.CharField(max_length=50, choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active')
    type_institution = models.CharField(max_length=100, null=True, blank=True)
    nombre_etudiants = models.IntegerField(null=True, blank=True)
    site_web = models.URLField(null=True, blank=True)
    accreditations = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return self.nom


class Departement(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='departements')
    responsable_academique = models.ForeignKey(
        'users.ResponsableAcademique', 
        on_delete=models.CASCADE,
        related_name='departements'
        )

    def __str__(self):
        return self.nom


class DomaineEtude(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.nom


class Filiere(models.Model):
    nom = models.CharField(max_length=255)
    domaine_etude = models.ForeignKey(DomaineEtude, on_delete=models.CASCADE, related_name='filieres')
    description = models.TextField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now=True)
    statut = models.CharField(max_length=50, choices=[('actif', 'Actif'), ('en_pause', 'En Pause'), ('archive', 'Archivée')], default='actif')
    
    def __str__(self):
        return self.nom

class Matiere(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.nom


class Groupe(models.Model):
    nom = models.CharField(max_length=100)
    enseignants = models.ManyToManyField('users.Formateur', related_name='academics_groupes')
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.nom


class Classe(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now=True)
    filieres = models.ManyToManyField(Filiere, related_name='classes')
    matieres = models.ManyToManyField(Matiere, related_name='classes')
    groupes = models.ForeignKey(Groupe, on_delete=models.CASCADE, related_name='classe', null=True, blank=True)
    apprenants = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='apprenants_classe_institution', null=True, blank=True)

    def __str__(self):
        return self.nom


class Specialite(models.Model):
    nom = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nom


class AnneeScolaire(models.Model):
    annee_format_classique = models.CharField(
        max_length=9,
        null=True,
        blank=True,
        help_text="Format classique de l'année (ex: 2023-2024)"
    )
    date_debut = models.DateField(
        null=True,
        blank=True,
        help_text="Date de début de l'année scolaire si période spécifique"
    )
    date_fin = models.DateField(
        null=True,
        blank=True,
        help_text="Date de fin de l'année scolaire si période spécifique"
    )
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        if self.annee_format_classique:
            return f"Année scolaire {self.annee_format_classique}"
        return f"Année scolaire du {self.date_debut} au {self.date_fin}"

    class Meta:
        ordering = ["-date_debut"]
        verbose_name = "Année scolaire"
        verbose_name_plural = "Années scolaires"


class Inscription(models.Model):
    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE)
    statut = models.CharField(max_length=20, choices=[
        ('actif', 'Actif'),
        ('diplome', 'Diplômé'),
        ('retire', 'Retiré'),
    ])
    statut_paiement = models.CharField(max_length=20, choices=[
    ('en_attente', 'En attente'),
    ('payé', 'Payé'),
    ('annulé', 'Annulé'),
    ], default='en_attente')

    def __str__(self):
        return f"{self.apprenant} - {self.institution} ({self.annee_scolaire})"



