# analytics/services/event_service.py
# ============================================================================
# JOURNAL D'ACTIVITÉ PÉDAGOGIQUE (Phase 2)
#
# Point d'entrée unique pour enregistrer les événements pédagogiques
# (frontend via /analytics/events/bulk/, backend via signals/views).
#
# - Normalise les noms d'événements frontend → taxonomie LearningEventType.
# - Résout la hiérarchie pédagogique (cours/module/séquence/bloc/ressource/séance).
# - Conserve le nom brut dans payload['raw_event_type'] si non reconnu.
# ============================================================================
import logging

logger = logging.getLogger(__name__)


# Alias des noms frontend (event-tracker.service.ts) → taxonomie
EVENT_ALIASES = {
    'cours.opened':        'COURSE_OPENED',
    'course.opened':       'COURSE_OPENED',
    'module.opened':       'MODULE_OPENED',
    'sequence.opened':     'SEQUENCE_STARTED',
    'sequence.started':    'SEQUENCE_STARTED',
    'sequence.completed':  'SEQUENCE_COMPLETED',
    'bloc.opened':         'BLOCK_STARTED',
    'bloc.started':        'BLOCK_STARTED',
    'bloc.paused':         'BLOCK_PAUSED',
    'bloc.resumed':        'BLOCK_RESUMED',
    'bloc.completed':      'BLOCK_COMPLETED',
    'video.play':          'BLOCK_RESUMED',
    'video.pause':         'BLOCK_PAUSED',
    'video.ended':         'RESOURCE_COMPLETED',
    'video.progress':      'RESOURCE_VIEWED',
    'quiz.started':        'QUIZ_STARTED',
    'quiz.completed':      'QUIZ_SUBMITTED',
    'quiz.retaken':        'QUIZ_RETAKEN',
    'evaluation.started':  'EVALUATION_STARTED',
    'evaluation.submitted': 'EVALUATION_SUBMITTED',
    'remediation.opened':  'AI_CONTENT_VIEWED',
    'session.idle_start':  'SESSION_PAUSED',
    'session.idle_end':    'SESSION_RESUMED',
    'session.focus_lost':  'SESSION_PAUSED',
    'session.focus_gained': 'SESSION_RESUMED',
    'session.end':         'SESSION_PAUSED',
}


def normalize_event_type(raw: str) -> str:
    """Renvoie un code de la taxonomie LearningEventType (ou le code brut uppercased)."""
    from ..models import LearningEventType
    if not raw:
        return LearningEventType.OTHER
    key = str(raw).strip()
    if key in EVENT_ALIASES:
        return EVENT_ALIASES[key]
    if key.lower() in EVENT_ALIASES:
        return EVENT_ALIASES[key.lower()]
    up = key.upper().replace('.', '_').replace('-', '_').replace(' ', '_')[:64]
    return up if up in LearningEventType.values else LearningEventType.OTHER


def _get_or_none(model, pk):
    if not pk:
        return None
    try:
        return model.objects.filter(pk=pk).first()
    except Exception:
        return None


def build_event(apprenant, item: dict):
    """
    Construit un LearningEvent (non sauvegardé) à partir d'un item frontend.
    Résout la hiérarchie à partir des ids éventuellement fournis.
    """
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    from analytics.models import LearningEvent
    from courses.models import Cours, Module, Sequence, BlocContenu, RessourceSequence, Session

    raw_type = item.get('event_type') or item.get('type') or ''
    event_type = normalize_event_type(raw_type)

    ts_str = item.get('ts') or None
    try:
        ts = parse_datetime(ts_str) if ts_str else timezone.now()
        if ts is None:
            ts = timezone.now()
    except Exception:
        ts = timezone.now()

    payload = dict(item.get('payload') or {})
    if item.get('metadata'):
        payload.setdefault('metadata', item.get('metadata'))
    if raw_type and event_type != raw_type:
        payload.setdefault('raw_event_type', str(raw_type)[:64])

    return LearningEvent(
        apprenant=apprenant,
        cours=_get_or_none(Cours, item.get('cours_id')),
        module=_get_or_none(Module, item.get('module_id')),
        sequence=_get_or_none(Sequence, item.get('sequence_id')),
        bloc=_get_or_none(BlocContenu, item.get('bloc_id')),
        ressource=_get_or_none(RessourceSequence, item.get('ressource_id')),
        # `session_id` frontend = session technique (trace_id) ;
        # la séance pédagogique (Session) utilise `seance_id`/`session_ref_id`.
        session=_get_or_none(Session, item.get('seance_id') or item.get('session_ref_id')),
        trace_id=str(item.get('session_id') or item.get('trace_id') or '')[:64],
        event_type=event_type,
        ts=ts,
        duree_ms=int(item.get('duree_ms') or (int(item.get('duree_sec') or 0) * 1000)),
        source=str(item.get('source') or 'web')[:32],
        payload=payload,
    )


def record_event(apprenant, event_type, *, ts=None, trace_id='', cours=None, module=None,
                 sequence=None, bloc=None, ressource=None, session=None,
                 duree_ms=0, source='system', metadata=None):
    """Enregistre un événement pédagogique unique (usage backend)."""
    from django.utils import timezone
    from analytics.models import LearningEvent

    et = normalize_event_type(event_type)
    payload = dict(metadata or {})
    if event_type and et != event_type:
        payload.setdefault('raw_event_type', str(event_type)[:64])

    try:
        return LearningEvent.objects.create(
            apprenant=apprenant,
            cours=cours, module=module, sequence=sequence, bloc=bloc,
            ressource=ressource, session=session,
            trace_id=str(trace_id or '')[:64],
            event_type=et,
            ts=ts or timezone.now(),
            duree_ms=int(duree_ms or 0),
            source=str(source or '')[:32],
            payload=payload,
        )
    except Exception as exc:  # ne jamais casser l'appelant
        logger.warning('[event] échec enregistrement %s : %s', event_type, exc)
        return None
