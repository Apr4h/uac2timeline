api:    uvicorn backend.app.main:app --reload --port 8000
worker: celery -A backend.app.tasks.celery_app worker --loglevel=info
