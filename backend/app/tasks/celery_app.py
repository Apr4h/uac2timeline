from celery import Celery
from backend.app.config import REDIS_URL

celery = Celery(
    "uac2timeline",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["backend.app.tasks.parsers"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
