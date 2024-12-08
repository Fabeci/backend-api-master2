from django.db import models
from courses.models import Sequence, Cours
# Create your models here.

class Quiz(models.Model):
    titre = models.CharField(max_length=255)
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name='quizz')
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Quiz: {self.titre} (Sequence: {self.sequence.titre})"


class Question(models.Model):
    TYPE_CHOICES = [
        ('texte', 'Texte à rédiger'),
        ('choix_unique', 'Choix unique'),
        ('choix_multiple', 'Choix multiple'),
    ]
    texte = models.TextField()
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions_quizz', null=True, blank=True)
    evaluation = models.ForeignKey(
        'Evaluation', on_delete=models.CASCADE, related_name='questions_evaluation', null=True, blank=True
    )
    type_question = models.CharField(max_length=20, choices=TYPE_CHOICES)

    def __str__(self):
        return f"Question: {self.texte[:50]}..."


class Reponse(models.Model):
    texte = models.TextField()
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='reponses')
    est_correcte = models.BooleanField(default=False)
    est_choix_unique = models.BooleanField(default=False)
    est_choix_multiple = models.BooleanField(default=False)

def __str__(self):
        return f"Réponse: {self.texte[:50]}..."


class Evaluation(models.Model):
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name='evaluations')
    bareme = models.FloatField()
    date_passage = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Évaluation de {self.cours} pour le cours {self.cours} - Note: {self.note}"


class ApprenantEvaluation(models.Model):
    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='apprenant_evaluations')
    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name='apprenant_evaluations')
    note = models.FloatField()  # Note obtenue par l'apprenant pour cette évaluation
    date_passage = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('apprenant', 'evaluation')  # Assure qu'un apprenant ne peut passer qu'une fois une évaluation

    def __str__(self):
        return f"{self.apprenant} - {self.evaluation} - Note: {self.note}"


class Solution(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='questions')

    def __str__(self):
        return f"Solution pour {self.question.texte}"