# courses/tasks.py
# Tâche Celery d'import de cours. Découverte automatique par
# `app.autodiscover_tasks()` (module `tasks` de l'app `courses`).

from celery import shared_task


@shared_task(name="importer_cours")
def importer_cours(task_id: str, user_id: int, meta: dict, modules: list):
    # Import différé pour éviter tout cycle au chargement des modules.
    from courses.async_import import _executer
    _executer(task_id, user_id, meta, modules)
