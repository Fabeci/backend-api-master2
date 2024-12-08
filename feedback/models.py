from django.db import models
from django.utils import timezone

from courses.models import Session, Cours
from evaluations.models import Evaluation


# Create your models here.


class Feedback(models.Model):
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='feedbacks', null=True, blank=True)
    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name='feedbacks', null=True, blank=True)
    auteur = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='feedbacks', null=True, blank=True)
    destinataires = models.ManyToManyField('users.User', related_name='feedbacks_recus', blank=True)
    contenu = models.TextField()
    note = models.FloatField(null=True, blank=True)  # Note entre 1 et 5, par exemple
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback de {self.auteur.username} pour {self.cours.nom}"


class Progression(models.Model):
    apprenant = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='progressions')  # Référence à l'apprenant
    cours = models.ForeignKey('courses.Cours', on_delete=models.CASCADE, related_name='progressions')  # Référence à la session
    pourcentage = models.FloatField()  # Pourcentage de progression (0-100)
    date_mise_a_jour = models.DateTimeField(auto_now=True)  # Date de la dernière mise à jour

    def __str__(self):
        return f"{self.apprenant.username} - {self.cours.nom} : {self.pourcentage}%"


class HistoriqueProgression(models.Model):
    progression = models.ForeignKey(Progression, on_delete=models.CASCADE, related_name='historique')
    date_changement = models.DateTimeField(auto_now_add=True)  # Date à laquelle le changement a été enregistré
    ancienne_progression = models.FloatField()  # Ancien pourcentage de progression
    nouvelle_progression = models.FloatField()  # Nouveau pourcentage de progression

    def __str__(self):
        return f"Historique de {self.progression.apprenant.username} pour {self.progression.session.titre} : {self.ancienne_progression}% -> {self.nouvelle_progression}%"


class PlanAction(models.Model):
    progression = models.ForeignKey(Progression, on_delete=models.CASCADE, related_name='plans_actions')
    description = models.TextField()  # Description de l'action à entreprendre
    date_creation = models.DateTimeField(auto_now_add=True)  # Date à laquelle le plan d'action a été créé
    date_limite = models.DateTimeField(null=True, blank=True)  # Date limite pour l'action
    complet = models.BooleanField(default=False)  # Indique si l'action a été complétée

    def __str__(self):
        return f"Plan d'action pour {self.progression.apprenant.username} - {self.description}"
