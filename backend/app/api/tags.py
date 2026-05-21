"""
Tag management and tagging endpoints.

GET    /api/tags                          list all tags
POST   /api/tags                          create tag
PATCH  /api/tags/{id}                     rename / recolor
DELETE /api/tags/{id}                     delete tag + all its taggings

GET    /api/collections/{id}/taggings     all taggings for a collection
POST   /api/taggings                      apply tag to one or more artifact rows (idempotent)
DELETE /api/taggings                      remove tag from one or more artifact rows
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Tag, Tagging
from backend.app.schemas import (
    TagOut, TagCreate, TagUpdate,
    TaggingOut, TaggingApply, TaggingRemove,
)

router = APIRouter()

VALID_ARTIFACT_TYPES = {"processes", "auth", "cmdhistory", "netconns", "files", "users", "cron", "services"}
VALID_COLORS = {"red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "gray"}


def _get_tag_or_404(tag_id: int, db: Session) -> Tag:
    tag = db.query(Tag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


# ── Tag CRUD ──────────────────────────────────────────────────────────────────

@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)):
    return db.query(Tag).order_by(Tag.is_default.desc(), Tag.name).all()


@router.post("/tags", response_model=TagOut, status_code=201)
def create_tag(body: TagCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Tag name cannot be empty")
    color = body.color if body.color in VALID_COLORS else "gray"
    if db.query(Tag).filter_by(name=name).first():
        raise HTTPException(status_code=409, detail="A tag with that name already exists")
    tag = Tag(name=name, color=color, is_default=False)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.patch("/tags/{tag_id}", response_model=TagOut)
def update_tag(tag_id: int, body: TagUpdate, db: Session = Depends(get_db)):
    tag = _get_tag_or_404(tag_id, db)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Tag name cannot be empty")
        existing = db.query(Tag).filter(Tag.name == name, Tag.id != tag_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="A tag with that name already exists")
        tag.name = name
    if body.color is not None:
        tag.color = body.color if body.color in VALID_COLORS else tag.color
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = _get_tag_or_404(tag_id, db)
    db.delete(tag)
    db.commit()


# ── Taggings ──────────────────────────────────────────────────────────────────

@router.get("/collections/{collection_id}/taggings", response_model=list[TaggingOut])
def list_collection_taggings(collection_id: int, db: Session = Depends(get_db)):
    return db.query(Tagging).filter_by(collection_id=collection_id).all()


@router.post("/taggings", response_model=list[TaggingOut], status_code=201)
def apply_taggings(body: TaggingApply, db: Session = Depends(get_db)):
    _get_tag_or_404(body.tag_id, db)
    if body.artifact_type not in VALID_ARTIFACT_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid artifact_type '{body.artifact_type}'")
    if not body.artifact_ids:
        raise HTTPException(status_code=422, detail="artifact_ids cannot be empty")

    # Derive collection_id from the first artifact row; validate all belong to same collection.
    collection_id = _resolve_collection_id(body.artifact_type, body.artifact_ids, db)

    artifact_ids = list(dict.fromkeys(body.artifact_ids))  # deduplicate, preserve order

    created = []
    for aid in artifact_ids:
        existing = db.query(Tagging).filter_by(
            tag_id=body.tag_id,
            artifact_type=body.artifact_type,
            artifact_id=aid,
        ).first()
        if existing:
            created.append(existing)
            continue
        t = Tagging(
            tag_id=body.tag_id,
            artifact_type=body.artifact_type,
            artifact_id=aid,
            collection_id=collection_id,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(t)
        created.append(t)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate tagging conflict")

    for t in created:
        db.refresh(t)
    return created


@router.delete("/taggings", status_code=204)
def remove_taggings(body: TaggingRemove, db: Session = Depends(get_db)):
    if body.artifact_type not in VALID_ARTIFACT_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid artifact_type '{body.artifact_type}'")
    db.query(Tagging).filter(
        Tagging.tag_id == body.tag_id,
        Tagging.artifact_type == body.artifact_type,
        Tagging.artifact_id.in_(body.artifact_ids),
    ).delete(synchronize_session=False)
    db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_collection_id(artifact_type: str, artifact_ids: list[int], db: Session) -> int:
    """Look up the collection_id for the given artifact rows."""
    from uac_parser.models import Process, NetworkConnection, Authentication, CommandHistory, File, User, CronJob, SystemdService
    _MODEL_MAP = {
        "processes":  Process,
        "netconns":   NetworkConnection,
        "auth":       Authentication,
        "cmdhistory": CommandHistory,
        "files":      File,
        "users":      User,
        "cron":       CronJob,
        "services":   SystemdService,
    }
    model = _MODEL_MAP[artifact_type]
    row = db.query(model).filter(model.id == artifact_ids[0]).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Artifact row {artifact_ids[0]} not found")
    return row.collection_id
