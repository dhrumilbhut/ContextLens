from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "contextlens",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks", "app.worker.scheduled_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "check-volume-spikes-hourly": {
        "task": "app.worker.scheduled_tasks.check_for_volume_spikes",
        "schedule": crontab(minute=0),  # every hour on the hour
    },
    "reprocess-pending-traces-daily": {
        "task": "app.worker.scheduled_tasks.reprocess_pending_traces",
        "schedule": crontab(hour=0, minute=5),  # daily at 00:05 UTC
    },
    "cluster-queries-every-6-hours": {
        "task": "app.worker.scheduled_tasks.cluster_project_queries_all",
        "schedule": crontab(minute=0, hour="*/6"),  # 00:00, 06:00, 12:00, 18:00 UTC
    },
}
