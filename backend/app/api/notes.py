"""
Note management endpoints.

GET    /api/collections/{id}/notes   list all notes for a collection
POST   /api/notes                    upsert (create or update) one note per artifact_id
DELETE /api/notes                    delete notes for given artifact_ids
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Note
from backend.app.schemas import NoteOut, NoteUpsert, NoteDelete

router = APIRouter()

_MAX_CONTENT = 500


@router.get("/collections/{collection_id}/notes", response_model=list[NoteOut])
def list_notes(collection_id: int, db: Session = Depends(get_db)):
    return db.query(Note).filter_by(collection_id=collection_id).all()


@router.post("/notes", response_model=list[NoteOut], status_code=200)
def upsert_notes(body: NoteUpsert, db: Session = Depends(get_db)):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Note content cannot be empty")
    if len(content) > _MAX_CONTENT:
        raise HTTPException(status_code=422, detail=f"Note content exceeds {_MAX_CONTENT} characters")

    now = datetime.datetime.utcnow()
    results: list[Note] = []

    for artifact_id in body.artifact_ids:
        note = db.query(Note).filter_by(
            artifact_type=body.artifact_type,
            artifact_id=artifact_id,
        ).first()
        if note:
            note.content    = content
            note.updated_at = now
        else:
            note = Note(
                collection_id=body.collection_id,
                artifact_type=body.artifact_type,
                artifact_id=artifact_id,
                content=content,
                created_at=now,
                updated_at=now,
            )
            db.add(note)
        results.append(note)

    db.commit()
    for n in results:
        db.refresh(n)
    return results


@router.delete("/notes", status_code=204)
def delete_notes(body: NoteDelete, db: Session = Depends(get_db)):
    db.query(Note).filter(
        Note.artifact_type == body.artifact_type,
        Note.artifact_id.in_(body.artifact_ids),
    ).delete(synchronize_session=False)
    db.commit()
