# users/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils.timezone import now, timedelta
from locations.models import Pays
import uuid
import random

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError("L'email est requis")
        email = self.normalize_email(email)
        if self.model.objects.filter(email=email).exists():
            raise ValueError("Un utilisateur avec cet email existe déjà.")

        # Par défaut: inactif jusqu'à vérification
        extra_fields.setdefault("is_active", False)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(email=email, **extra_fields)
        if password:
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
        # On n’impose pas de rôle FK ici
        user = self.create_user(email, password, **extra_fields)
        return user


class UserRole(models.Model):
    name = models.CharField(max_length=50, unique=True)  # "Admin", "Formateur", etc.
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
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    # laissé pour compat mais plus nécessaire pour l’activation par code
    activation_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, blank=True)
    role = models.ForeignKey(UserRole, on_delete=models.SET_NULL, null=True, blank=True)

    # renommer les related_name pour éviter tout conflit avec auth.User
    groups = models.ManyToManyField('auth.Group', related_name='somapro_user_groups', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='somapro_user_permissions', blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom']
    objects = CustomUserManager()

    def __str__(self):
        return self.email


# === Multi-table inheritance (gardé) ===
class Admin(User):
    date_entree = models.DateField(null=True, blank=True, auto_now_add=True)
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='administrateurs', null=True, blank=True)
    def __str__(self):  # corrige: ne pas référencer self.user
        return f"Admin: {self.nom} {self.prenom}"


class Parent(User):
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='parents', null=True, blank=True)
    def __str__(self):
        return f"Parent: {self.nom} {self.prenom}"


class Apprenant(User):
    matricule = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    groupe = models.ForeignKey('academics.Groupe', on_delete=models.SET_NULL, related_name='groupe_apprenant', null=True, blank=True)
    tuteur = models.ForeignKey(Parent, on_delete=models.SET_NULL, related_name='children', null=True, blank=True)
    def __str__(self):
        return f"Apprenant: {self.nom} {self.prenom}"


class Formateur(User):
    institutions = models.ManyToManyField('academics.Institution', related_name="formateurs", blank=True)
    specialites = models.ManyToManyField('academics.Specialite', related_name="formateurs", blank=True)
    groupes = models.ManyToManyField('academics.Groupe', related_name="formateurs", blank=True)
    def __str__(self):
        return f"Formateur: {self.nom} {self.prenom}"


class ResponsableAcademique(User):
    institution = models.ForeignKey('academics.Institution', on_delete=models.CASCADE, related_name='responsables_academiques', null=True, blank=True)
    departement = models.ForeignKey('academics.Departement', on_delete=models.CASCADE, related_name='responsables_departement', null=True, blank=True)
    def __str__(self):
        return f"{self.nom} {self.prenom}"


class SuperAdmin(User):
    pass


# === Vérification par code à 6 chiffres ===
class VerificationCode(models.Model):
    PURPOSE_CHOICES = (
        ('activation', 'Activation'),
        ('password_reset', 'Password Reset'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_codes')
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='activation')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    @staticmethod
    def generate_code() -> str:
        return f"{random.randint(0, 999999):06d}"

    @classmethod
    def create_activation_code(cls, user, ttl_minutes: int = 15):
        code = cls.generate_code()
        obj = cls.objects.create(
            user=user,
            code=code,
            purpose='activation',
            expires_at=now() + timedelta(minutes=ttl_minutes),
        )
        return obj

    def is_valid(self) -> bool:
        return (not self.is_used) and (self.expires_at >= now())

    def __str__(self):
        return f"{self.user.email} - {self.purpose} - {self.code}"
