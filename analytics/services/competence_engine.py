# analytics/services/competence_engine.py
# ============================================================================
# MOTEUR DE COMPÉTENCES & MAÎTRISE (Phase 6)
#
# Pour chaque compétence d'un apprenant, agrège des PREUVES hétérogènes :
#   - maîtrise de séquences/modules/cours liés (SkillMasteryScore)
#   - réponses aux questions liées (ReponseQuiz / ReponseQuestion)
#   - notes d'évaluations liées (PassageEvaluation)
# et calcule un score de maîtrise + une CONFIANCE (quantité & cohérence).
# ============================================================================
import logging
from statistics import mean, pstdev

logger = logging.getLogger(__name__)


def _cls(score: float) -> str:
    if score < 40: return 'non_acquis'
    if score < 70: return 'fragile'
    if score < 90: return 'maitrise'
    return 'expert'


def collect_evidence(apprenant, competence) -> list:
    """Renvoie une liste de preuves [{'source', 'score', 'weight'}]."""
    from analytics.models import CompetenceCible, SkillMasteryScore, LearnerProfile
    from evaluations.models import ReponseQuiz, ReponseQuestion, PassageEvaluation

    ev = []
    links = CompetenceCible.objects.filter(competence=competence)

    for l in links:
        # Maîtrise pédagogique liée
        for kind, obj_id in (('sequence', l.sequence_id), ('module', l.module_id), ('cours', l.cours_id)):
            if not obj_id:
                continue
            m = SkillMasteryScore.objects.filter(
                apprenant=apprenant, **{f'{kind}_id': obj_id},
            ).first()
            if m is not None:
                ev.append({'source': f'{kind}:{obj_id}', 'score': float(m.score), 'weight': 1.0})

        # Question liée : taux de réussite
        if l.question_id:
            resp = ReponseQuiz.objects.filter(passage_quiz__apprenant=apprenant, question_id=l.question_id)
            total = resp.count()
            correct = resp.filter(points_obtenus__gt=0).count()
            if total:
                ev.append({'source': f'question:{l.question_id}',
                           'score': round((correct / total) * 100, 1), 'weight': 1.0})

        # Évaluation liée : note normalisée
        if l.evaluation_id:
            for p in PassageEvaluation.objects.filter(
                apprenant=apprenant, evaluation_id=l.evaluation_id, note__isnull=False,
            ).select_related('evaluation'):
                bareme = float(getattr(p.evaluation, 'bareme', 20) or 20)
                ev.append({'source': f'evaluation:{l.evaluation_id}',
                           'score': round((float(p.note) / bareme) * 100, 1), 'weight': 1.0})

    return ev


def compute_competence_mastery(apprenant, competence) -> dict:
    ev = collect_evidence(apprenant, competence)
    if not ev:
        return {'score': 0.0, 'confidence': 0.0, 'niveau': 'non_acquis',
                'evidence_count': 0, 'evidence': []}

    scores = [e['score'] for e in ev]
    mastery = round(mean(scores), 1)
    n = len(scores)
    spread = pstdev(scores) if n > 1 else 0.0
    # Confiance = quantité (n/5) × cohérence (1 - dispersion)
    confidence = round(min(1.0, n / 5.0) * (1 - min(1.0, spread / 100)), 2)

    return {
        'score': mastery,
        'confidence': confidence,
        'niveau': _cls(mastery),
        'evidence_count': n,
        'evidence': ev[:20],
    }


def refresh_competence_mastery(apprenant, competence, save: bool = True):
    from analytics.models import CompetenceMastery

    data = compute_competence_mastery(apprenant, competence)
    obj, _ = CompetenceMastery.objects.get_or_create(apprenant=apprenant, competence=competence)
    prev = obj.score if obj.pk else None
    obj.score_precedent = prev
    obj.score = data['score']
    obj.confidence = data['confidence']
    obj.niveau = data['niveau']
    obj.evidence_count = data['evidence_count']
    obj.evidence = data['evidence']
    if prev is None:
        obj.tendance = 'stable'
    elif data['score'] - prev >= 8:
        obj.tendance = 'hausse'
    elif data['score'] - prev <= -8:
        obj.tendance = 'baisse'
    else:
        obj.tendance = 'stable'
    if save:
        obj.save()
    return obj


def refresh_all_competences(apprenant):
    """Recalcule la maîtrise de toutes les compétences liées à l'apprenant."""
    from analytics.models import Competence, CompetenceCible, CompetenceMastery
    from courses.models import InscriptionCours

    cours_ids = list(
        InscriptionCours.objects.filter(apprenant=apprenant).values_list('cours_id', flat=True).distinct()
    )
    # Compétences liées aux cours de l'apprenant (ou via séquences/modules de ces cours)
    comp_ids = set(
        CompetenceCible.objects.filter(cours_id__in=cours_ids).values_list('competence_id', flat=True)
    )
    comp_ids |= set(
        CompetenceCible.objects.filter(module__cours_id__in=cours_ids).values_list('competence_id', flat=True)
    )
    comp_ids |= set(
        CompetenceCible.objects.filter(sequence__module__cours_id__in=cours_ids).values_list('competence_id', flat=True)
    )
    out = []
    for comp in Competence.objects.filter(pk__in=comp_ids, est_active=True):
        out.append(refresh_competence_mastery(apprenant, comp))
    return out


def competences_summary(apprenant) -> dict:
    """Renvoie {competences:[...], fortes:[...], a_renforcer:[...]}."""
    from analytics.models import CompetenceMastery

    qs = CompetenceMastery.objects.filter(apprenant=apprenant).select_related('competence')
    items = [{
        'competence_id': m.competence_id,
        'code':          m.competence.code,
        'libelle':       m.competence.libelle,
        'score':         m.score,
        'confidence':    m.confidence,
        'niveau':        m.niveau,
        'tendance':      m.tendance,
        'evidence_count': m.evidence_count,
    } for m in qs]
    fortes = [i for i in items if i['niveau'] in ('maitrise', 'expert')]
    a_renforcer = [i for i in items if i['niveau'] in ('non_acquis', 'fragile')]
    return {'competences': items, 'fortes': fortes, 'a_renforcer': a_renforcer}
