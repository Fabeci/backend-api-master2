# users/import_users_views.py
# =============================================================================
#   POST /api/v1/utilisateurs/importer/analyser/
#   POST /api/v1/utilisateurs/importer/
# Import de formateurs et de responsables académiques depuis un document.
# =============================================================================

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission

from academics.models import AnneeScolaire, Departement, Institution
from courses.views import api_error, api_success
from users import import_users
from users.models import Formateur, ResponsableAcademique, User
from users.serializers import (
    FormateurCrudSerializer,
    ResponsableAcademiqueCrudSerializer,
)

logger = logging.getLogger(__name__)

MAX_SIZE = 10 * 1024 * 1024
ROLE_FORMATEUR = import_users.ROLE_FORMATEUR
ROLE_RESPONSABLE = import_users.ROLE_RESPONSABLE


def _role_name(request):
    role = getattr(request.user, "role", None)
    raw = getattr(role, "name", None) if role else None
    if not raw:
        return None
    key = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in ("responsable", "responsableacademique", "responsableacad"):
        return "Responsable"
    return raw


def _check_access(request):
    if request.user.is_superuser:
        return None
    if _role_name(request) in ("Admin", "Responsable"):
        return None
    return "Action réservée à l'administration."


def _check_file(request):
    f = request.FILES.get("file")
    if not f:
        return None, "Aucun fichier fourni."
    if f.size > MAX_SIZE:
        return None, "Fichier trop volumineux (max 10 Mo)."
    name = (f.name or "").lower()
    if not name.endswith(import_users.SUPPORTED):
        return None, "Format non pris en charge : CSV, Excel, Word, PDF ou TXT."
    return f, None


def _context(request):
    """MONO-ÉTABLISSEMENT : institution/année de référence, non négociables."""
    from core.tenant import default_institution, default_annee_scolaire
    institution = default_institution()
    annee = default_annee_scolaire()
    if not institution or not annee:
        return None, None, "Institution ou année scolaire par défaut introuvable."
    return institution, annee, None


def _split_name(nom: str, prenom: str):
    nom = (nom or "").strip()
    prenom = (prenom or "").strip()
    if not prenom and len(nom.split()) >= 2:
        parts = nom.split()
        prenom, nom = parts[0], " ".join(parts[1:])
    return nom[:30], prenom[:30]


def _departements(institution):
    out = {}
    for d in Departement.objects.filter(institution=institution):
        out[import_users._norm(d.nom)] = d
    return out


def _resolve(rows, institution, actor_role):
    existing = {e.strip().lower() for e in User.objects.values_list("email", flat=True) if e}
    deps = _departements(institution)

    out = []
    for i, row in enumerate(rows, start=1):
        email = (row.get("email") or "").strip().lower()
        nom, prenom = _split_name(row.get("nom") or "", row.get("prenom") or "")
        role = row.get("role") or ROLE_FORMATEUR
        dep_name = (row.get("departement") or "").strip()
        dep = deps.get(import_users._norm(dep_name)) if dep_name else None

        if not email or not nom or not prenom:
            statut, message = "invalide", "Email, nom et prénom sont obligatoires."
        else:
            try:
                validate_email(email)
            except DjangoValidationError:
                statut, message = "invalide", "Adresse email invalide."
            else:
                if role not in import_users.ROLES_VALIDES:
                    statut, message = "invalide", "Rôle invalide (Formateur ou Responsable)."
                elif email in existing:
                    statut, message = "existe", "Un compte avec cet email existe déjà."
                elif role == ROLE_RESPONSABLE and actor_role == "Responsable":
                    statut, message = "role_interdit", "Seul un administrateur peut créer un responsable."
                else:
                    statut, message = "ok", "Compte à créer."

        if dep_name and not dep and statut not in ("invalide", "existe"):
            message += f" Département « {dep_name} » introuvable (laissé vide)."

        out.append({
            "ligne": i,
            "nom": f"{prenom} {nom}".strip() or row.get("raw") or email,
            "nom_famille": nom,
            "prenom": prenom,
            "email": email,
            "role": role,
            "telephone": row.get("telephone") or "",
            "departement": dep.nom if dep else (dep_name or ""),
            "departement_id": dep.pk if dep else None,
            "password_fourni": bool(row.get("password")),
            "statut": statut,
            "message": message,
        })
    return out


def _stats(rows):
    from collections import Counter
    c = Counter(r["statut"] for r in rows)
    return {
        "total": len(rows),
        "ok": c.get("ok", 0),
        "existe": c.get("existe", 0),
        "invalide": c.get("invalide", 0),
        "role_interdit": c.get("role_interdit", 0),
    }


class UtilisateurImportAnalyseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        err = _check_access(request)
        if err:
            return api_error(err, http_status=status.HTTP_403_FORBIDDEN)

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        institution, annee, err = _context(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        role_defaut = request.data.get("role") or ROLE_FORMATEUR
        if role_defaut not in import_users.ROLES_VALIDES:
            return api_error("Rôle par défaut invalide.", http_status=status.HTTP_400_BAD_REQUEST)

        try:
            res = import_users.extract_users(f.name, f.read(), role_defaut)
        except Exception as exc:
            logger.exception("Analyse utilisateurs échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        rows = _resolve(res.get("rows") or [], institution, _role_name(request))
        st = _stats(rows)

        return api_success(
            f"{st['ok']} compte(s) à créer sur {st['total']} ligne(s).",
            {
                "institution": {"id": institution.id, "nom": institution.nom},
                "annee_scolaire": {"id": annee.id, "libelle": getattr(annee, "annee_format_classique", str(annee))},
                "stats": st,
                "rows": rows,
                "warnings": res.get("warnings") or [],
            },
            status.HTTP_200_OK,
        )


class UtilisateurImportCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        err = _check_access(request)
        if err:
            return api_error(err, http_status=status.HTTP_403_FORBIDDEN)

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        institution, annee, err = _context(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        role_defaut = request.data.get("role") or ROLE_FORMATEUR
        if role_defaut not in import_users.ROLES_VALIDES:
            return api_error("Rôle par défaut invalide.", http_status=status.HTTP_400_BAD_REQUEST)

        try:
            res = import_users.extract_users(f.name, f.read(), role_defaut)
        except Exception as exc:
            logger.exception("Analyse utilisateurs échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        rows = _resolve(res.get("rows") or [], institution, _role_name(request))

        created = 0
        accounts = []
        errors = []

        for r in rows:
            if r["statut"] != "ok":
                continue

            password = import_users.temp_password()
            common = {
                "email": r["email"],
                "nom": r["nom_famille"],
                "prenom": r["prenom"],
                "telephone": r["telephone"],
                "password": password,
                "is_active": True,
                "annee_scolaire_active_id": annee.id,
            }

            try:
                if r["role"] == ROLE_RESPONSABLE:
                    data = {**common, "institution_id": institution.id}
                    if r.get("departement_id"):
                        data["departement_id"] = r["departement_id"]
                    serializer = ResponsableAcademiqueCrudSerializer(data=data)
                else:
                    data = {**common, "institution_ids": [institution.id]}
                    serializer = FormateurCrudSerializer(data=data)

                serializer.is_valid(raise_exception=True)
                user = serializer.save()

                # Le FK `institution` de base n'est pas exposé par le serializer Formateur.
                if r["role"] == ROLE_FORMATEUR:
                    Formateur.objects.filter(pk=user.pk).update(
                        institution=institution, annee_scolaire_active=annee
                    )
                    if hasattr(user, "institutions"):
                        user.institutions.add(institution)

                created += 1
                accounts.append({
                    "email": r["email"],
                    "role": r["role"],
                    "password": password,
                })
            except ValidationError as exc:
                errors.append({"ligne": r["ligne"], "email": r["email"], "message": exc.detail})
            except Exception as exc:
                logger.exception("Création utilisateur échouée (%s)", r["email"])
                errors.append({"ligne": r["ligne"], "email": r["email"], "message": str(exc)})

        return api_success(
            f"{created} compte(s) créé(s)" + (f", {len(errors)} erreur(s)." if errors else "."),
            {
                "created": created,
                "accounts": accounts,
                "errors": errors,
                "stats": _stats(rows),
                "warnings": res.get("warnings") or [],
            },
            status.HTTP_201_CREATED,
        )
