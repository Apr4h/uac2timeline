redis:   docker run --rm -p 6379:6379 redis:alpine
api:     uvicorn backend.app.main:app --reload --port 8000
worker:  celery -A backend.app.tasks.celery_app worker --loglevel=info
frontend: bash -c "cd frontend && npm run dev"
