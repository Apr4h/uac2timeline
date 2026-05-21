from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.collections import router as collections_router
from backend.app.api.timeline import router as timeline_router
from backend.app.api.tags import router as tags_router
from backend.app.api.notes import router as notes_router
from backend.app.database import engine  # call once to create all tables

# Ensure tables exist
engine()

app = FastAPI(title="uac2timeline", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collections_router, prefix="/api")
app.include_router(timeline_router, prefix="/api")
app.include_router(tags_router, prefix="/api")
app.include_router(notes_router, prefix="/api")

# Serve built Vue frontend — only when the dist directory exists
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
