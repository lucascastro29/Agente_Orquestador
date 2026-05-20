import os
from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "agente_orquestador",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Beat schedule — watchers (Fase 6)
    beat_schedule={
        "check-mail-every-15min": {
            "task": "watchers.check_mail",
            "schedule": crontab(minute="*/15"),
        },
        "check-calendar-every-30min": {
            "task": "watchers.check_calendar",
            "schedule": crontab(minute="*/30"),
        },
        "run-scheduled-tasks-every-min": {
            "task": "workers.run_due_scheduled_tasks",
            "schedule": crontab(minute="*"),
        },
    },
    # Registrar módulos de tasks para que beat los encuentre
    imports=[
        "app.workers.tasks",
        "app.watchers.mail_watcher",
        "app.watchers.calendar_watcher",
    ],
)
