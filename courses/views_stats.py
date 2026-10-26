# courses/views_stats.py
"""Tableau de bord formateur — usage agrégé du tuteur IA.

Aucun contenu de message n'est exposé : uniquement des compteurs, des mots-clés
agrégés et des identifiants de cours/blocs.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.rbac import display_role
from users.views import api_error, api_success

from .models import ConversationTuteur, Cours, EvenementTuteur, MessageTuteur, QuizTuteur
from .services import difficulte as difficulte_service
from .services.rag import mots_cles
from .utils import _formateur_cours_ids

ROLES_AUTORISES = ("Admin", "Responsable", "Formateur")


class TuteurStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.tenant import default_institution_id  # import tardif (patchable en tests)

        role = (display_role(request.user) or "").strip()
        if role not in ROLES_AUTORISES:
            return api_error(
                "Tableau de bord réservé à l'encadrement.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        institution_id = default_institution_id()
        cours_qs = Cours.objects.filter(institution_id=institution_id)
        if role == "Formateur":
            cours_qs = cours_qs.filter(id__in=_formateur_cours_ids(request.user))

        cours_filtre = request.query_params.get("cours")
        if cours_filtre:
            cours_qs = cours_qs.filter(id=cours_filtre)

        cours_ids = list(cours_qs.values_list("id", flat=True))

        try:
            jours = max(1, min(365, int(request.query_params.get("jours", 30))))
        except Exception:  # noqa: BLE001
            jours = 30
        depuis = timezone.now() - timedelta(days=jours)

        conversations = ConversationTuteur.objects.filter(
            cours_id__in=cours_ids, maj_le__gte=depuis,
        )
        messages = MessageTuteur.objects.filter(
            conversation__in=conversations, role="user",
        )

        # Notions les plus demandées (scan borné, aucune donnée brute renvoyée).
        compteur: Counter = Counter()
        for contenu in messages.order_by("-cree_le").values_list("contenu", flat=True)[:2000]:
            for mot in set(mots_cles(contenu)):
                compteur[mot] += 1

        # Niveaux de difficulté détectés (borné).
        niveaux = Counter()
        for conversation in (
            conversations
            .select_related("bloc__sequence__module__cours")[:300]
        ):
            try:
                niveaux[difficulte_service.analyser(conversation)["niveau"]] += 1
            except Exception:  # noqa: BLE001
                continue

        # Quiz
        quiz_qs = QuizTuteur.objects.filter(cours_id__in=cours_ids, cree_le__gte=depuis)
        scores = [
            score for score in quiz_qs.filter(statut="corrige").values_list("score", flat=True)
            if score is not None
        ]
        score_moyen = round(sum(scores) / len(scores), 1) if scores else None

        # Refus pendant évaluation et explications d'erreur
        refus = EvenementTuteur.objects.filter(
            type="refus_evaluation", cours_id__in=cours_ids, cree_le__gte=depuis,
        ).count()
        explications = EvenementTuteur.objects.filter(
            type="explication", cours_id__in=cours_ids, cree_le__gte=depuis,
        ).count()

        # Activité par cours (top 5)
        par_cours = list(
            conversations.values("cours_id").annotate(nb=Count("id")).order_by("-nb")[:5]
        )
        titres = dict(
            Cours.objects.filter(id__in=[ligne["cours_id"] for ligne in par_cours])
            .values_list("id", "titre")
        )

        return api_success("Statistiques du tuteur.", {
            "periode_jours": jours,
            "conversations": conversations.count(),
            "messages": messages.count(),
            "apprenants_actifs": conversations.values("apprenant_id").distinct().count(),
            "quiz": {
                "total": quiz_qs.count(),
                "corriges": len(scores),
                "score_moyen": score_moyen,
            },
            "refus_evaluation": refus,
            "explications": explications,
            "difficulte": {
                "difficulte": niveaux.get("difficulte", 0),
                "attention": niveaux.get("attention", 0),
                "ok": niveaux.get("ok", 0),
            },
            "notions": [{"mot": mot, "nb": nombre} for mot, nombre in compteur.most_common(10)],
            "par_cours": [
                {
                    "cours_id": ligne["cours_id"],
                    "titre": titres.get(ligne["cours_id"], "—"),
                    "conversations": ligne["nb"],
                }
                for ligne in par_cours
            ],
            "cours_disponibles": [
                {"id": cours.id, "titre": cours.titre}
                for cours in cours_qs.order_by("titre")[:100]
            ],
        })
