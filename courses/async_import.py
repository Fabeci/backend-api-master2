# courses/async_import.py
# =============================================================================
# Création de cours en arrière-plan (import volumineux).
#
# Le worker Celery est optionnel dans docker-compose ; pour que l'import
# asynchrone fonctionne dans tous les déploiements, on utilise un thread
# daemon et un état partagé dans le cache Django. Le passage à Celery est
# possible en remplaçant `_executer` par une tâche `shared_task` sans changer
# l'API HTTP ni le frontend.
# =============================================================================

import logging
import threading
import uuid
from collections import Counter

from django.core.cache import cache
from django.db import close_old_connections

from courses import import_course

logger = logging.getLogger(__name__)

CACHE_PREFIX = "import_cours:"
CACHE_TTL = 3600  # 1 heure


def _key(task_id: str) -> str:
    return f"{CACHE_PREFIX}{task_id}"


def _update(task_id: str, **fields) -> None:
    data = cache.get(_key(task_id)) or {}
    data.update(fields)
    cache.set(_key(task_id), data, CACHE_TTL)


def _stats(modules) -> dict:
    return {
        "modules": len(modules),
        "sequences": sum(len(m.get("sequences") or []) for m in modules),
        "blocs": sum(len(s.get("blocs") or []) for m in modules for s in (m.get("sequences") or [])),
        "quizzes": sum(len(s.get("quizzes") or []) for m in modules for s in (m.get("sequences") or [])),
        "questions": sum(
            len(q.get("questions") or [])
            for m in modules for s in (m.get("sequences") or [])
            for q in (s.get("quizzes") or [])
        ),
    }


def _executer(task_id: str, user_id: int, meta: dict, modules: list) -> None:
    close_old_connections()
    try:
        _update(task_id, status="running", progress=10, message="Préparation du cours…")

        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(pk=user_id)

        tree = {
            "titre": meta.get("titre") or "Cours importé",
            "modules": modules,
            "warnings": [],
            "stats": _stats(modules),
        }

        _update(task_id, progress=35, message="Création des modules et séquences…")
        cours = import_course.create_course_from_tree(user, meta, tree)

        _update(
            task_id,
            status="success",
            progress=100,
            message="Cours importé.",
            result={
                "cours_id": cours.id,
                "titre": cours.titre,
                "stats": tree["stats"],
                "warnings": tree["warnings"],
            },
        )
    except Exception as exc:
        logger.exception("Import asynchrone du cours échoué (tâche %s)", task_id)
        _update(
            task_id,
            status="error",
            progress=100,
            message="L'import a échoué.",
            error=str(exc),
        )
    finally:
        close_old_connections()


def _worker_celery_disponible() -> bool:
    try:
        # SQLite ne supporte pas les écritures concurrentes entre le worker
        # Celery et l'API : on garde le thread local dans ce mode.
        from django.db import connection
        if connection.vendor == "sqlite":
            return False
        from master_backend_api.celery import app
        return bool(app.control.ping(timeout=0.4))
    except Exception:
        return False


def lancer_creation_cours(meta: dict, modules: list, user_id: int) -> str:
    """Démarre la création et retourne immédiatement un identifiant de tâche.

    Utilise Celery si un worker répond ; sinon un thread daemon assure le
    fonctionnement en développement ou sans profil `celery`.
    """
    task_id = uuid.uuid4().hex
    cache.set(
        _key(task_id),
        {
            "task_id": task_id,
            "user_id": user_id,
            "status": "pending",
            "progress": 0,
            "message": "Import en file d'attente…",
            "result": None,
            "error": None,
        },
        CACHE_TTL,
    )
    if _worker_celery_disponible():
        try:
            from courses.tasks import importer_cours
            importer_cours.delay(task_id, user_id, meta, modules)
            return task_id
        except Exception:
            logger.exception("Envoi de la tâche Celery impossible, repli sur un thread")

    thread = threading.Thread(
        target=_executer,
        args=(task_id, user_id, meta, modules),
        name=f"import-cours-{task_id[:8]}",
        daemon=True,
    )
    thread.start()
    return task_id


def statut_import(task_id: str) -> dict | None:
    return cache.get(_key(task_id))
