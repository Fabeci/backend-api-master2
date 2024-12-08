# app_name/signals.py

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from django.db.models.signals import post_save
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.conf import settings


@receiver(post_migrate)
def create_super_admin_group(sender, **kwargs):
    super_admin_group, created = Group.objects.get_or_create(name='SuperAdmin')

    # Assigner toutes les permissions si le groupe est nouveau
    if created:
        for content_type in ContentType.objects.all():
            permissions = Permission.objects.filter(content_type=content_type)
            super_admin_group.permissions.add(*permissions)


# Fonction pour créer un utilisateur SuperAdmin et l'ajouter au groupe
def create_super_admin_user(username, password):
    User = get_user_model()
    user = User.objects.create_user(username=username, password=password)
    super_admin_group = Group.objects.get(name="SuperAdmin")
    user.groups.add(super_admin_group)
    user.is_superuser = True  # Pour les privilèges de super utilisateur
    user.is_staff = True  # Pour l'accès à l'administration
    user.save()
    return user


@receiver(post_save, sender=get_user_model())
def send_verification_email(sender, instance, created, **kwargs):
    """
    Envoie un e-mail de vérification après la création d'un utilisateur.
    """
    # if created and not instance.is_active:  # Si l'utilisateur vient juste d'être créé et n'est pas encore activé
    #     uid = urlsafe_base64_encode(str(instance.pk).encode())
    #     token = default_token_generator.make_token(instance)

    #     activation_link = reverse('activate_user', kwargs={'uidb64': uid, 'token': token})
    #     activation_url = f"{settings.FRONTEND_URL}{activation_link}"

    #     send_mail(
    #         'Activer votre compte',
    #         f'Cliquez sur ce lien pour activer votre compte : {activation_url}',
    #         settings.EMAIL_HOST_USER,
    #         [instance.email],
    #         fail_silently=False,
    #     )
    pass
