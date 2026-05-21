"""
Timeline and per-artifact query endpoints.

GET /api/collections/{id}/timeline
GET /api/collections/{id}/processes
GET /api/collections/{id}/netconns
GET /api/collections/{id}/auth
GET /api/collections/{id}/cmdhistory
GET /api/collections/{id}/users
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Tagging
from backend.app.schemas import (
    TimelineEvent, TimelineResponse,
    PaginatedProcesses, PaginatedNetconns, PaginatedAuth,
    PaginatedCmdHistory, PaginatedUsers, PaginatedFiles, PaginatedCronJobs,
    PaginatedSystemdServices, PaginatedRcScripts,
    ProcessOut, NetworkConnectionOut, AuthenticationOut,
    CommandHistoryOut, UserOut, FileOut, SystemInfoOut, CronJobOut,
    SystemdServiceOut, RcScriptOut, FilePreviewResponse,
)
from uac_parser.models import (
    UACCollection, Process, NetworkConnection,
    Authentication, CommandHistory, User, File, SystemInfo, CronJob,
    SystemdService, RcScript,
)

router = APIRouter()

ALL_TYPES = {"processes", "netconns", "auth", "cmdhistory", "files", "cron", "services", "rcscripts"}


def _require_collection(collection_id: int, db: Session) -> UACCollection:
    col = db.query(UACCollection).filter_by(id=collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return col


def _apply_filter(text: str | None, filter_str: str | None, regex: str | None) -> bool:
    """Return True if text passes the active filters."""
    if text is None:
        text = ""
    if filter_str and filter_str.lower() not in text.lower():
        return False
    if regex:
        try:
            if not re.search(regex, text, re.IGNORECASE):
                return False
        except re.error:
            pass
    return True


def _process_summary(p: Process) -> str:
    parts = [p.command or ""]
    if p.arguments:
        parts.append(p.arguments)
    summary = " ".join(parts).strip()
    if p.user:
        summary = f"[{p.user}] {summary}"
    return summary


def _auth_summary(a: Authentication) -> str:
    parts = []
    if a.result:
        parts.append(a.result.upper())
    if a.method:
        parts.append(a.method)
    if a.username:
        parts.append(f"for {a.username}")
    if a.source:
        parts.append(f"from {a.source}")
    return " ".join(parts) or "authentication event"


def _cmdhistory_summary(c: CommandHistory) -> str:
    user = f"[{c.user}] " if c.user else ""
    return f"{user}{c.command or ''}"


def _obj_to_dict(obj) -> dict[str, Any]:
    """Serialize an ORM object to a plain dict (excluding SQLAlchemy internals)."""
    result = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.strftime('%Y-%m-%dT%H:%M:%SZ')
        result[col.name] = val
    return result


def _filter_by_tags(query, model, artifact_type: str, db: Session, collection_id: int, tag_ids_str: str | None):
    """Restrict query to rows tagged with any of the given tag IDs (OR logic)."""
    if not tag_ids_str:
        return query
    ids = [int(x) for x in tag_ids_str.split(',') if x.strip().isdigit()]
    if not ids:
        return query
    sub = (
        db.query(Tagging.artifact_id)
          .filter(
              Tagging.collection_id == collection_id,
              Tagging.artifact_type == artifact_type,
              Tagging.tag_id.in_(ids),
          )
          .subquery()
    )
    return query.filter(model.id.in_(sub))


# ── Unified timeline ──────────────────────────────────────────────────────────

@router.get("/collections/{collection_id}/timeline", response_model=TimelineResponse)
def get_timeline(
    collection_id: int,
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    types: Optional[str] = Query(default=None, description="Comma-separated: processes,netconns,auth,cmdhistory"),
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None, description="Comma-separated tag IDs (OR logic)"),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)

    requested_types = {t.strip() for t in types.split(",")} if types else ALL_TYPES

    events: list[TimelineEvent] = []

    # Processes
    if "processes" in requested_types:
        q = db.query(Process).filter_by(collection_id=collection_id)
        if start:
            q = q.filter(Process.started >= start)
        if end:
            q = q.filter(Process.started <= end)
        q = _filter_by_tags(q, Process, "processes", db, collection_id, tag_ids)
        for p in q.all():
            summary = _process_summary(p)
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=p.started,
                artifact_type="processes",
                id=p.id,
                summary=summary,
                details=_obj_to_dict(p),
            ))

    # Authentications
    if "auth" in requested_types:
        q = db.query(Authentication).filter_by(collection_id=collection_id)
        if start:
            q = q.filter(Authentication.time >= start)
        if end:
            q = q.filter(Authentication.time <= end)
        q = _filter_by_tags(q, Authentication, "auth", db, collection_id, tag_ids)
        for a in q.all():
            summary = _auth_summary(a)
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=a.time,
                artifact_type="auth",
                id=a.id,
                summary=summary,
                details=_obj_to_dict(a),
            ))

    # Command history
    if "cmdhistory" in requested_types:
        q = db.query(CommandHistory).filter_by(collection_id=collection_id)
        if start:
            q = q.filter(CommandHistory.time >= start)
        if end:
            q = q.filter(CommandHistory.time <= end)
        q = _filter_by_tags(q, CommandHistory, "cmdhistory", db, collection_id, tag_ids)
        for c in q.all():
            summary = _cmdhistory_summary(c)
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=c.time,
                artifact_type="cmdhistory",
                id=c.id,
                summary=summary,
                details=_obj_to_dict(c),
            ))

    # Cron jobs — use source_file_modified as the timeline timestamp
    if "cron" in requested_types:
        q = db.query(CronJob).filter_by(collection_id=collection_id)
        if start:
            q = q.filter(CronJob.source_file_modified >= start)
        if end:
            q = q.filter(CronJob.source_file_modified <= end)
        q = _filter_by_tags(q, CronJob, "cron", db, collection_id, tag_ids)
        for cj in q.all():
            if cj.source_file_modified is None and (start or end):
                continue
            user = f"{cj.username}: " if cj.username else ""
            summary = f"[{cj.source_type or 'cron'}] {user}{cj.command or ''}"
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=cj.source_file_modified,
                artifact_type="cron",
                id=cj.id,
                summary=summary,
                details=_obj_to_dict(cj),
            ))

    # Systemd units — use source_file_modified as the timeline timestamp
    if "services" in requested_types:
        q = db.query(SystemdService).filter_by(collection_id=collection_id)
        if start:
            q = q.filter(SystemdService.source_file_modified >= start)
        if end:
            q = q.filter(SystemdService.source_file_modified <= end)
        q = _filter_by_tags(q, SystemdService, "services", db, collection_id, tag_ids)
        for svc in q.all():
            if svc.source_file_modified is None and (start or end):
                continue
            label = f"{svc.unit_name or ''}.{svc.unit_type or ''}".strip('.')
            detail = svc.description or svc.exec_start or ''
            summary = f"[{svc.source_dir_type or 'services'}] {label}: {detail}".rstrip(': ')
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=svc.source_file_modified,
                artifact_type="services",
                id=svc.id,
                summary=summary,
                details=_obj_to_dict(svc),
            ))

    # RC scripts — use source_file_modified as the timeline timestamp
    if "rcscripts" in requested_types:
        q = db.query(RcScript).filter_by(collection_id=collection_id)
        if start:
            q = q.filter(RcScript.source_file_modified >= start)
        if end:
            q = q.filter(RcScript.source_file_modified <= end)
        q = _filter_by_tags(q, RcScript, "rcscripts", db, collection_id, tag_ids)
        for rc in q.all():
            if rc.source_file_modified is None and (start or end):
                continue
            user_part = f"{rc.username}: " if rc.username else ""
            summary = f"[{rc.source_type or 'rcscript'}] {user_part}{rc.path or ''}"
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=rc.source_file_modified,
                artifact_type="rcscripts",
                id=rc.id,
                summary=summary,
                details=_obj_to_dict(rc),
            ))

    # Filesystem events — each file contributes up to 4 events (one per timestamp type)
    if "files" in requested_types:
        _TS_LABELS = [("mtime", "M"), ("atime", "A"), ("ctime", "C"), ("crtime", "B")]
        q = db.query(File).filter_by(collection_id=collection_id)
        q = _filter_by_tags(q, File, "files", db, collection_id, tag_ids)
        for f in q.all():
            for attr, label in _TS_LABELS:
                ts = getattr(f, attr)
                if ts is None:
                    continue
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                summary = f"[{label}] {f.path or ''}"
                if not _apply_filter(summary, filter, regex):
                    continue
                events.append(TimelineEvent(
                    timestamp=ts,
                    artifact_type="files",
                    id=f.id,
                    summary=summary,
                    details=_obj_to_dict(f),
                ))

    # Network connections (no timestamp — include only when explicitly requested)
    if "netconns" in requested_types and not start and not end:
        q = db.query(NetworkConnection).filter_by(collection_id=collection_id)
        q = _filter_by_tags(q, NetworkConnection, "netconns", db, collection_id, tag_ids)
        for nc in q.all():
            summary = f"{nc.proto} {nc.local_addr}:{nc.local_port} → {nc.remote_addr}:{nc.remote_port} [{nc.state}]"
            if not _apply_filter(summary, filter, regex):
                continue
            events.append(TimelineEvent(
                timestamp=None,
                artifact_type="netconns",
                id=nc.id,
                summary=summary,
                details=_obj_to_dict(nc),
            ))

    # Sort: events with timestamps first (ascending), then timestampless
    events.sort(key=lambda e: (e.timestamp is None, e.timestamp or datetime.min))

    total = len(events)
    page = events[offset: offset + limit]

    return TimelineResponse(total=total, offset=offset, limit=limit, events=page)


# ── Per-artifact endpoints ────────────────────────────────────────────────────

@router.get("/collections/{collection_id}/processes", response_model=PaginatedProcesses)
def get_processes(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(Process).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, Process, "processes", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(_process_summary(r), filter, regex)]
    total = len(rows)
    return PaginatedProcesses(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/netconns", response_model=PaginatedNetconns)
def get_netconns(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(NetworkConnection).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, NetworkConnection, "netconns", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(
            f"{r.proto} {r.local_addr}:{r.local_port} {r.remote_addr}:{r.remote_port} {r.state}",
            filter, regex,
        )]
    total = len(rows)
    return PaginatedNetconns(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/auth", response_model=PaginatedAuth)
def get_auth(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(Authentication).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, Authentication, "auth", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(_auth_summary(r), filter, regex)]
    total = len(rows)
    return PaginatedAuth(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/cmdhistory", response_model=PaginatedCmdHistory)
def get_cmdhistory(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(CommandHistory).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, CommandHistory, "cmdhistory", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(_cmdhistory_summary(r), filter, regex)]
    total = len(rows)
    return PaginatedCmdHistory(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/users", response_model=PaginatedUsers)
def get_users(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(User).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, User, "users", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(
            f"{r.username} {r.shell} {r.home}",
            filter, regex,
        )]
    total = len(rows)
    return PaginatedUsers(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/cron", response_model=PaginatedCronJobs)
def get_cron(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(CronJob).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, CronJob, "cron", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(
            f"{r.username or ''} {r.command or ''} {r.source_file or ''} {r.source_type or ''}",
            filter, regex,
        )]
    total = len(rows)
    return PaginatedCronJobs(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/services", response_model=PaginatedSystemdServices)
def get_systemd(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(SystemdService).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, SystemdService, "services", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(
            f"{r.unit_name or ''} {r.description or ''} {r.exec_start or ''} {r.run_user or ''} {r.source_path or ''}",
            filter, regex,
        )]
    total = len(rows)
    return PaginatedSystemdServices(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/rcscripts", response_model=PaginatedRcScripts)
def get_rcscripts(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(RcScript).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, RcScript, "rcscripts", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(
            f"{r.path or ''} {r.source_type or ''} {r.run_context or ''} {r.username or ''} {r.shell or ''}",
            filter, regex,
        )]
    total = len(rows)
    return PaginatedRcScripts(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


_PREVIEW_SIZE_CAP = 512 * 1024  # 512 KB


@router.get("/collections/{collection_id}/file-preview", response_model=FilePreviewResponse)
def get_file_preview(
    collection_id: int,
    path: str = Query(..., description="Logical filesystem path, e.g. /etc/rc.local"),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)

    from backend.app.models import ProcessingJob
    pjob = (
        db.query(ProcessingJob)
        .filter_by(collection_id=collection_id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )
    if not pjob or not pjob.upload_path:
        raise HTTPException(status_code=404, detail="Collection files not available")

    root_dir = os.path.join(pjob.upload_path, "[root]")
    # Strip leading slash so os.path.join doesn't treat it as absolute
    rel_path = path.lstrip("/")
    candidate = os.path.realpath(os.path.join(root_dir, rel_path))
    # Path traversal guard
    if not candidate.startswith(os.path.realpath(root_dir) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")

    if not os.path.isfile(candidate):
        return FilePreviewResponse(path=path, available=False)

    size = os.path.getsize(candidate)

    # Binary detection
    try:
        with open(candidate, "rb") as f:
            chunk = f.read(512)
        if b"\x00" in chunk:
            return FilePreviewResponse(path=path, available=True, binary=True, size=size)
    except OSError:
        return FilePreviewResponse(path=path, available=False)

    # Text read with size cap
    truncated = size > _PREVIEW_SIZE_CAP
    try:
        with open(candidate, "r", errors="replace") as f:
            content = f.read(_PREVIEW_SIZE_CAP)
    except OSError:
        return FilePreviewResponse(path=path, available=False)

    return FilePreviewResponse(
        path=path,
        available=True,
        binary=False,
        content=content,
        size=size,
        truncated=truncated,
    )


@router.get("/collections/{collection_id}/system-info", response_model=SystemInfoOut)
def get_system_info(
    collection_id: int,
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    info = db.query(SystemInfo).filter_by(collection_id=collection_id).first()
    if not info:
        raise HTTPException(status_code=404, detail="System info not yet available")
    return info


@router.get("/collections/{collection_id}/files", response_model=PaginatedFiles)
def get_files(
    collection_id: int,
    filter: Optional[str] = Query(default=None, alias="filter"),
    regex: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(File).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, File, "files", db, collection_id, tag_ids)
    rows = q.all()
    if filter or regex:
        rows = [r for r in rows if _apply_filter(r.path or "", filter, regex)]
    total = len(rows)
    return PaginatedFiles(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])
