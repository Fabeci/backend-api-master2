import logging
from celery import shared_task

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — pipeline IA unifié (analytics.services.ai_claude_service)
# ══════════════════════════════════════════════════════════════════════════════

def _bloc_texte(bloc) -> str:
    """Extrait le texte brut d'un BlocContenu (pour alimenter le prompt)."""
    if not bloc:
        return ''
    import re
    parts = []
    for field in ('contenu_html', 'contenu_texte', 'contenu_markdown', 'code_source'):
        val = getattr(bloc, field, None)
        if val:
            parts.append(re.sub(r'<[^>]+>', ' ', str(val)).strip())
    return '\n'.join(parts)[:3000]


def _traiter(ai_req):
    """Exécute la génération IA puis crée le ContenuGenere / QuizGenereClaude."""
    from analytics.services.ai_claude_service import traiter_demande_ai
    from analytics.views import _creer_contenu_genere
    traiter_demande_ai(ai_req)
    _creer_contenu_genere(ai_req)
    return ai_req


# ══════════════════════════════════════════════════════════════════════════════
# TÂCHES
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(name='generer_contenu_alternatif', bind=False)
def generer_contenu_alternatif(apprenant_id, bloc_id):
    """Génère un contenu alternatif/simplifié pour un bloc (trigger multi_reouverture)."""
    from users.models import Apprenant
    from courses.models import BlocContenu
    from analytics.models import AIAnalysisRequest, ContenuGenere, RecommandationPedagogique

    try:
        apprenant = Apprenant.objects.get(id=apprenant_id)
        bloc = BlocContenu.objects.select_related('sequence__module__cours').get(id=bloc_id)

        seq = getattr(bloc, 'sequence', None)
        mod = getattr(seq, 'module', None) if seq else None
        crs = getattr(mod, 'cours', None) if mod else None

        context = {
            'bloc_titre': bloc.titre,
            'bloc_contenu': _bloc_texte(bloc),
            'duree_estimee_min': 0,
            'duree_passee_min': 0,
            'ratio_pct': 0,
            'nb_ouvertures': 1,
            'scroll_max_pct': 0,
            'cours_titre': crs.titre if crs else '',
            'sequence_titre': seq.titre if seq else '',
        }

        ai_req = _traiter(AIAnalysisRequest.objects.create(
            apprenant=apprenant,
            bloc=bloc,
            sequence=seq,
            module=mod,
            cours=crs,
            trigger='multi_reouverture',
            prompt_context=context,
        ))

        contenu = ContenuGenere.objects.filter(ai_request=ai_req).first()
        if not contenu:
            logger.warning("Generateur a retourne None pour apprenant=%s bloc=%s", apprenant_id, bloc_id)
            return "Echec de generation (contenu=None)"

        RecommandationPedagogique.objects.create(
            apprenant=apprenant,
            cours=crs,
            bloc_cible=bloc,
            sequence_cible=seq,
            contenu_genere=contenu,
            type_recommandation='contenu_alternatif',
            message=f"Une nouvelle approche est disponible pour « {bloc.titre} » !",
            priorite=2,
        )
        logger.info("Contenu alternatif genere pour apprenant=%s bloc=%s", apprenant_id, bloc_id)
        return f"Contenu genere pour {apprenant}"

    except Exception:
        logger.exception("Erreur dans generer_contenu_alternatif apprenant=%s bloc=%s", apprenant_id, bloc_id)
        raise


@shared_task(name='generer_contenu_remediation', bind=False)
def generer_contenu_remediation(apprenant_id, question_id, bloc_id):
    """Génère un quiz de remédiation ciblé sur une question ratée (trigger quiz_rate)."""
    from users.models import Apprenant
    from evaluations.models import Question
    from courses.models import BlocContenu
    from analytics.models import AIAnalysisRequest, QuizGenereClaude, RecommandationPedagogique

    try:
        apprenant = Apprenant.objects.get(id=apprenant_id)
        question = Question.objects.select_related('quiz__sequence__module__cours').get(id=question_id)
        bloc = BlocContenu.objects.filter(id=bloc_id).first()

        quiz = getattr(question, 'quiz', None)
        seq = getattr(quiz, 'sequence', None) if quiz else None
        mod = getattr(seq, 'module', None) if seq else None
        crs = getattr(mod, 'cours', None) if mod else None

        context = {
            'quiz_titre': getattr(quiz, 'titre', '') if quiz else '',
            'quiz_description': getattr(quiz, 'description', '') or '',
            'score_obtenu': 0,
            'nb_tentatives': 1,
            'questions_ratees': [{'question': question.enonce_texte}],
            'cours_titre': crs.titre if crs else '',
            'sequence_titre': seq.titre if seq else '',
        }

        ai_req = _traiter(AIAnalysisRequest.objects.create(
            apprenant=apprenant,
            bloc=bloc,
            quiz=quiz,
            sequence=seq,
            module=mod,
            cours=crs,
            trigger='quiz_rate',
            prompt_context=context,
        ))

        quiz_genere = QuizGenereClaude.objects.filter(ai_request=ai_req).first()
        if not quiz_genere:
            logger.warning("Generateur a retourne None pour remediation apprenant=%s", apprenant_id)
            return "Echec de generation (contenu=None)"

        RecommandationPedagogique.objects.create(
            apprenant=apprenant,
            cours=crs,
            bloc_cible=bloc,
            sequence_cible=seq,
            quiz_genere=quiz_genere,
            type_recommandation='quiz_supplementaire',
            message="Un quiz de remédiation est prêt pour vous aider à progresser !",
            priorite=1,
        )
        logger.info("Contenu remediation genere pour apprenant=%s question=%s", apprenant_id, question_id)
        return "Contenu de remediation genere"

    except Exception:
        logger.exception("Erreur dans generer_contenu_remediation apprenant=%s", apprenant_id)
        raise


@shared_task(name='generer_contenu_adaptatif_sequence', bind=False)
def generer_contenu_adaptatif_sequence(apprenant_id, sequence_id, reco_id=None):
    """
    Pré-génère un contenu adaptatif (séquence) pour une recommandation prioritaire,
    puis rattache le `ContenuGenere` obtenu à la recommandation.
    """
    from users.models import Apprenant
    from courses.models import Sequence
    from analytics.models import AIAnalysisRequest, ContenuGenere, RecommandationPedagogique

    def _rattacher_contenu(contenu):
        if reco_id:
            RecommandationPedagogique.objects.filter(pk=reco_id).update(contenu_genere=contenu)

    try:
        apprenant = Apprenant.objects.get(id=apprenant_id)
        sequence = Sequence.objects.select_related('module__cours').get(id=sequence_id)
    except Exception:
        logger.exception("Sequence/apprenant introuvable (apprenant=%s sequence=%s)", apprenant_id, sequence_id)
        return "Element introuvable"

    try:
        # Anti-doublon : un contenu existe-t-il déjà pour cette séquence ?
        existant = ContenuGenere.objects.filter(
            apprenant=apprenant, sequence_source=sequence,
        ).order_by('-created_at').first()
        if existant:
            _rattacher_contenu(existant)
            return "Contenu deja existant"

        mod = getattr(sequence, 'module', None)
        crs = getattr(mod, 'cours', None) if mod else None

        from analytics.recommendation_engine import build_sequence_adaptative_context
        context = build_sequence_adaptative_context(apprenant, sequence)

        ai_req = _traiter(AIAnalysisRequest.objects.create(
            apprenant=apprenant,
            sequence=sequence,
            module=mod,
            cours=crs,
            trigger='sequence_complexe',
            prompt_context=context,
        ))

        contenu = ContenuGenere.objects.filter(ai_request=ai_req).first()
        if not contenu:
            logger.warning("Pre-generation: contenu=None (apprenant=%s sequence=%s)", apprenant_id, sequence_id)
            return "Echec de generation (contenu=None)"

        _rattacher_contenu(contenu)
        logger.info("Contenu adaptatif pre-genere apprenant=%s sequence=%s", apprenant_id, sequence_id)
        return "Contenu adaptatif genere"

    except Exception:
        logger.exception("Erreur pre-generation apprenant=%s sequence=%s", apprenant_id, sequence_id)
        raise


@shared_task(name='generer_contenu_intervention', bind=False)
def generer_contenu_intervention(intervention_id):
    """Génère le contenu/quiz IA d'une intervention (garde-fous inclus)."""
    from analytics.models import LearningIntervention
    from analytics.services.ai_intervention_service import request_intervention_generation

    try:
        iv = LearningIntervention.objects.get(id=intervention_id)
    except LearningIntervention.DoesNotExist:
        return 'introuvable'

    req, reason = request_intervention_generation(iv)
    if not req:
        logger.info("Génération intervention %s ignorée : %s", intervention_id, reason)
        return reason

    try:
        _traiter(req)
        return 'generated'
    except Exception:
        logger.exception("Erreur génération intervention %s", intervention_id)
        raise


@shared_task(name='analyser_progression_quotidienne', bind=False)
def analyser_progression_quotidienne():
    """
    Analyse quotidienne :
      1. génère et persiste les recommandations pour tous les apprenants actifs ;
      2. pré-génère (optionnellement) le contenu adaptatif des recommandations
         prioritaires (priorité 1-2) qui n'en ont pas encore.
    """
    from django.conf import settings
    from users.models import Apprenant
    from analytics.services.recommendation_engine import RecommendationEngine
    from analytics.models import RecommandationPedagogique

    pregen       = getattr(settings, 'AI_PREGENERATE_DAILY', True)
    budget_max   = getattr(settings, 'AI_PREGENERATE_MAX_PER_RUN', 50)
    generes_lances = 0

    from time import monotonic
    t0 = monotonic()

    # Nettoyage des requêtes IA bloquées (thread interrompu par un redémarrage)
    try:
        from analytics.models import AIAnalysisRequest
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        stale = AIAnalysisRequest.objects.filter(
            status='pending', created_at__lt=_tz.now() - _td(minutes=10),
        ).update(status='error', error_message='[timeout] thread interrompu', completed_at=_tz.now())
        if stale:
            logger.info("Requêtes IA périmées annulées: %s", stale)
    except Exception:
        logger.exception("Erreur nettoyage requêtes IA")

    try:
        compteur = 0
        diag_total = 0
        iv_total = 0
        apprenants = Apprenant.objects.filter(is_active=True)

        for apprenant in apprenants:
            # ✅ Pipeline longitudinal (états précalculés → pas de recalcul redondant)
            try:
                from analytics.services.engagement_engine import compute_engagement, refresh_engagement_state
                from analytics.services.performance_engine import compute_performance, refresh_performance_state
                from analytics.services.competence_engine import refresh_all_competences
                from analytics.services.progress_engine import compute_learning_state, refresh_learning_state
                from analytics.services.signal_engine import compute_signals, refresh_signals
                from analytics.services.diagnosis_engine import compute_diagnoses, refresh_diagnoses
                from analytics.services.intervention_engine import refresh_interventions
                from analytics.services.outcome_engine import refresh_outcomes
                from analytics.services.risk_engine import refresh_risk_state

                # 1) États (calculés une seule fois)
                eng  = compute_engagement(apprenant)
                perf = compute_performance(apprenant)
                st   = compute_learning_state(apprenant)
                refresh_engagement_state(apprenant, computed=eng)
                refresh_performance_state(apprenant, computed=perf)
                refresh_all_competences(apprenant)

                # 2) Signaux → Diagnostics
                signals = compute_signals(apprenant, eng=eng, perf=perf, st=st)
                refresh_signals(apprenant, computed=signals)
                diagnoses = compute_diagnoses(apprenant, signals=signals)
                diag_objs = refresh_diagnoses(apprenant, diagnoses=diagnoses)
                diag_total += len(diag_objs)

                # 3) Interventions → efficacité → risque → état
                ivs = refresh_interventions(apprenant, diagnoses=diag_objs)
                iv_total += len(ivs)
                refresh_outcomes(apprenant)
                refresh_risk_state(apprenant)
                refresh_learning_state(apprenant)  # en dernier (lit engagement + risque)
            except Exception:
                logger.exception("Erreur pipeline apprenant=%s", apprenant.pk)

            try:
                recos = RecommendationEngine(apprenant).analyser_et_recommander()
                compteur += len(recos)
            except Exception:
                logger.exception("Erreur analyse progression pour apprenant=%s", apprenant.pk)
                continue

            if not pregen:
                continue

            # ✅ IA ciblée (Phase 11) : pré-générer pour les interventions IA
            #    prioritaires (P1-P2) sans contenu ni quiz.
            from analytics.models import LearningIntervention
            ai_ivs = LearningIntervention.objects.filter(
                apprenant=apprenant,
                status__in=['proposee', 'acceptee', 'en_cours'],
                intervention_type__in=['AI_CONTENT', 'AI_QUIZ'],
                priority__lte=2,
                contenu_genere__isnull=True,
                quiz_genere__isnull=True,
            ).order_by('priority')

            for iv in ai_ivs:
                if generes_lances >= budget_max:
                    break
                generer_contenu_intervention.delay(iv.pk)
                generes_lances += 1

            if generes_lances >= budget_max:
                logger.info("Budget de pre-generation atteint (%s)", budget_max)
                break

        duree = round(monotonic() - t0, 1)
        logger.info(
            "Analyse quotidienne : %s apprenants | %s recommandations | %s diagnostics | "
            "%s interventions | %s pre-generations IA | %.1fs",
            apprenants.count(), compteur, diag_total, iv_total, generes_lances, duree,
        )
        return (
            f"{compteur} recommandations, {diag_total} diagnostics, "
            f"{iv_total} interventions, {generes_lances} pre-generations "
            f"pour {apprenants.count()} apprenants en {duree}s"
        )

    except Exception:
        logger.exception("Erreur globale dans analyser_progression_quotidienne")
        raise


# ══════════════════════════════════════════════════════════════════════════════
# RAPPELS DE SÉANCES (avant l'heure) — visio / présentiel
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(name='rappels_sessions_a_venir', bind=False)
def rappels_sessions_a_venir():
    """
    Notifie les participants (apprenants inscrits au cours) et le formateur
    des séances qui commencent dans les prochaines minutes.

    Fenêtre configurable via settings.SESSION_REMINDER_MINUTES (défaut 15).
    Le drapeau `Session.rappel_envoye` garantit un envoi unique.
    """
    from datetime import timedelta
    from django.conf import settings
    from django.utils import timezone
    from users.models import User
    from courses.models import InscriptionCours, Session
    from notifications.signals import _notifier
    from notifications.models import (
        TypeNotification, PrioriteNotification, EntityType,
    )

    minutes = getattr(settings, 'SESSION_REMINDER_MINUTES', 15)
    now = timezone.now()
    limite = now + timedelta(minutes=minutes)

    sessions = (
        Session.objects
        .select_related('cours', 'formateur', 'institution', 'annee_scolaire')
        .filter(
            statut='planifiee',
            rappel_envoye=False,
            date_debut__gt=now,
            date_debut__lte=limite,
        )
    )

    total = 0
    for seance in sessions:
        heure = timezone.localtime(seance.date_debut).strftime('%H:%M') if seance.date_debut else ''
        destinataires = set()

        for insc in InscriptionCours.objects.filter(cours=seance.cours).only('apprenant_id'):
            if insc.apprenant_id:
                destinataires.add(insc.apprenant_id)
        if seance.formateur_id:
            destinataires.add(seance.formateur_id)

        message = f"La séance « {seance.titre} » commence à {heure}."
        if seance.lien_visio:
            message += " Rejoignez la réunion en ligne depuis la page du cours."

        for user in User.objects.filter(id__in=destinataires):
            _notifier(
                recipient=user,
                type_notif=TypeNotification.RAPPEL_SESSION,
                titre=f"Rappel : séance « {seance.titre} »",
                message=message,
                priorite=PrioriteNotification.HAUTE,
                entity_type=EntityType.SESSION,
                entity_id=seance.id,
                action_url=f"/formations/cours/detail/{seance.cours_id}",
                institution=seance.institution,
                annee_scolaire=seance.annee_scolaire,
                groupe_dedup=f"rappel_session_{seance.id}",
            )
            total += 1

        seance.rappel_envoye = True
        seance.save(update_fields=['rappel_envoye'])

    logger.info("Rappels de séances envoyés : %s", total)
    return f"{total} rappel(s) de séance envoyé(s)"


# ══════════════════════════════════════════════════════════════════════════════
# PUBLICATION PROGRESSIVE — bascule « programmé » → « publié » à l'heure prévue
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(name='publier_contenus_programmes', bind=False)
def publier_contenus_programmes():
    """
    Idempotent : publie les modules / séquences / blocs dont la date de
    publication programmée est atteinte (fuseau du projet).

    ⚠️ La sécurité NE dépend PAS de cette tâche : les endpoints apprenants
    vérifient la date et l'état à chaque requête (courses/publication.py).
    """
    from django.utils import timezone
    from courses.models import Module, Sequence, BlocContenu

    now = timezone.now()
    total = 0
    try:
        for model in (Module, Sequence, BlocContenu):
            total += model.objects.filter(
                etat_publication='programme',
                date_publication_programmee__isnull=False,
                date_publication_programmee__lte=now,
            ).update(etat_publication='publie', date_publication_effective=now)
        logger.info("[publication] %s contenu(s) publié(s) automatiquement", total)
    except Exception:  # noqa: BLE001
        logger.exception("[publication] échec de la publication automatique")
    return total
