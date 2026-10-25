# users/security.py
"""
Helpers de sécurité transverses (mots de passe).

Les règles sont PARAMÉTRABLES via Paramètres → Sécurité
(`securite_mdp_longueur_min`, `securite_mdp_complexite`),
avec priorité établissement > global (parametres.services.effective).
"""
import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


def validate_password_strength(password: str, user=None, institution=None) -> str:
    """
    Applique les règles paramétrables (longueur minimale, complexité) PUIS les
    validateurs Django (mot de passe commun, entièrement numérique, similarité
    avec l'utilisateur). Lève une ValidationError DRF si l'une échoue.
    """
    from parametres.services import securite_mdp_longueur_min, securite_mdp_complexite

    if institution is None:
        institution = getattr(user, "institution", None)

    pwd = password or ""
    erreurs: list[str] = []

    mini = securite_mdp_longueur_min(institution)
    if len(pwd) < mini:
        erreurs.append(f"Le mot de passe doit contenir au moins {mini} caractères.")

    if pwd and securite_mdp_complexite(institution):
        manques = []
        if not re.search(r"[A-Z]", pwd):
            manques.append("une majuscule")
        if not re.search(r"[a-z]", pwd):
            manques.append("une minuscule")
        if not re.search(r"\d", pwd):
            manques.append("un chiffre")
        if not re.search(r"[^A-Za-z0-9]", pwd):
            manques.append("un caractère spécial")
        if manques:
            erreurs.append("Le mot de passe doit contenir " + ", ".join(manques) + ".")

    if erreurs:
        raise serializers.ValidationError(erreurs)

    try:
        validate_password(pwd, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return password
