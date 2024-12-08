from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from locations.models import Pays
from django.utils.timezone import now
import uuid


# Create your models here.

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('L\'email est requis')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Crée et retourne un super administrateur.
        """
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_super_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_super_admin') is not True:
            raise ValueError('Superuser doit avoir is_super_admin=True.')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser doit avoir is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser doit avoir is_superuser=True.')

        return self.create_user(email, password, **extra_fields)
    
    # def create_apprenant(self, email, password=None, **extra_fields):
    #     """
    #     Crée un utilisateur avec le rôle d'apprenant.
    #     """
    #     extra_fields.setdefault('is_apprenant', True)
    #     return self.create_user(email, password, **extra_fields)

    def create_formateur(self, email, password=None, **extra_fields):
        """
        Crée un utilisateur avec le rôle de formateur.
        """
        extra_fields.setdefault('is_formateur', True)
        return self.create_user(email, password, **extra_fields)

    def create_responsable_academique(self, email, password=None, **extra_fields):
        """
        Crée un utilisateur avec le rôle de responsable académique.
        """
        extra_fields.setdefault('is_responsable_academique', True)
        return self.create_user(email, password, **extra_fields)

    def create_parent(self, email, password=None, **extra_fields):
        """
        Crée un utilisateur avec le rôle de parent.
        """
        extra_fields.setdefault('is_parent', True)
        return self.create_user(email, password, **extra_fields)
    
    
class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    nom = models.CharField(max_length=30)
    prenom = models.CharField(max_length=30)
    telephone = models.CharField(max_length=15, blank=True, null=True)
    pays_residence = models.ForeignKey(Pays, on_delete=models.CASCADE, related_name='users', null=True)
    is_active = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=now)
    is_staff = models.BooleanField(default=False)  # Obligatoire pour l'admin
    is_superuser = models.BooleanField(default=False)
    activation_token = models.CharField(max_length=255, editable=False, blank=True)
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_groups',  # Changez pour un related_name unique
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_permissions',  # Changez pour un related_name unique
        blank=True
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom']

    objects = CustomUserManager()
    
    

    def __str__(self):
        return self.email


class Admin(User):
    date_entree = models.DateField(null=True)
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='administrateurs', null=True)

    class Meta:
        pass


class SuperAdmin(User):
    pass


class Parent(User):
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='parents', null=True, blank=True)


class Apprenant(User):
    matricule = models.CharField(max_length=20, unique=True, null=True)
    date_naissance = models.DateField(null=True)
    groupe = models.ForeignKey('academics.Groupe', on_delete=models.CASCADE, related_name='groupe_apprenant', null=True)
    tuteur = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='children', null=True)
    classe = models.ForeignKey('academics.Classe', on_delete=models.CASCADE, related_name='classe_apprenant', null=True)
    
    class Meta:
        pass


class Formateur(User):
    institutions = models.ManyToManyField('academics.Institution', related_name="formateurs_users", null=True, blank=True)
    specialites = models.ManyToManyField('academics.Specialite', related_name="formateurs", null=True, blank=True)
    groupes = models.ManyToManyField('academics.Groupe', related_name="formateurs", null=True, blank=True)

    def __str__(self):
        return self.nom
    class Meta:
        pass


class ResponsableAcademique(User):
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='responsables_academiques', null=True)
    departement = models.ForeignKey('academics.Departement', on_delete=models.CASCADE, related_name='responsables_departement', null=True, blank=True)

    def __str__(self):
        return self.nom

    class Meta:
        pass

