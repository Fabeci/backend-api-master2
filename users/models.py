from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from locations.models import Pays
from django.utils.timezone import now
import uuid
from django.core.mail import send_mail
from django.conf import settings



# Create your models here.

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError("L'email est requis")
        email = self.normalize_email(email)
        
        if self.model.objects.filter(email=email).exists():
            raise ValueError("Un utilisateur avec cet email existe déjà.")
        
        extra_fields.setdefault("is_active", True)
        
        user = self.model(email=email, **extra_fields)
        user.set_password(password)

        if role:
            try:
                user_role = UserRole.objects.get(name=role)
                user.role = user_role
            except UserRole.DoesNotExist:
                raise ValueError(f"Le rôle '{role}' n'existe pas.")
        
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(email, password, role="Super Admin", **extra_fields)

    
    
class UserRole(models.Model):
    name = models.CharField(max_length=50, unique=True)  # Exemple : "Admin", "Formateur", etc.
    
    def __str__(self):
        return self.name
       
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
    activation_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, blank=True)    
    role = models.ForeignKey(UserRole, on_delete=models.SET_NULL, null=True, blank=True)
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
    date_entree = models.DateField(null=True, auto_now=True)
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='administrateurs', null=True)

    def __str__(self):
        return f"Admin: {self.user.nom} {self.user.prenom}"

class Parent(User):
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='parents', null=True, blank=True)

    def __str__(self):
        return f"Parent: {self.user.nom} {self.user.prenom}"

class Apprenant(User):
    matricule = models.CharField(max_length=20, unique=True, null=True)
    date_naissance = models.DateField(null=True)
    groupe = models.ForeignKey('academics.Groupe', on_delete=models.CASCADE, related_name='groupe_apprenant', null=True)
    tuteur = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name='children', null=True)
    classe = models.ForeignKey('academics.Classe', on_delete=models.CASCADE, related_name='classe_apprenant', null=True)

    def __str__(self):
        return f"Apprenant: {self.user.nom} {self.user.prenom}"

class Formateur(User):
    institutions = models.ManyToManyField('academics.Institution', related_name="formateurs_users", blank=True)
    specialites = models.ManyToManyField('academics.Specialite', related_name="formateurs", blank=True)
    groupes = models.ManyToManyField('academics.Groupe', related_name="formateurs", blank=True)

    def __str__(self):
        return f"Formateur: {self.user.nom} {self.user.prenom}"

class ResponsableAcademique(User):
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='responsables_academiques', null=True)
    departement = models.ForeignKey('academics.Departement', on_delete=models.CASCADE, related_name='responsables_departement', null=True, blank=True)

    def __str__(self):
        return f"{self.user.nom} {self.user.prenom}"
    
class SuperAdmin(User):
    pass

