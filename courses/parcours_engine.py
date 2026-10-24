# courses/parcours_engine.py
# ============================================================================
# MOTEUR DE PARCOURS — déblocage progressif, validation, reprise
#
# Hiérarchie : Cours → Modules → Séquences → Blocs
# Règles :
#   - Un bloc est « validé » selon son type (consulté / visionné / terminé),
#     jamais simplement parce qu'il a été ouvert.
#   - Seuls les blocs **obligatoires ET visibles** bloquent le suivant.
#   - La séquence suivante est débloquée quand tous les blocs obligatoires de
#     la précédente sont validés (+ quiz de la séquence si `quiz_obligatoire`).
#   - Le module suivant quand toutes les séquences du précédent sont validées.
#   - Un module/séquence sans contenu obligatoire ne bloque jamais (anti-deadlock).
# ============================================================================
import logging
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

logger = logging.getLogger(__name__)

CONSULT_RATIO = 0.6   # temps réalisé ≥ 60 % du temps estimé
SCROLL_MIN    = 80    # ou scroll ≥ 80 %
VIDEO_RATIO   = 0.6   # vidéo/audio : ≥ 60 % du temps estimé (proxy visionnage)


# ── Contexte préchargé (évite les N+1) ──────────────────────────────────────

class ParcoursContext:
    def __init__(self, apprenant, cours):
        from .models import Module, Sequence, BlocContenu, BlocProgress
        from analytics.models import BlocAnalytics, BlocAnalyticsSummary

        self.apprenant = apprenant
        self.cours = cours
        self.modules   = list(Module.objects.filter(cours=cours).select_related('cours', 'institution', 'annee_scolaire').order_by('ordre', 'id'))
        self.sequences = list(Sequence.objects.filter(module__cours=cours).select_related('module', 'module__cours', 'module__cours__institution').order_by('ordre', 'id'))
        self.blocs     = list(BlocContenu.objects.filter(sequence__module__cours=cours).select_related('sequence', 'sequence__module', 'sequence__module__cours', 'sequence__module__cours__institution').order_by('ordre', 'id'))
        bloc_ids = [b.pk for b in self.blocs]
        self.prog  = {p.bloc_id: p for p in BlocProgress.objects.filter(apprenant=apprenant, bloc_id__in=bloc_ids)}
        self.summ  = {s.bloc_id: s for s in BlocAnalyticsSummary.objects.filter(apprenant=apprenant, bloc_id__in=bloc_ids)}
        # dernière ouverture par bloc (reprise)
        self.last_open = {}
        for row in BlocAnalytics.objects.filter(
            apprenant=apprenant, bloc_id__in=bloc_ids,
        ).values('bloc_id').annotate(last=Max('ouvert_le')):
            self.last_open[row['bloc_id']] = row['last']

        # progressions de haut niveau (facultatif)
        self.seq_by_module = {}
        for s in self.sequences:
            self.seq_by_module.setdefault(s.module_id, []).append(s)
        self.blocs_by_seq = {}
        for b in self.blocs:
            self.blocs_by_seq.setdefault(b.sequence_id, []).append(b)


# ── Validation d'un bloc ────────────────────────────────────────────────────

def _consulted(bloc, summ) -> bool:
    est = (bloc.duree_estimee_minutes or 0) * 60
    duree = getattr(summ, 'duree_totale_sec', 0) or 0
    scroll = getattr(summ, 'scroll_max_pct', 0) or 0
    ratio = CONSULT_RATIO if bloc.type_bloc not in ('video', 'audio') else VIDEO_RATIO
    # Seuil de scroll effectif (établissement > global) : % au-delà duquel un
    # bloc est considéré comme consulté (donc validé).
    from parametres.services import progression_seuil_completion_pct
    institution = getattr(
        getattr(getattr(getattr(bloc, 'sequence', None), 'module', None), 'cours', None),
        'institution', None,
    )
    scroll_min = progression_seuil_completion_pct(institution, default=SCROLL_MIN)
    if est and duree >= est * ratio:
        return True
    if scroll >= scroll_min:
        return True
    return False


def bloc_est_valide(bloc, prog, summ) -> bool:
    """Un bloc est validé selon son type — jamais juste parce qu'il est ouvert."""
    if prog is not None and prog.est_valide:
        return True
    if prog is not None and prog.est_termine:
        return True
    # Bloc vidéo/audio : visionnage suffisant
    if bloc.type_bloc in ('video', 'audio'):
        return _consulted(bloc, summ)
    # Bloc texte/html/markdown/code/image/fichier/lien : consultation suffisante
    return _consulted(bloc, summ)


def _a_commence(prog, summ) -> bool:
    """Activité RÉELLE : une ligne de suivi vide (0 s, 0 scroll, jamais validée)
    ne doit pas faire croire que le cours est commencé."""
    if prog is not None:
        if prog.est_valide or prog.est_termine:
            return True
        if getattr(prog, "etat", "") in ("en_cours", "termine", "valide", "echoue"):
            return True
    if summ is not None:
        if (getattr(summ, "duree_totale_sec", 0) or 0) > 0:
            return True
        if (getattr(summ, "scroll_max_pct", 0) or 0) > 0:
            return True
    return False


def bloc_etat(bloc, prog, summ, unlocked: bool) -> str:
    if not unlocked:
        return 'verrouille'
    if bloc_est_valide(bloc, prog, summ):
        return 'valide'
    if prog is not None and prog.est_termine:
        return 'termine'
    if _a_commence(prog, summ):
        return 'en_cours'
    return 'non_commence'


# ── Déblocage (parcours) ────────────────────────────────────────────────────

def _oblig_blocs(blocs):
    return [b for b in blocs if b.est_obligatoire and b.est_visible]


def _sequence_quiz_ok(apprenant, sequence) -> bool:
    if not getattr(sequence, 'quiz_obligatoire', False):
        return True
    from evaluations.models import PassageQuiz
    return PassageQuiz.objects.filter(
        apprenant=apprenant, quiz__sequence=sequence, termine=True,
        score__gte=(sequence.quiz_seuil or 60),
    ).exists()


def _sequence_validee(apprenant, sequence, blocs_by_seq, prog, summ) -> bool:
    oblig = _oblig_blocs(blocs_by_seq.get(sequence.pk, []))
    if oblig and not all(bloc_est_valide(b, prog.get(b.pk), summ.get(b.pk)) for b in oblig):
        return False
    return _sequence_quiz_ok(apprenant, sequence)


def build_parcours(apprenant, cours) -> dict:
    """Arbre du cours avec états + verrous + position de reprise.

    ✅ Disponibilité : la STRUCTURE reste toujours visible pour l'apprenant,
    y compris les contenus en brouillon / programmés (date non atteinte) ou dont
    un parent ne l'est pas : ils sont affichés « verrouillés » (« Bientôt
    disponible ») mais leur CONTENU reste bloqué côté API (bloc_disponible).
    Seul un bloc explicitement masqué (`est_visible=False`) est retiré.
    """
    from .publication import module_disponible, sequence_disponible, bloc_disponible

    ctx = ParcoursContext(apprenant, cours)

    # Tous les blocs visibles (pour l'affichage de la structure).
    ctx.seq_by_module = {}
    for s_ in ctx.sequences:
        ctx.seq_by_module.setdefault(s_.module_id, []).append(s_)
    ctx.blocs_by_seq = {}
    for b_ in ctx.blocs:
        if getattr(b_, "est_visible", True):
            ctx.blocs_by_seq.setdefault(b_.sequence_id, []).append(b_)

    # Disponibilité par élément + blocs disponibles (pour les calculs de validation).
    dispo_bloc  = {b.pk: bloc_disponible(b) for b in ctx.blocs if getattr(b, "est_visible", True)}
    dispo_seq   = {s.pk: sequence_disponible(s) for s in ctx.sequences}
    dispo_mod   = {m.pk: module_disponible(m) for m in ctx.modules}
    blocs_dispo_by_seq = {}
    for b_ in ctx.blocs:
        if getattr(b_, "est_visible", True) and dispo_bloc.get(b_.pk):
            blocs_dispo_by_seq.setdefault(b_.sequence_id, []).append(b_)

    modules_out = []
    module_locked = False
    for m in ctx.modules:
        m_dispo = dispo_mod.get(m.pk, False)
        seqs = ctx.seq_by_module.get(m.pk, [])
        seq_locked = module_locked
        seqs_out = []
        for s in seqs:
            s_dispo = dispo_seq.get(s.pk, False) and m_dispo
            blocs = ctx.blocs_by_seq.get(s.pk, [])
            oblig = _oblig_blocs(blocs_dispo_by_seq.get(s.pk, []))
            bloc_locked = seq_locked
            blocs_out = []
            for b in blocs:
                b_dispo = dispo_bloc.get(b.pk, False) and s_dispo
                p, sm = ctx.prog.get(b.pk), ctx.summ.get(b.pk)
                unlocked = not bloc_locked
                verrouille = (not unlocked) or (not b_dispo)
                raison = None
                if not b_dispo:
                    raison = 'Bientôt disponible'
                elif not unlocked:
                    raison = 'Terminez le bloc précédent pour débloquer.'
                blocs_out.append({
                    'bloc_id': b.pk, 'titre': b.titre, 'type_bloc': b.type_bloc,
                    'ordre': b.ordre, 'obligatoire': b.est_obligatoire, 'visible': b.est_visible,
                    'duree_estimee_minutes': b.duree_estimee_minutes,
                    'disponible': b_dispo,
                    'etat': bloc_etat(b, p, sm, unlocked) if b_dispo else 'non_commence',
                    'verrouille': verrouille,
                    'termine': bool(p and p.est_termine),
                    'valide': bloc_est_valide(b, p, sm),
                    'raison_verrou': raison,
                })
                # un bloc obligatoire non validé bloque les suivants — seulement
                # s'il est réellement accessible (sinon il bloquerait tout le cours).
                if b.est_obligatoire and b.est_visible and b_dispo and not bloc_est_valide(b, p, sm):
                    bloc_locked = True
            seq_validee = _sequence_validee(apprenant, s, blocs_dispo_by_seq, ctx.prog, ctx.summ)
            seqs_out.append({
                'sequence_id': s.pk, 'titre': s.titre, 'ordre': s.ordre,
                'disponible': s_dispo,
                'verrouille': seq_locked or not s_dispo,
                'valide': seq_validee,
                'quiz_obligatoire': bool(getattr(s, 'quiz_obligatoire', False)),
                'raison_verrou': ('Bientôt disponible' if not s_dispo
                                  else (None if not seq_locked
                                        else 'Terminez la séquence précédente (ou son quiz) pour débloquer.')),
                'blocs': blocs_out,
            })
            if not seq_locked and not seq_validee and s_dispo:
                seq_locked = True  # la séquence suivante attend la validation de celle-ci
        # module validé si toutes ses séquences (disponibles) sont validées
        seqs_dispo = [s for s in seqs if dispo_seq.get(s.pk) and m_dispo]
        module_valide = bool(seqs_dispo) and all(
            _sequence_validee(apprenant, s, blocs_dispo_by_seq, ctx.prog, ctx.summ) for s in seqs_dispo
        )
        modules_out.append({
            'module_id': m.pk, 'titre': m.titre, 'ordre': m.ordre,
            'disponible': m_dispo,
            'verrouille': module_locked or not m_dispo,
            'valide': module_valide,
            'raison_verrou': ('Bientôt disponible' if not m_dispo
                              else (None if not module_locked
                                    else 'Terminez le module précédent pour débloquer.')),
            'sequences': seqs_out,
        })
        if not module_locked and not module_valide and m_dispo:
            module_locked = True

    return {'cours_id': cours.pk, 'titre': getattr(cours, 'titre', ''), 'modules': modules_out}


def build_parcours_staff(cours) -> dict:
    """Arbre du cours SANS verrous (formateur/responsable/admin : consultation)."""
    from .models import Module, Sequence, BlocContenu

    out = []
    for m in Module.objects.filter(cours=cours).order_by('ordre', 'id'):
        seqs = []
        for s in Sequence.objects.filter(module=m).order_by('ordre', 'id'):
            blocs = [{
                'bloc_id': b.pk, 'titre': b.titre, 'type_bloc': b.type_bloc,
                'ordre': b.ordre, 'obligatoire': b.est_obligatoire, 'visible': b.est_visible,
                'duree_estimee_minutes': b.duree_estimee_minutes,
                'etat': 'non_commence', 'verrouille': False, 'termine': False, 'valide': False,
                'raison_verrou': None,
            } for b in BlocContenu.objects.filter(sequence=s).order_by('ordre', 'id')]
            seqs.append({'sequence_id': s.pk, 'titre': s.titre, 'ordre': s.ordre,
                         'verrouille': False, 'valide': False,
                         'quiz_obligatoire': bool(getattr(s, 'quiz_obligatoire', False)),
                         'raison_verrou': None, 'blocs': blocs})
        out.append({'module_id': m.pk, 'titre': m.titre, 'ordre': m.ordre,
                    'verrouille': False, 'valide': False, 'raison_verrou': None, 'sequences': seqs})
    return {'cours_id': cours.pk, 'titre': getattr(cours, 'titre', ''), 'modules': out}


def resume_position(apprenant, cours) -> dict:
    """
    Bloc de reprise : dernier bloc ouvert non validé (parmi les accessibles),
    sinon premier bloc obligatoire non validé accessible, sinon premier bloc.
    """
    parc = build_parcours(apprenant, cours)
    ordered = []
    for m in parc['modules']:
        for s in m['sequences']:
            for b in s['blocs']:
                ordered.append((m['module_id'], s['sequence_id'], b))

    # État global du cours pour l'apprenant
    all_blocs = [b for m in parc['modules'] for s in m['sequences'] for b in s['blocs']]
    oblig = [b for b in all_blocs if b['obligatoire'] and b['visible']]
    started = any(b['etat'] in ('en_cours', 'termine', 'valide') for b in all_blocs)
    if oblig and all(b['valide'] for b in oblig):
        state = 'termine'
    elif started:
        state = 'en_cours'
    else:
        state = 'non_commence'

    if not ordered:
        return {'module_id': None, 'sequence_id': None, 'bloc_id': None, 'state': state, 'reprise': False}

    # blocs accessibles non validés, obligatoires d'abord
    accessibles = [(mid, sid, b) for mid, sid, b in ordered if not b['verrouille'] and not b['valide']]
    if accessibles:
        ctx = ParcoursContext(apprenant, cours)
        accessibles.sort(key=lambda t: (ctx.last_open.get(t[2]['bloc_id']) is None,
                                        -(ctx.last_open.get(t[2]['bloc_id']).timestamp() if ctx.last_open.get(t[2]['bloc_id']) else 0)))
        mid, sid, b = accessibles[0]
        return {'module_id': mid, 'sequence_id': sid, 'bloc_id': b['bloc_id'],
                'state': state, 'reprise': state == 'en_cours'}

    # tout validé → dernier bloc
    mid, sid, b = ordered[-1]
    return {'module_id': mid, 'sequence_id': sid, 'bloc_id': b['bloc_id'],
            'state': state, 'reprise': False}


def is_bloc_unlocked_for(apprenant, bloc) -> tuple:
    """(bool, raison) — un apprenant peut-il accéder à ce bloc ?"""
    cours = bloc.sequence.module.cours
    parc = build_parcours(apprenant, cours)
    for m in parc['modules']:
        for s in m['sequences']:
            for b in s['blocs']:
                if b['bloc_id'] == bloc.pk:
                    return (not b['verrouille']), b.get('raison_verrou')
    return True, None


def bloc_est_valide_pour(apprenant, bloc) -> bool:
    """Un bloc est-il validé (terminé) pour cet apprenant ?"""
    from .models import BlocProgress
    from analytics.models import BlocAnalyticsSummary
    prog = BlocProgress.objects.filter(apprenant=apprenant, bloc=bloc).first()
    summ = BlocAnalyticsSummary.objects.filter(apprenant=apprenant, bloc=bloc).first()
    return bloc_est_valide(bloc, prog, summ)


def bloc_termine_pour(apprenant, bloc) -> bool:
    """
    Bloc EXPLICITEMENT terminé/validé (marqué par l'apprenant ou le système),
    hors simple consultation par le temps. Sert à décider si l'on propose encore
    une aide : un bloc que l'apprenant vient de terminer n'en a plus besoin.
    """
    from .models import BlocProgress
    prog = BlocProgress.objects.filter(apprenant=apprenant, bloc=bloc).first()
    return bool(prog and (prog.est_valide or prog.est_termine))


def sequence_est_validee_pour(apprenant, sequence) -> bool:
    """Une séquence est-elle validée (tous les blocs obligatoires + quiz) ?"""
    ctx = ParcoursContext(apprenant, sequence.module.cours)
    return _sequence_validee(apprenant, sequence, ctx.blocs_by_seq, ctx.prog, ctx.summ)


def blocs_et_sequences_valides(apprenant, cours) -> tuple:
    """
    Retourne (set des bloc_ids validés, set des sequence_ids validées)
    pour un cours donné, en une seule passe.
    """
    ctx = ParcoursContext(apprenant, cours)
    blocs_valides = {
        b.pk for b in ctx.blocs
        if bloc_est_valide(b, ctx.prog.get(b.pk), ctx.summ.get(b.pk))
    }
    seqs_validees = {
        s.pk for s in ctx.sequences
        if _sequence_validee(apprenant, s, ctx.blocs_by_seq, ctx.prog, ctx.summ)
    }
    return blocs_valides, seqs_validees


def is_sequence_unlocked_for(apprenant, sequence) -> tuple:
    cours = sequence.module.cours
    parc = build_parcours(apprenant, cours)
    for m in parc['modules']:
        for s in m['sequences']:
            if s['sequence_id'] == sequence.pk:
                return (not s['verrouille']), s.get('raison_verrou')
    return True, None


# ── Validation & cascade ────────────────────────────────────────────────────

def validate_block(apprenant, bloc) -> dict:
    """Valide un bloc s'il remplit ses conditions (idempotent) + cascade."""
    from .models import BlocProgress
    from analytics.models import BlocAnalyticsSummary

    unlocked, raison = is_bloc_unlocked_for(apprenant, bloc)
    if not unlocked:
        return {'ok': False, 'raison': raison or 'Bloc verrouillé.'}

    prog, _ = BlocProgress.objects.get_or_create(apprenant=apprenant, bloc=bloc)
    summ = BlocAnalyticsSummary.objects.filter(apprenant=apprenant, bloc=bloc).first()

    valide = bloc_est_valide(bloc, prog, summ)
    changed = False
    if valide and not prog.est_valide:
        prog.est_valide = True
        prog.valide_le = timezone.now()
        changed = True
    prog.etat = 'valide' if valide else ('termine' if prog.est_termine else 'en_cours')
    prog.save()
    _update_progress_cascade(apprenant, bloc)

    # ✅ Aligner la progression globale utilisée par les dashboards
    try:
        from progress.models import ProgressionApprenant
        cours = bloc.sequence.module.cours
        pa, _ = ProgressionApprenant.objects.get_or_create(apprenant=apprenant, cours=cours)
        pa.recalculer_depuis_blocs()
    except Exception as exc:  # noqa: BLE001
        logger.warning('[parcours] progression globale non synchronisée : %s', exc)

    return {'ok': True, 'valide': valide, 'etat': prog.etat}


def _update_progress_cascade(apprenant, bloc):
    """Recalcule SequenceProgress / ModuleProgress / CoursProgress (idempotent)."""
    from .models import Sequence, Module, SequenceProgress, ModuleProgress, CoursProgress

    try:
        sequence = bloc.sequence
        module = sequence.module
        cours = module.cours

        # Séquence validée ?
        ctx = ParcoursContext(apprenant, cours)
        seq_val = _sequence_validee(apprenant, sequence, ctx.blocs_by_seq, ctx.prog, ctx.summ)
        sp, _ = SequenceProgress.objects.get_or_create(apprenant=apprenant, sequence=sequence)
        if sp.est_termine != seq_val:
            sp.est_termine = seq_val
            sp.completed_at = timezone.now() if seq_val else None
            sp.save()

        # Module validé ?
        seqs = list(Sequence.objects.filter(module=module))
        mod_val = bool(seqs) and all(
            _sequence_validee(apprenant, s, ctx.blocs_by_seq, ctx.prog, ctx.summ) for s in seqs
        )
        mp, _ = ModuleProgress.objects.get_or_create(apprenant=apprenant, module=module)
        if mp.est_termine != mod_val:
            mp.est_termine = mod_val
            mp.completed_at = timezone.now() if mod_val else None
            mp.save()

        # Cours validé ?
        mods = list(Module.objects.filter(cours=cours))
        crs_val = bool(mods)
        for mo in mods:
            seqs_mo = list(Sequence.objects.filter(module=mo))
            if not seqs_mo or not all(
                _sequence_validee(apprenant, s, ctx.blocs_by_seq, ctx.prog, ctx.summ) for s in seqs_mo
            ):
                crs_val = False
                break
        cp, _ = CoursProgress.objects.get_or_create(apprenant=apprenant, cours=cours)
        if cp.est_termine != crs_val:
            cp.est_termine = crs_val
            cp.completed_at = timezone.now() if crs_val else None
            cp.save()
    except Exception as e:  # noqa: BLE001
        logger.warning('[parcours] cascade : %s', e)
