from celery import Celery
from backend.app.config import BROKER_DIR, RESULTS_DIR

celery = Celery(
    "uac2timeline",
    broker="filesystem://",
    backend=f"file://{RESULTS_DIR}",
    include=["backend.app.tasks.parsers"],
)

celery.conf.update(
    broker_transport_options={
        "data_folder_in":  BROKER_DIR,
        "data_folder_out": BROKER_DIR,
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
