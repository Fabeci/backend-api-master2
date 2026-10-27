# academics/import_inscriptions_etab.py
# =============================================================================
# Import d'INSCRIPTIONS à l'établissement courant pour l'année courante.
#
# - Apprenant existant (email/nom) → inscription à l'établissement ;
# - Apprenant inconnu avec email + nom → création du compte Apprenant
#   (mot de passe temporaire généré) puis inscription.
# =============================================================================

import logging
import secrets
import string

from django.db import transaction
from django.db.models import Q

from academics.models import Classe, Inscription
from courses import import_inscriptions
from users.models import Apprenant, UserRole

logger = logging.getLogger(__name__)


def _temp_password(n: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _split_name(nom: str, prenom: str):
    nom = (nom or "").strip()
    prenom = (prenom or "").strip()
    if not prenom and nom:
        parts = nom.split()
        if len(parts) >= 2:
            prenom, nom = parts[0], " ".join(parts[1:])
    return nom[:30], prenom[:30]


def _maps():
    by_email = {}
    by_name = {}
    for a in Apprenant.objects.all():
        if a.email:
            by_email[a.email.strip().lower()] = a
        parts = [import_inscriptions._norm(a.prenom or ""), import_inscriptions._norm(a.nom or "")]
        for n in {" ".join(p for p in parts if p), " ".join(p for p in reversed(parts) if p)}:
            if n:
                by_name.setdefault(n, []).append(a)
    return by_email, by_name


def _match(row, by_email, by_name):
    email = (row.get("email") or "").strip().lower()
    if email and email in by_email:
        return [by_email[email]]

    candidates = set()
    for raw in (
        row.get("raw") or "",
        f"{row.get('prenom') or ''} {row.get('nom') or ''}".strip(),
        f"{row.get('nom') or ''} {row.get('prenom') or ''}".strip(),
    ):
        n = import_inscriptions._norm(raw)
        if n and n in by_name:
            candidates.update(by_name[n])
    return list(candidates)


def resolve(rows, institution, annee) -> list[dict]:
    by_email, by_name = _maps()

    classes = {}
    for c in Classe.objects.filter(institution=institution).filter(
        Q(annee_scolaire=annee) | Q(annee_scolaire__isnull=True)
    ):
        classes[import_inscriptions._norm(c.nom)] = c

    registered = set(
        Inscription.objects.filter(institution=institution, annee_scolaire=annee)
        .values_list("apprenant_id", flat=True)
    )

    out = []
    for i, row in enumerate(rows, start=1):
        email = (row.get("email") or "").strip().lower()
        nom, prenom = _split_name(row.get("nom") or "", row.get("prenom") or "")
        classe_name = (row.get("classe") or "").strip()
        classe = classes.get(import_inscriptions._norm(classe_name)) if classe_name else None

        matches = _match(row, by_email, by_name)

        if len(matches) > 1:
            statut = "ambigu"
            message = "Plusieurs apprenants correspondent : précisez l'email."
            appr = None
        elif matches:
            appr = matches[0]
            if appr.pk in registered:
                statut = "deja_inscrit"
                message = "Déjà inscrit à l'établissement pour cette année."
            else:
                statut = "ok"
                message = "Inscription à créer."
        else:
            appr = None
            if email and (nom or prenom):
                statut = "nouveau"
                message = "Compte apprenant à créer + inscription."
            else:
                statut = "invalide"
                message = "Email et nom requis pour créer l'apprenant."

        if classe_name and not classe and statut != "invalide":
            message += f" Classe « {classe_name} » introuvable (laissée vide)."

        out.append({
            "ligne": i,
            "nom": f"{prenom} {nom}".strip() or row.get("raw") or email,
            "email": email,
            "nom_famille": nom,
            "prenom": prenom,
            "classe": classe.nom if classe else (classe_name or ""),
            "classe_id": classe.pk if classe else None,
            "apprenant_id": appr.pk if appr else None,
            "apprenant_nom": (
                f"{appr.prenom or ''} {appr.nom or ''}".strip() if appr else ""
            ),
            "statut": statut,
            "message": message,
            "candidats": (
                [
                    {
                        "id": a.pk,
                        "nom": f"{a.prenom or ''} {a.nom or ''}".strip(),
                        "email": a.email or "",
                    }
                    for a in matches
                ]
                if statut == "ambigu" else []
            ),
        })

    return out


def stats(rows) -> dict:
    from collections import Counter
    c = Counter(r["statut"] for r in rows)
    return {
        "total": len(rows),
        "ok": c.get("ok", 0),
        "nouveau": c.get("nouveau", 0),
        "deja_inscrit": c.get("deja_inscrit", 0),
        "ambigu": c.get("ambigu", 0),
        "invalide": c.get("invalide", 0),
    }


@transaction.atomic
def create(rows, institution, annee) -> dict:
    role = UserRole.objects.get_or_create(name="Apprenant")[0]

    created_inscriptions = 0
    created_accounts = []
    skipped = 0
    errors = []

    for r in rows:
        if r["statut"] not in ("nouveau", "ok"):
            skipped += 1
            if r["statut"] in ("ambigu", "invalide"):
                errors.append({
                    "ligne": r.get("ligne"),
                    "email": r.get("email") or "",
                    "nom": r.get("nom") or "",
                    "statut": r["statut"],
                    "message": r.get("message") or "",
                })
            continue

        try:
            account_info = None
            with transaction.atomic():
                if r["statut"] == "nouveau":
                    password = _temp_password()
                    apprenant = Apprenant(
                        email=r["email"],
                        nom=r["nom_famille"] or r["nom"][:30],
                        prenom=r["prenom"] or "",
                        institution=institution,
                        annee_scolaire_active=annee,
                        role=role,
                        is_active=True,
                    )
                    apprenant.set_password(password)
                    apprenant.save()
                    account_info = {"email": apprenant.email, "password": password}
                    appr = apprenant
                else:
                    appr = Apprenant.objects.filter(pk=r["apprenant_id"]).first()
                    if appr is None:
                        skipped += 1
                        errors.append({
                            "ligne": r.get("ligne"), "email": r.get("email") or "",
                            "nom": r.get("nom") or "", "statut": "introuvable",
                            "message": "Apprenant introuvable.",
                        })
                        continue

                classe = Classe.objects.filter(pk=r["classe_id"]).first() if r.get("classe_id") else None
                _, was_created = Inscription.objects.get_or_create(
                    apprenant=appr,
                    institution=institution,
                    annee_scolaire=annee,
                    defaults={
                        "classe": classe,
                        "statut": "actif",
                        "statut_paiement": "en_attente",
                    },
                )
                if was_created:
                    created_inscriptions += 1
                else:
                    skipped += 1
            if account_info:
                created_accounts.append(account_info)
        except Exception as exc:
            errors.append({
                "ligne": r.get("ligne"), "email": r.get("email") or "",
                "nom": r.get("nom") or "", "statut": "erreur",
                "message": str(exc),
            })

    return {
        "created_inscriptions": created_inscriptions,
        "created_accounts": created_accounts,
        "skipped": skipped,
        "errors": errors,
    }
