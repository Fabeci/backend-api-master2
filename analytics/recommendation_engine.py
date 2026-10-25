# analytics/recommendation_engine.py
# ============================================================================
# MOTEUR DE RECOMMANDATIONS — Version intermédiaire
#
# Génère une liste ordonnée de séquences à retravailler basée sur :
#   1. Lacunes critiques non résolues
#   2. Lacunes modérées non résolues
#   3. Séquences en niveau "fragile" (tendance stable ou baisse)
#   4. Séquences jamais évaluées dans les cours inscrits
# ============================================================================
import logging

logger = logging.getLogger(__name__)

PRIORITE_LABELS = {1: 'critique', 2: 'moderee', 3: 'fragile', 4: 'non_evalue'}
RAISONS = {
    1: 'Lacune critique détectée',
    2: 'Lacune modérée détectée',
    3: 'Maîtrise fragile',
    4: 'Séquence jamais évaluée',
}


def get_recommendations(apprenant, cours=None, max_results: int = 5) -> list:
    """
    Retourne une liste ordonnée de recommandations pour l'apprenant.

    Chaque entrée :
    {
      'sequence_id':    int,
      'sequence_titre': str,
      'module_titre':   str,
      'cours_titre':    str,
      'cours_id':       int,
      'priorite':       int (1=critique, 2=moderee, 3=fragile, 4=non_évalué),
      'priorite_label': str,
      'raison':         str,
      'score':          float | None,
      'tendance':       str | None,
      'severity':       str | None,
    }
    """
    from .models import KnowledgeGap, SkillMasteryScore

    results = []
    seen_seq_ids = set()

    # ✅ Une séquence DÉJÀ VALIDÉE (blocs obligatoires terminés + quiz) ne doit
    #    plus être recommandée, même si une lacune/maîtrise ancienne subsiste.
    from courses.parcours_engine import build_parcours
    _valide_cache: dict = {}

    def _seqs_validees(crs) -> set:
        if crs is None:
            return set()
        if crs.pk not in _valide_cache:
            try:
                parc = build_parcours(apprenant, crs)
                _valide_cache[crs.pk] = {
                    s['sequence_id']
                    for m in parc.get('modules', [])
                    for s in m.get('sequences', [])
                    if s.get('valide')
                }
            except Exception as e:  # noqa: BLE001
                logger.warning('[reco] parcours indisponible (cours %s) : %s', crs.pk, e)
                _valide_cache[crs.pk] = set()
        return _valide_cache[crs.pk]

    def _est_validee(seq) -> bool:
        mod = getattr(seq, 'module', None)
        crs = getattr(mod, 'cours', None) if mod else None
        return seq.pk in _seqs_validees(crs)

    # ── Priorité 1 & 2 : lacunes actives ─────────────────────────────────────
    gap_qs = KnowledgeGap.objects.filter(
        apprenant=apprenant,
        statut__in=['detectee', 'en_cours'],
    ).select_related('sequence__module__cours').order_by(
        # critique avant moderee, puis plus récent
        '-severity', '-detected_at'
    )
    if cours:
        gap_qs = gap_qs.filter(sequence__module__cours=cours)

    for gap in gap_qs:
        if len(results) >= max_results:
            break
        seq = gap.sequence
        if seq.pk in seen_seq_ids:
            continue
        if _est_validee(seq):
            continue
        seen_seq_ids.add(seq.pk)
        mod = getattr(seq, 'module', None)
        crs = getattr(mod, 'cours', None) if mod else None
        priorite = 1 if gap.severity == 'critique' else 2
        results.append({
            'sequence_id':    seq.pk,
            'sequence_titre': seq.titre,
            'module_titre':   mod.titre if mod else '',
            'cours_titre':    crs.titre if crs else '',
            'cours_id':       crs.pk if crs else None,
            'priorite':       priorite,
            'priorite_label': PRIORITE_LABELS[priorite],
            'raison':         RAISONS[priorite],
            'score':          None,
            'tendance':       None,
            'severity':       gap.severity,
        })

    # ── Priorité 3 : niveau fragile (avec score) ──────────────────────────────
    if len(results) < max_results:
        fragile_qs = SkillMasteryScore.objects.filter(
            apprenant=apprenant,
            sequence__isnull=False,
            niveau='fragile',
        ).select_related('sequence__module__cours').order_by('score')
        if cours:
            fragile_qs = fragile_qs.filter(cours=cours)

        for sms in fragile_qs:
            if len(results) >= max_results:
                break
            seq = sms.sequence
            if seq.pk in seen_seq_ids:
                continue
            if _est_validee(seq):
                continue
            seen_seq_ids.add(seq.pk)
            mod = getattr(seq, 'module', None)
            crs = getattr(mod, 'cours', None) if mod else None
            results.append({
                'sequence_id':    seq.pk,
                'sequence_titre': seq.titre,
                'module_titre':   mod.titre if mod else '',
                'cours_titre':    crs.titre if crs else '',
                'cours_id':       crs.pk if crs else None,
                'priorite':       3,
                'priorite_label': PRIORITE_LABELS[3],
                'raison':         RAISONS[3] + (f' ({sms.tendance})' if sms.tendance != 'stable' else ''),
                'score':          sms.score,
                'tendance':       sms.tendance,
                'severity':       None,
            })

    # ── Priorité 4 : séquences jamais évaluées dans les cours inscrits ────────
    if len(results) < max_results:
        try:
            from courses.models import InscriptionCours, Sequence

            cours_ids_qs = (
                InscriptionCours.objects.filter(apprenant=apprenant, statut='actif')
                .values_list('cours_id', flat=True)
            )
            if cours:
                cours_ids_qs = [cours.pk]

            evaluated_seq_ids = set(
                SkillMasteryScore.objects.filter(
                    apprenant=apprenant, sequence__isnull=False
                ).values_list('sequence_id', flat=True)
            )

            non_eval_seqs = (
                Sequence.objects.filter(module__cours_id__in=list(cours_ids_qs))
                .exclude(pk__in=evaluated_seq_ids | seen_seq_ids)
                .select_related('module__cours')
                .order_by('module__cours_id', 'module__ordre', 'ordre')
            )

            for seq in non_eval_seqs:
                if len(results) >= max_results:
                    break
                if _est_validee(seq):
                    continue
                mod = getattr(seq, 'module', None)
                crs = getattr(mod, 'cours', None) if mod else None
                results.append({
                    'sequence_id':    seq.pk,
                    'sequence_titre': seq.titre,
                    'module_titre':   mod.titre if mod else '',
                    'cours_titre':    crs.titre if crs else '',
                    'cours_id':       crs.pk if crs else None,
                    'priorite':       4,
                    'priorite_label': PRIORITE_LABELS[4],
                    'raison':         RAISONS[4],
                    'score':          None,
                    'tendance':       None,
                    'severity':       None,
                })
        except Exception as e:
            logger.warning('[reco] Erreur priorité 4 : %s', e)

    return results


# ============================================================================
# CONTEXTE — détection d'abandon de cours (trigger cours_abandonne)
# ============================================================================

def build_cours_abandonne_context(apprenant, cours) -> dict:
    """
    Agrège le taux de complétion et l'inactivité d'un cours pour décider (et
    alimenter) le trigger `cours_abandonne`.

    Retourne un dict utilisable à la fois pour `_should_trigger` et comme
    `prompt_context` de la génération IA :
      {
        'cours_titre', 'cours_description',
        'ratio_completion' (0-1), 'ratio_completion_pct' (0-100),
        'jours_inactivite', 'modules_non_termines': [titres...]
      }
    """
    from django.db.models import Max
    from django.utils import timezone

    from courses.models import Module, Sequence
    from .models import BlocAnalytics, ModuleAnalyticsSummary, SequenceAnalyticsSummary

    total_seq = Sequence.objects.filter(module__cours=cours).count()
    done_seq = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, cours=cours, completee_le__isnull=False,
    ).count()
    ratio = (done_seq / total_seq) if total_seq else 0.0

    derniere = BlocAnalytics.objects.filter(
        apprenant=apprenant, cours=cours,
    ).aggregate(d=Max('ouvert_le'))['d']
    jours = (timezone.now() - derniere).days if derniere else 9999

    # Modules sans aucune complétion enregistrée
    modules_termines_ids = set(
        ModuleAnalyticsSummary.objects.filter(
            apprenant=apprenant, cours=cours, complete_le__isnull=False,
        ).values_list('module_id', flat=True)
    )
    modules_non_termines = list(
        Module.objects.filter(cours=cours)
        .exclude(pk__in=modules_termines_ids)
        .order_by('ordre')
        .values_list('titre', flat=True)
    )

    return {
        'cours_titre':          getattr(cours, 'titre', ''),
        'cours_description':    getattr(cours, 'description', '') or '',
        'ratio_completion':     round(ratio, 4),
        'ratio_completion_pct': round(ratio * 100),
        'jours_inactivite':     jours,
        'modules_non_termines': modules_non_termines[:10],
    }


# ============================================================================
# CONTEXTE — génération d'une séquence adaptative (trigger sequence_complexe)
# ============================================================================

def build_sequence_adaptative_context(apprenant, sequence) -> dict:
    """
    Construit le `prompt_context` attendu par `generer_sequence_adaptative`
    à partir de la summary analytics et des lacunes actives de la séquence.
    """
    import re
    from courses.models import BlocContenu
    from .models import KnowledgeGap, SequenceAnalyticsSummary

    summary = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, sequence=sequence,
    ).first()
    gaps = KnowledgeGap.objects.filter(
        apprenant=apprenant, sequence=sequence, statut__in=['detectee', 'en_cours'],
    ).order_by('-severity')
    concepts = [g.description for g in gaps if g.description][:5]

    # ✅ Contenu RÉEL des blocs de la séquence (au lieu du seul titre) pour
    #    éviter les générations génériques.
    parts = []
    for b in BlocContenu.objects.filter(sequence=sequence).order_by('ordre')[:20]:
        titre_bloc = getattr(b, 'titre', '') or ''
        texte = ''
        for field in ('contenu_html', 'contenu_texte', 'contenu_markdown', 'code_source'):
            val = getattr(b, field, None)
            if val:
                texte = re.sub(r'<[^>]+>', ' ', str(val)).strip()
                break
        if titre_bloc or texte:
            parts.append(f"{titre_bloc}\n{texte}".strip())
    contenu_texte = '\n\n'.join(p for p in parts if p)[:2500]

    mod = getattr(sequence, 'module', None)
    crs = getattr(mod, 'cours', None) if mod else None

    return {
        'sequence_titre':     sequence.titre,
        'sequence_contenu':   contenu_texte or sequence.titre,
        'module_titre':       mod.titre if mod else '',
        'cours_titre':        crs.titre if crs else '',
        'ratio_temps_pct':    summary.ratio_temps_pct if summary else 0,
        'score_moyen':        summary.score_moyen_quiz if summary else 0,
        'concepts_difficiles': concepts,
    }
