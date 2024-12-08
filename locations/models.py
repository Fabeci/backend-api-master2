from django.db import models


class Pays(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)

    def __str__(self):
        return self.nom


class Ville(models.Model):
    nom = models.CharField(max_length=100)
    pays = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name='villes')

    def __str__(self):
        return f"{self.nom}, {self.pays.nom}"


class Quartier(models.Model):
    nom = models.CharField(max_length=100)
    ville = models.ForeignKey(Ville, on_delete=models.CASCADE, related_name='quartiers')

    def __str__(self):
        return f"{self.nom}, {self.ville.nom}"
