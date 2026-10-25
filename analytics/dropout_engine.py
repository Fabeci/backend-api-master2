# analytics/dropout_engine.py
# ============================================================================
# MOTEUR DE RISQUE DE DÉCROCHAGE
# Score 0-100 : < 40 = faible, 40-69 = moyen, 70+ = élevé
# ============================================================================
import logging
from datetime import timedelta
from django.db.models import Max
from django.utils import timezone

logger = logging.getLogger(__name__)


def compute_dropout_risk(apprenant, cours=None) -> float:
    from .models import BlocAnalytics, SkillMasteryScore, KnowledgeGap

    score = 0.0

    # F1 — Inactivité (35 pts max : 14j sans activité = 35 pts)
    qs = BlocAnalytics.objects.filter(apprenant=apprenant)
    if cours:
        qs = qs.filter(cours=cours)
    derniere = qs.aggregate(Max('ouvert_le'))['ouvert_le__max']
    if derniere:
        jours = (timezone.now() - derniere).days
        score += min(35.0, jours * 2.5)
    else:
        score += 35.0

    # F2 — Maîtrise faible (30 pts max)
    mastery_qs = SkillMasteryScore.objects.filter(apprenant=apprenant)
    if cours:
        mastery_qs = mastery_qs.filter(cours=cours)
    scores = list(mastery_qs.values_list('score', flat=True))
    if scores:
        avg = sum(scores) / len(scores)
        if avg < 30:   score += 30.0
        elif avg < 50: score += 15.0
        elif avg < 70: score += 5.0
    else:
        score += 20.0  # pas de données = risque modéré inconnu

    # F3 — Peu de sessions sur 30 jours (20 pts max)
    since_30 = timezone.now() - timedelta(days=30)
    sess_qs  = BlocAnalytics.objects.filter(apprenant=apprenant, ouvert_le__gte=since_30)
    if cours:
        sess_qs = sess_qs.filter(cours=cours)
    nb = sess_qs.count()
    if   nb == 0:  score += 20.0
    elif nb < 3:   score += 15.0
    elif nb < 10:  score += 5.0

    # F4 — Lacunes critiques (15 pts max)
    gap_qs = KnowledgeGap.objects.filter(
        apprenant=apprenant, statut__in=['detectee', 'en_cours']
    )
    if cours:
        gap_qs = gap_qs.filter(sequence__module__cours=cours)
    nb_crit = gap_qs.filter(severity='critique').count()
    nb_mod  = gap_qs.filter(severity='moderee').count()
    score  += min(15.0, nb_crit * 8 + nb_mod * 3)

    return min(100.0, round(score, 2))


def check_and_create_alert(apprenant, cours=None):
    """
    Calcule le risque et crée une DropoutAlert si seuil dépassé.
    Évite les doublons (pas d'alerte si une alerte active existe depuis < 48h).
    Retourne l'alerte créée, ou None.
    """
    from .models import DropoutAlert

    risk = compute_dropout_risk(apprenant, cours)
    if risk < 40:
        return None

    recent_qs = DropoutAlert.objects.filter(
        apprenant=apprenant,
        statut='active',
        created_at__gte=timezone.now() - timedelta(hours=48),
    )
    if cours:
        recent_qs = recent_qs.filter(cours=cours)
    if recent_qs.exists():
        return None

    if risk >= 70:
        alert_type = 'risque_eleve'
        message    = (
            f"Score de risque de décrochage : {risk:.0f}/100. "
            "Intervention pédagogique recommandée."
        )
    else:
        alert_type = 'engagement_faible'
        message    = f"Engagement faible détecté. Score de risque : {risk:.0f}/100."

    alert = DropoutAlert.objects.create(
        apprenant=apprenant,
        cours=cours,
        alert_type=alert_type,
        score_risque=risk,
        message=message,
    )
    logger.info('[dropout] Alerte créée: appr=%s risk=%.0f', apprenant.pk, risk)
    return alert
