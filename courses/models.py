from django.db import models

from academics.models import Groupe, Matiere


class Cours(models.Model):
    groupe = models.ForeignKey(Groupe, on_delete=models.CASCADE)
    enseignant = models.ForeignKey('users.Formateur', on_delete=models.CASCADE)
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE)
    date = models.DateField(null=True, blank=True)
    heure = models.TimeField(null=True, blank=True)

    def __str__(self):
        return f"Cours de {self.matiere} par {self.enseignant} dans {self.groupe}"


class Sequence(models.Model):
    titre = models.CharField(max_length=255)
    module = models.ForeignKey('Module', on_delete=models.CASCADE, related_name='sequences')

    def __str__(self):
        return self.titre


class Module(models.Model):
    titre = models.CharField(max_length=255)
    description = models.TextField()
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='modules')

    def __str__(self):
        return self.titre


class InscriptionCours(models.Model):
    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='inscriptions')
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='inscriptions')
    date_inscription = models.DateField(auto_now_add=True)
    statut = models.CharField(max_length=50)  # Par exemple : 'en cours', 'complété', etc.

    def __str__(self):
        return f"{self.apprenant.nom} inscrit à {self.cours.nom}"


class Suivi(models.Model):
    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='suivis')
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='suivis')
    date_debut = models.DateField(auto_now_add=True)
    progression = models.FloatField(default=0.0)  # Progrès en pourcentage (0.0 à 100.0)
    note = models.FloatField(null=True, blank=True)  # Note de l'apprenant, si applicable
    commentaires = models.TextField(null=True, blank=True)  # Commentaires ou retours sur le suivi

    def __str__(self):
        return f"Suivi de {self.apprenant.nom} pour {self.cours.nom}"

    def save(self, *args, **kwargs):
        # Vérification de l'inscription avant de sauvegarder
        if not InscriptionCours.objects.filter(apprenant=self.apprenant, cours=self.cours).exists():
            raise ValueError(f"L'apprenant {self.apprenant.nom} n'est pas inscrit à ce cours.")
        super().save(*args, **kwargs)


class Session(models.Model):
    titre = models.CharField(max_length=255)
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    cours = models.ForeignKey('Cours', on_delete=models.CASCADE,
                              related_name='sessions')  # Supposons que vous ayez déjà un modèle Cours
    formateur = models.ForeignKey('users.Formateur', on_delete=models.CASCADE,
                                  related_name='sessions')  # Formateur pour la session

    def __str__(self):
        return f"{self.titre} ({self.date_debut} - {self.date_fin})"


class Participation(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='participations')
    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE,
                                  related_name='participations')  # On suppose que User représente les apprenants
    date_participation = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            'session', 'apprenant')  # Assurer qu'un apprenant ne peut pas participer à la même session plusieurs fois

    def __str__(self):
        return f"{self.apprenant.username} participe à {self.session.titre}"
