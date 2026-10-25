# analytics/services/recommendation_engine.py
# ============================================================================
# MOTEUR DE RECOMMANDATIONS PERSISTÉES
#
# Enveloppe le moteur de calcul `analytics.recommendation_engine.get_recommendations`
# (lacunes critiques/modérées, maîtrise fragile, séquences non évaluées) et
# persiste le résultat sous forme de `RecommandationPedagogique` suivables
# par l'apprenant (endpoints /analytics/recommendations/...).
#
# Utilisé par :
#   - la tâche Celery `analyser_progression_quotidienne`
#   - l'endpoint GET /api/v1/analytics/recommendations/<apprenant_id>/
# ============================================================================
import logging

logger = logging.getLogger(__name__)

# priorite (moteur) → (type_recommandation, priorite persistée)
_PRIORITE_MAP = {
    1: ('bloc_revoir',         1),
    2: ('changement_approche', 2),
    3: ('changement_approche', 3),
    4: ('bloc_revoir',         3),
}

_TYPE_LABELS = {
    'bloc_revoir':         'Revoir',
    'changement_approche': "Changer d'approche",
    'contenu_alternatif':  'Contenu alternatif',
    'quiz_supplementaire': 'Quiz supplémentaire',
    'module_revision':     'Module de révision',
    'pause':               'Pause',
}


def _message_pour(reco: dict) -> str:
    """Construit le message affiché à l'apprenant à partir d'une reco du moteur."""
    titre = reco.get('sequence_titre') or reco.get('module_titre') or reco.get('cours_titre') or 'ce contenu'
    raison = reco.get('raison') or ''
    if reco.get('priorite') == 4:
        return (
            f"Vous n'avez pas encore travaillé « {titre} ». "
            "Pensez à la découvrir pour avancer dans votre parcours."
        )
    return f"{raison} sur « {titre} ». Un contenu adapté est proposé pour vous aider."


class RecommendationEngine:
    """Génère et persiste les recommandations d'un apprenant."""

    def __init__(self, apprenant, cours=None):
        self.apprenant = apprenant
        self.cours = cours

    def _a_activite(self, sequence_id) -> bool:
        """
        True si l'apprenant a une activité réelle enregistrée sur la séquence
        (au moins une session BlocAnalytics). Évite de recommander des séquences
        issues uniquement de données pré-remplies / seed.
        """
        if not sequence_id:
            return False
        from analytics.models import BlocAnalytics
        if BlocAnalytics.objects.filter(
            apprenant=self.apprenant, sequence_id=sequence_id,
        ).exists():
            return True
        # Un quiz terminé sur la séquence compte aussi comme activité réelle.
        from evaluations.models import PassageQuiz
        return PassageQuiz.objects.filter(
            apprenant=self.apprenant, quiz__sequence_id=sequence_id, termine=True,
        ).exists()

    def analyser_et_recommander(self) -> list:
        """
        Calcule les recommandations puis les enregistre en base (sans doublon
        avec une recommandation active déjà suivie ou non pour la même séquence).

        Retourne la liste des RecommandationPedagogique créées.
        """
        from analytics.recommendation_engine import get_recommendations
        from analytics.models import RecommandationPedagogique, ContenuGenere

        try:
            recos = get_recommendations(self.apprenant, cours=self.cours, max_results=5)
        except Exception as exc:  # noqa: BLE001
            logger.exception('[reco] calcul impossible pour apprenant=%s : %s', self.apprenant.pk, exc)
            return []

        creees = []
        for r in recos:
            seq_id = r.get('sequence_id')

            # ✅ Ne recommander que ce que l'apprenant a réellement commencé.
            if not self._a_activite(seq_id):
                continue

            type_reco, priorite = _PRIORITE_MAP.get(r.get('priorite'), ('bloc_revoir', 3))

            # Anti-doublon : une seule reco active par séquence. MAIS si une
            # difficulté NOUVELLE est réapparue après la dernière reco (lacune
            # détectée plus récemment), on autorise une nouvelle reco — même si
            # l'ancienne avait été ignorée/suivie.
            from analytics.models import KnowledgeGap
            last_reco = RecommandationPedagogique.objects.filter(
                apprenant=self.apprenant, sequence_cible_id=seq_id,
            ).order_by('-date_creation').first()
            if last_reco is not None:
                # Difficulté nouvelle (lacune détectée après la dernière reco) ?
                new_gap = KnowledgeGap.objects.filter(
                    apprenant=self.apprenant, sequence_id=seq_id,
                    statut__in=['detectee', 'en_cours'],
                    detected_at__gt=last_reco.date_creation,
                ).exists()
                if not new_gap:
                    # S'il existe déjà une reco ACTIVE (non rejetée) → pas de doublon.
                    dismissed = last_reco.est_suivie or last_reco.est_ignoree
                    if not dismissed:
                        continue
                    # Reco rejetée : on n'en recrée une que si l'apprenant a
                    # retravaillé la séquence depuis (bloc/quiz).
                    from analytics.models import BlocAnalytics
                    from evaluations.models import PassageQuiz
                    renewed = (
                        BlocAnalytics.objects.filter(
                            apprenant=self.apprenant, sequence_id=seq_id,
                            ouvert_le__gt=last_reco.date_creation,
                        ).exists()
                        or PassageQuiz.objects.filter(
                            apprenant=self.apprenant, quiz__sequence_id=seq_id,
                            termine=True, date_passage__gt=last_reco.date_creation,
                        ).exists()
                    )
                    if not renewed:
                        continue

            # Rattacher un éventuel contenu déjà généré pour cette séquence.
            contenu = None
            if r.get('priorite') in (1, 2, 3):
                contenu = (
                    ContenuGenere.objects.filter(
                        apprenant=self.apprenant,
                        sequence_source_id=seq_id,
                    ).order_by('-created_at').first()
                )
            # ✅ Rattacher aussi un quiz de remédiation existant (bouton « Passer le quiz »).
            from analytics.models import QuizGenereClaude
            quiz = (
                QuizGenereClaude.objects.filter(
                    apprenant=self.apprenant,
                    quiz_source__sequence_id=seq_id,
                ).order_by('-created_at').first()
            )

            reco = RecommandationPedagogique.objects.create(
                apprenant=self.apprenant,
                cours_id=r.get('cours_id'),
                sequence_cible_id=seq_id,
                contenu_genere=contenu,
                quiz_genere=quiz,
                type_recommandation=type_reco,
                message=_message_pour(r),
                priorite=priorite,
            )
            creees.append(reco)

        if creees:
            logger.info('[reco] %s recommandation(s) créée(s) pour apprenant=%s',
                        len(creees), self.apprenant.pk)
        return creees
