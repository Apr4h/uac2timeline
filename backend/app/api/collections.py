"""
Collection management endpoints:
  POST /api/collections/upload  – upload ZIP/tar.gz, start processing
  GET  /api/collections         – list all
  GET  /api/collections/{id}    – detail
  DELETE /api/collections/{id}  – remove
  GET  /api/jobs/{id}           – processing job detail
  GET  /api/jobs/{id}/logs      – all log lines for a job
"""
from __future__ import annotations

import os
import shutil
import tarfile
import uuid
import zipfile
import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.config import UPLOAD_DIR, PARSE_THRESHOLD
from backend.app.database import get_db
from backend.app.models import ProcessingJob, ArtifactJob, ProcessingLog
from backend.app.schemas import (
    CollectionOut, UploadResponse,
    ProcessingJobOut, ProcessingLogOut,
)
from uac_parser.models import (
    UACCollection, Process, NetworkConnection,
    Authentication, CommandHistory, User, CronJob, SystemdService,
)
from uac_parser.parser import get_collection_metadata

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collection_out(col: UACCollection, db: Session) -> CollectionOut:
    counts = {
        "process_count": db.query(func.count(Process.id)).filter_by(collection_id=col.id).scalar() or 0,
        "netconn_count": db.query(func.count(NetworkConnection.id)).filter_by(collection_id=col.id).scalar() or 0,
        "auth_count": db.query(func.count(Authentication.id)).filter_by(collection_id=col.id).scalar() or 0,
        "cmdhistory_count": db.query(func.count(CommandHistory.id)).filter_by(collection_id=col.id).scalar() or 0,
        "user_count": db.query(func.count(User.id)).filter_by(collection_id=col.id).scalar() or 0,
        "cron_count": db.query(func.count(CronJob.id)).filter_by(collection_id=col.id).scalar() or 0,
        "systemd_count": db.query(func.count(SystemdService.id)).filter_by(collection_id=col.id).scalar() or 0,
    }
    latest_job = (
        db.query(ProcessingJob)
        .filter_by(collection_id=col.id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )
    return CollectionOut(
        id=col.id,
        hostname=col.hostname,
        os=col.os,
        timezone_setting=col.timezone_setting,
        primary_ip_address=col.primary_ip_address,
        created_at=col.created_at,
        uac_log_md5=col.uac_log_md5,
        latest_job=ProcessingJobOut.model_validate(latest_job) if latest_job else None,
        **counts,
    )


def _extract_archive(src: Path, dest: Path) -> Path:
    """Extract zip or tar.gz to dest; return the root of the UAC collection."""
    dest.mkdir(parents=True, exist_ok=True)

    if src.suffix == ".zip" or (src.suffixes and src.suffixes[-1] == ".zip"):
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(dest)
    elif str(src).endswith((".tar.gz", ".tgz")):
        with tarfile.open(src, 'r:gz') as tf:
            tf.extractall(dest)
    elif str(src).endswith(".tar"):
        with tarfile.open(src, 'r') as tf:
            tf.extractall(dest)
    else:
        raise ValueError(f"Unsupported archive format: {src.name}")

    # If the archive unpacked into a single sub-directory, descend into it
    entries = list(dest.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return dest


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/collections/upload", response_model=UploadResponse, status_code=201)
async def upload_collection(
    file: UploadFile = File(...),
    threshold: int = Query(default=PARSE_THRESHOLD, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filename = file.filename or "upload"
    # Path.suffix only returns the last extension (.gz for .tar.gz), so build
    # the full compound suffix explicitly for multi-part extensions.
    _p = Path(filename)
    if len(_p.suffixes) >= 2 and _p.suffixes[-2] == ".tar":
        suffix = "".join(_p.suffixes[-2:])   # e.g. ".tar.gz", ".tar.bz2"
    else:
        suffix = _p.suffix                    # e.g. ".zip", ".tgz", ".tar"

    if suffix not in (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar"):
        raise HTTPException(status_code=400, detail="Upload must be a .zip or .tar.gz archive")

    run_id = str(uuid.uuid4())
    archive_path = Path(UPLOAD_DIR) / f"{run_id}{suffix}"
    extract_path = Path(UPLOAD_DIR) / run_id

    # Save upload to disk
    with open(archive_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    # Extract
    try:
        collection_root = _extract_archive(archive_path, extract_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to extract archive: {exc}")

    # Read UAC metadata
    metadata = get_collection_metadata(str(collection_root))
    if not metadata:
        raise HTTPException(status_code=422, detail="Could not parse uac.log — is this a valid UAC collection?")

    # Duplicate check
    if metadata.get("uac_log_md5"):
        existing = (
            db.query(UACCollection)
            .filter_by(uac_log_md5=metadata["uac_log_md5"])
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Collection already exists (hostname={existing.hostname}, id={existing.id})",
            )

    # Create UACCollection
    col = UACCollection(**metadata)
    db.add(col)
    db.flush()

    # Create ProcessingJob
    pjob = ProcessingJob(
        collection_id=col.id,
        status="pending",
        upload_path=str(collection_root),
        created_at=datetime.datetime.utcnow(),
    )
    db.add(pjob)
    db.commit()
    db.refresh(col)
    db.refresh(pjob)

    # Dispatch Celery
    from backend.app.tasks.parsers import process_collection
    process_collection.delay(
        job_id=pjob.id,
        collection_path=str(collection_root),
        collection_id=col.id,
        collection_os=metadata.get("os"),
        threshold=threshold,
    )

    return UploadResponse(
        collection_id=col.id,
        job_id=pjob.id,
        message=f"Collection '{metadata.get('hostname')}' queued for processing",
    )


# ── Collection CRUD ───────────────────────────────────────────────────────────

@router.get("/collections", response_model=list[CollectionOut])
def list_collections(db: Session = Depends(get_db)):
    cols = db.query(UACCollection).order_by(UACCollection.created_at.desc()).all()
    return [_collection_out(c, db) for c in cols]


@router.get("/collections/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: int, db: Session = Depends(get_db)):
    col = db.query(UACCollection).filter_by(id=collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _collection_out(col, db)


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: int, db: Session = Depends(get_db)):
    col = db.query(UACCollection).filter_by(id=collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Delete all artifact rows
    db.query(Process).filter_by(collection_id=collection_id).delete()
    db.query(NetworkConnection).filter_by(collection_id=collection_id).delete()
    db.query(Authentication).filter_by(collection_id=collection_id).delete()
    db.query(CommandHistory).filter_by(collection_id=collection_id).delete()
    db.query(User).filter_by(collection_id=collection_id).delete()
    db.query(CronJob).filter_by(collection_id=collection_id).delete()
    db.query(SystemdService).filter_by(collection_id=collection_id).delete()

    # Delete processing jobs (cascade handles artifact_jobs + logs)
    for pjob in db.query(ProcessingJob).filter_by(collection_id=collection_id).all():
        # Clean up extracted files
        if pjob.upload_path:
            extract_dir = Path(pjob.upload_path)
            parent = extract_dir.parent
            if parent.exists() and str(parent).startswith(UPLOAD_DIR):
                shutil.rmtree(parent, ignore_errors=True)
        db.delete(pjob)

    db.delete(col)
    db.commit()


# ── Job endpoints ─────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=ProcessingJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(ProcessingJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/logs", response_model=list[ProcessingLogOut])
def get_job_logs(
    job_id: int,
    artifact_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    job = db.query(ProcessingJob).filter_by(id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if artifact_type:
        aj = db.query(ArtifactJob).filter_by(processing_job_id=job_id, artifact_type=artifact_type).first()
        if not aj:
            return []
        logs = db.query(ProcessingLog).filter_by(artifact_job_id=aj.id).order_by(ProcessingLog.timestamp).all()
    else:
        logs = db.query(ProcessingLog).filter_by(processing_job_id=job_id).order_by(ProcessingLog.timestamp).all()

    return logs
