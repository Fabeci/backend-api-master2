from django.db import models
from courses.models import Sequence


class Ressource(models.Model):
    titre = models.CharField(max_length=255)
    fichier = models.FileField(upload_to='ressources/')
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name='ressources')
    date_ajout = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titre


class RessourceSupplementaire(models.Model):
    titre = models.CharField(max_length=255)
    fichier = models.FileField(upload_to='ressources_supplementaires/')
    sequence = models.ForeignKey(
        Sequence, on_delete=models.CASCADE, related_name='ressources_supplementaires', null=True, blank=True
    )
    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='ressources_supplementaires')
    date_ajout = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.titre} pour {self.apprenant.nom}"


class PieceJointe(models.Model):
    fichier = models.FileField(upload_to='pieces_jointes/')
    ressource = models.ForeignKey(
        Ressource, on_delete=models.CASCADE, related_name='pieces_jointes', null=True, blank=True
    )
    ressource_supplementaire = models.ForeignKey(
        RessourceSupplementaire, on_delete=models.CASCADE, related_name='pieces_jointes', null=True, blank=True
    )

    def __str__(self):
        return f"Pièce jointe pour {self.ressource.titre}"


class RessourcePieceJointe(models.Model):
    ressource = models.ForeignKey(Ressource, on_delete=models.CASCADE, related_name='ressources_pieces_jointes')
    piece_jointe = models.ForeignKey(PieceJointe, on_delete=models.CASCADE, related_name='ressource_piece_jointe')

    def __str__(self):
        return f"{self.ressource.titre} - {self.piece_jointe.fichier.name}"


class RessourceSuppPieceJointe(models.Model):
    ressource = models.ForeignKey(RessourceSupplementaire, on_delete=models.CASCADE, related_name='ressources_supplementaires_pieces_jointes')
    piece_jointe = models.ForeignKey(PieceJointe, on_delete=models.CASCADE, related_name='ressource_supp_piece_jointe')

    def __str__(self):
        return f"{self.ressource.titre} - {self.piece_jointe.fichier.name}"

