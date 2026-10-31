from django.db import models


class Pays(models.Model):
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=3, unique=True)
    # Code ISO 3166-1 alpha-2 (ex. SN pour le Sénégal), utilisé par le sélecteur ville.
    iso2 = models.CharField(max_length=2, blank=True, null=True)

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
