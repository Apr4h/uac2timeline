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

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import union_all as sa_union_all, select, literal, func, case as sa_case, null
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Tagging
from backend.app.schemas import (
    TimelineEvent, TimelineResponse,
    PaginatedProcesses, PaginatedNetconns, PaginatedAuth,
    PaginatedCmdHistory, PaginatedUsers, PaginatedFiles, PaginatedCronJobs,
    PaginatedSystemdServices, PaginatedRcScripts, PaginatedSyslog,
    ProcessOut, NetworkConnectionOut, AuthenticationOut,
    CommandHistoryOut, UserOut, FileOut, SystemInfoOut, CronJobOut,
    SystemdServiceOut, RcScriptOut, SyslogEntryOut, FilePreviewResponse,
)
from uac_parser.models import (
    UACCollection, Process, NetworkConnection,
    Authentication, CommandHistory, User, File, SystemInfo, CronJob,
    SystemdService, RcScript, SyslogEntry,
)

router = APIRouter()

ALL_TYPES = {"processes", "netconns", "auth", "cmdhistory", "files", "cron", "services", "rcscripts", "syslog"}


def _require_collection(collection_id: int, db: Session) -> UACCollection:
    col = db.query(UACCollection).filter_by(id=collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    return col


def _parse_col_filters(s: str | None) -> list[dict]:
    """Decode JSON col_filters query param. Returns [] on any parse error."""
    if not s:
        return []
    try:
        rules = json.loads(s)
        return [r for r in rules if r.get("col") and r.get("pattern")]
    except (json.JSONDecodeError, TypeError):
        return []


_TIMELINE_TOP_FIELDS = {"hostname", "ts_description", "summary", "assoc_user", "source_ip", "dest_ip", "md5"}


def _match_rule(val: str, pattern: str, is_regex: bool, mode: str) -> bool:
    """Return True if val passes a single filter rule."""
    if is_regex:
        try:
            matched = bool(re.search(pattern, val, re.IGNORECASE))
        except re.error:
            matched = False
    else:
        matched = pattern.lower() in val.lower()
    if mode == "inc":
        return matched
    return not matched  # exc


def _apply_col_filters_event(ev: "TimelineEvent", col_filters: list[dict]) -> bool:
    """Return True if a TimelineEvent passes all column filter rules (AND)."""
    for rule in col_filters:
        col = rule["col"]
        pattern = rule["pattern"]
        is_regex = rule.get("isRegex", False)
        mode = rule.get("mode", "inc")
        if col == "type":
            val = ev.artifact_type or ""
        elif col in _TIMELINE_TOP_FIELDS:
            val = str(getattr(ev, col) or "")
        else:
            val = str(ev.details.get(col) or "")
        if not _match_rule(val, pattern, is_regex, mode):
            return False
    return True


def _apply_col_filters_obj(obj, col_filters: list[dict]) -> bool:
    """Return True if an ORM object passes all column filter rules (AND)."""
    for rule in col_filters:
        col = rule["col"]
        pattern = rule["pattern"]
        is_regex = rule.get("isRegex", False)
        mode = rule.get("mode", "inc")
        val = str(getattr(obj, col, None) or "")
        if not _match_rule(val, pattern, is_regex, mode):
            return False
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


def _syslog_summary(s: SyslogEntry) -> str:
    prog = f"{s.program}[{s.pid}]" if s.pid else (s.program or "")
    host = f"{s.hostname} " if s.hostname else ""
    return f"{host}{prog}: {s.message or ''}".strip(": ")


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


_FILE_TS_DESC = {
    "mtime":  "FileModified",
    "atime":  "FileAccessed",
    "ctime":  "FileChanged",
    "crtime": "FileCreated",
}


def _enrich_event(artifact_type: str, obj, file_attr: str | None = None, hostname: str | None = None) -> dict:
    """Return enrichment fields (ts_description, hostname, source_ip, dest_ip, md5, assoc_user)."""
    source_ip: str | None = None
    dest_ip:   str | None = None
    md5:       str | None = None
    assoc_user: str | None = None
    ts_description: str | None = None

    if artifact_type == "processes":
        ts_description = "ProcessStarted"
        assoc_user = getattr(obj, "user", None)
    elif artifact_type == "auth":
        result = (getattr(obj, "result", None) or "").capitalize()
        ts_description = f"Login:{result}" if result else "Auth:Event"
        source_ip = getattr(obj, "source", None)
        dest_ip   = getattr(obj, "destination", None)
        assoc_user = getattr(obj, "username", None)
    elif artifact_type == "cmdhistory":
        ts_description = "HistoryEntry"
        assoc_user = getattr(obj, "user", None)
    elif artifact_type == "cron":
        ts_description = "CronModified"
        assoc_user = getattr(obj, "username", None)
    elif artifact_type == "services":
        ts_description = "ServiceModified"
    elif artifact_type == "rcscripts":
        ts_description = "RcScriptModified"
        assoc_user = getattr(obj, "username", None)
    elif artifact_type == "files":
        ts_description = _FILE_TS_DESC.get(file_attr or "", "FileTimestamp")
        md5 = getattr(obj, "md5", None)
        uid = getattr(obj, "uid", None)
        assoc_user = str(uid) if uid is not None else None
    elif artifact_type == "netconns":
        state = getattr(obj, "state", None)
        ts_description = f"NetConn:{state}" if state else "NetConn"
        dest_ip = getattr(obj, "remote_addr", None)
    elif artifact_type == "syslog":
        event_type = getattr(obj, "event_type", None)
        ts_description = f"Syslog:{event_type}" if event_type else "Syslog:EventGenerated"
        source_ip  = getattr(obj, "source_ip", None)
        assoc_user = getattr(obj, "actor_user", None)

    return dict(
        ts_description=ts_description,
        hostname=hostname,
        source_ip=source_ip,
        dest_ip=dest_ip,
        md5=md5,
        assoc_user=assoc_user,
    )


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

def _get_timeline_python(
    collection_id: int,
    start: Optional[datetime],
    end: Optional[datetime],
    requested_types: set,
    col_filters: list[dict],
    tag_ids: Optional[str],
    limit: int,
    offset: int,
    db: Session,
    hostname: str | None = None,
) -> "TimelineResponse":
    """Slow path: Python-level sort+filter for column filter queries."""
    events: list[TimelineEvent] = []

    def _add(ev: TimelineEvent) -> None:
        if not col_filters or _apply_col_filters_event(ev, col_filters):
            events.append(ev)

    if "processes" in requested_types:
        q = db.query(Process).filter_by(collection_id=collection_id)
        if start: q = q.filter(Process.started >= start)
        if end:   q = q.filter(Process.started <= end)
        q = _filter_by_tags(q, Process, "processes", db, collection_id, tag_ids)
        for p in q.all():
            _add(TimelineEvent(timestamp=p.started, artifact_type="processes", id=p.id, summary=_process_summary(p), details=_obj_to_dict(p), **_enrich_event("processes", p, hostname=hostname)))

    if "auth" in requested_types:
        q = db.query(Authentication).filter_by(collection_id=collection_id)
        if start: q = q.filter(Authentication.time >= start)
        if end:   q = q.filter(Authentication.time <= end)
        q = _filter_by_tags(q, Authentication, "auth", db, collection_id, tag_ids)
        for a in q.all():
            _add(TimelineEvent(timestamp=a.time, artifact_type="auth", id=a.id, summary=_auth_summary(a), details=_obj_to_dict(a), **_enrich_event("auth", a, hostname=hostname)))

    if "cmdhistory" in requested_types:
        q = db.query(CommandHistory).filter_by(collection_id=collection_id)
        if start: q = q.filter(CommandHistory.time >= start)
        if end:   q = q.filter(CommandHistory.time <= end)
        q = _filter_by_tags(q, CommandHistory, "cmdhistory", db, collection_id, tag_ids)
        for c in q.all():
            _add(TimelineEvent(timestamp=c.time, artifact_type="cmdhistory", id=c.id, summary=_cmdhistory_summary(c), details=_obj_to_dict(c), **_enrich_event("cmdhistory", c, hostname=hostname)))

    if "cron" in requested_types:
        q = db.query(CronJob).filter_by(collection_id=collection_id)
        if start: q = q.filter(CronJob.source_file_modified >= start)
        if end:   q = q.filter(CronJob.source_file_modified <= end)
        q = _filter_by_tags(q, CronJob, "cron", db, collection_id, tag_ids)
        for cj in q.all():
            if cj.source_file_modified is None and (start or end): continue
            user = f"{cj.username}: " if cj.username else ""
            _add(TimelineEvent(timestamp=cj.source_file_modified, artifact_type="cron", id=cj.id, summary=f"{user}{cj.command or ''}".strip(), details=_obj_to_dict(cj), **_enrich_event("cron", cj, hostname=hostname)))

    if "services" in requested_types:
        q = db.query(SystemdService).filter_by(collection_id=collection_id)
        if start: q = q.filter(SystemdService.source_file_modified >= start)
        if end:   q = q.filter(SystemdService.source_file_modified <= end)
        q = _filter_by_tags(q, SystemdService, "services", db, collection_id, tag_ids)
        for svc in q.all():
            if svc.source_file_modified is None and (start or end): continue
            label = f"{svc.unit_name or ''}.{svc.unit_type or ''}".strip('.')
            summary = f"{label}: {svc.description or svc.exec_start or ''}".rstrip(': ')
            _add(TimelineEvent(timestamp=svc.source_file_modified, artifact_type="services", id=svc.id, summary=summary, details=_obj_to_dict(svc), **_enrich_event("services", svc, hostname=hostname)))

    if "rcscripts" in requested_types:
        q = db.query(RcScript).filter_by(collection_id=collection_id)
        if start: q = q.filter(RcScript.source_file_modified >= start)
        if end:   q = q.filter(RcScript.source_file_modified <= end)
        q = _filter_by_tags(q, RcScript, "rcscripts", db, collection_id, tag_ids)
        for rc in q.all():
            if rc.source_file_modified is None and (start or end): continue
            user_part = f"{rc.username}: " if rc.username else ""
            _add(TimelineEvent(timestamp=rc.source_file_modified, artifact_type="rcscripts", id=rc.id, summary=f"{user_part}{rc.path or ''}".strip(), details=_obj_to_dict(rc), **_enrich_event("rcscripts", rc, hostname=hostname)))

    if "files" in requested_types:
        q = db.query(File).filter_by(collection_id=collection_id)
        q = _filter_by_tags(q, File, "files", db, collection_id, tag_ids)
        for f in q.all():
            for attr in ("mtime", "atime", "ctime", "crtime"):
                ts = getattr(f, attr)
                if ts is None or (start and ts < start) or (end and ts > end): continue
                _add(TimelineEvent(timestamp=ts, artifact_type="files", id=f.id, summary=f.path or '', details=_obj_to_dict(f), **_enrich_event("files", f, file_attr=attr, hostname=hostname)))

    if "netconns" in requested_types and not start and not end:
        q = db.query(NetworkConnection).filter_by(collection_id=collection_id)
        q = _filter_by_tags(q, NetworkConnection, "netconns", db, collection_id, tag_ids)
        for nc in q.all():
            summary = f"{nc.proto} {nc.local_addr}:{nc.local_port} → {nc.remote_addr}:{nc.remote_port} [{nc.state}]"
            _add(TimelineEvent(timestamp=None, artifact_type="netconns", id=nc.id, summary=summary, details=_obj_to_dict(nc), **_enrich_event("netconns", nc, hostname=hostname)))

    if "syslog" in requested_types:
        q = db.query(SyslogEntry).filter_by(collection_id=collection_id)
        if start: q = q.filter(SyslogEntry.timestamp >= start)
        if end:   q = q.filter(SyslogEntry.timestamp <= end)
        q = _filter_by_tags(q, SyslogEntry, "syslog", db, collection_id, tag_ids)
        for s in q.all():
            _add(TimelineEvent(timestamp=s.timestamp, artifact_type="syslog", id=s.id, summary=_syslog_summary(s), details=_obj_to_dict(s), **_enrich_event("syslog", s, hostname=hostname)))

    events.sort(key=lambda e: (e.timestamp is None, e.timestamp or datetime.min))
    total = len(events)
    return TimelineResponse(total=total, offset=offset, limit=limit, events=events[offset: offset + limit])


def _get_timeline_sql(
    collection_id: int,
    start: Optional[datetime],
    end: Optional[datetime],
    requested_types: set,
    tag_ids: Optional[str],
    limit: int,
    offset: int,
    db: Session,
    hostname: str | None = None,
) -> "TimelineResponse":
    """Fast path: SQL UNION ALL + ORDER BY + LIMIT/OFFSET, hydrate only the page."""

    def _tag_sub(artifact_type):
        if not tag_ids:
            return None
        ids = [int(x) for x in tag_ids.split(',') if x.strip().isdigit()]
        if not ids:
            return None
        return (
            db.query(Tagging.artifact_id)
              .filter(Tagging.collection_id == collection_id,
                      Tagging.artifact_type == artifact_type,
                      Tagging.tag_id.in_(ids))
              .subquery()
        )

    subqueries = []

    # Types with a single timestamp column
    _SIMPLE = [
        (Process,        "started",              "processes"),
        (Authentication, "time",                 "auth"),
        (CommandHistory, "time",                 "cmdhistory"),
        (CronJob,        "source_file_modified", "cron"),
        (SystemdService, "source_file_modified", "services"),
        (RcScript,       "source_file_modified", "rcscripts"),
        (SyslogEntry,    "timestamp",            "syslog"),
    ]
    for model, ts_attr, atype in _SIMPLE:
        if atype not in requested_types:
            continue
        ts_col = getattr(model, ts_attr)
        q = select(model.id.label("eid"), literal(atype).label("atype"), ts_col.label("ts")).where(
            model.collection_id == collection_id
        )
        if start: q = q.where(ts_col >= start)
        if end:   q = q.where(ts_col <= end)
        sub = _tag_sub(atype)
        if sub is not None: q = q.where(model.id.in_(sub))
        subqueries.append(q)

    # Files: up to 4 events per row (one per timestamp attribute)
    if "files" in requested_types:
        file_sub = _tag_sub("files")
        for attr, file_atype in [("mtime","files_M"),("atime","files_A"),("ctime","files_C"),("crtime","files_B")]:
            ts_col = getattr(File, attr)
            q = select(File.id.label("eid"), literal(file_atype).label("atype"), ts_col.label("ts")).where(
                File.collection_id == collection_id, ts_col.isnot(None)
            )
            if start: q = q.where(ts_col >= start)
            if end:   q = q.where(ts_col <= end)
            if file_sub is not None: q = q.where(File.id.in_(file_sub))
            subqueries.append(q)

    # Netconns: no timestamp, omit when a date filter is active
    if "netconns" in requested_types and not start and not end:
        nc_sub = _tag_sub("netconns")
        q = select(
            NetworkConnection.id.label("eid"),
            literal("netconns").label("atype"),
            null().label("ts"),
        ).where(NetworkConnection.collection_id == collection_id)
        if nc_sub is not None: q = q.where(NetworkConnection.id.in_(nc_sub))
        subqueries.append(q)

    if not subqueries:
        return TimelineResponse(total=0, offset=offset, limit=limit, events=[])

    combined = sa_union_all(*subqueries).subquery("combined")

    total = db.execute(select(func.count()).select_from(combined)).scalar() or 0

    # Nulls-last sort: events with real timestamps first (ascending), then timestamp-less
    page_rows = db.execute(
        select(combined.c.eid, combined.c.atype, combined.c.ts)
        .order_by(
            sa_case((combined.c.ts.is_(None), 1), else_=0),
            combined.c.ts,
        )
        .limit(limit)
        .offset(offset)
    ).fetchall()

    if not page_rows:
        return TimelineResponse(total=total, offset=offset, limit=limit, events=[])

    # Group IDs by type so we can batch-fetch only the rows on this page
    ids_by_atype: dict[str, list[int]] = defaultdict(list)
    for row in page_rows:
        ids_by_atype[row.atype].append(row.eid)

    _FILE_ATYPES = {"files_M", "files_A", "files_C", "files_B"}
    file_ids = set()
    for fat in _FILE_ATYPES:
        file_ids.update(ids_by_atype.get(fat, []))

    objs: dict[tuple, Any] = {}
    if ids_by_atype.get("processes"):
        for p in db.query(Process).filter(Process.id.in_(ids_by_atype["processes"])):
            objs[("processes", p.id)] = p
    if ids_by_atype.get("auth"):
        for a in db.query(Authentication).filter(Authentication.id.in_(ids_by_atype["auth"])):
            objs[("auth", a.id)] = a
    if ids_by_atype.get("cmdhistory"):
        for c in db.query(CommandHistory).filter(CommandHistory.id.in_(ids_by_atype["cmdhistory"])):
            objs[("cmdhistory", c.id)] = c
    if ids_by_atype.get("cron"):
        for cj in db.query(CronJob).filter(CronJob.id.in_(ids_by_atype["cron"])):
            objs[("cron", cj.id)] = cj
    if ids_by_atype.get("services"):
        for svc in db.query(SystemdService).filter(SystemdService.id.in_(ids_by_atype["services"])):
            objs[("services", svc.id)] = svc
    if ids_by_atype.get("rcscripts"):
        for rc in db.query(RcScript).filter(RcScript.id.in_(ids_by_atype["rcscripts"])):
            objs[("rcscripts", rc.id)] = rc
    if file_ids:
        for f in db.query(File).filter(File.id.in_(file_ids)):
            objs[("file", f.id)] = f
    if ids_by_atype.get("netconns"):
        for nc in db.query(NetworkConnection).filter(NetworkConnection.id.in_(ids_by_atype["netconns"])):
            objs[("netconns", nc.id)] = nc
    if ids_by_atype.get("syslog"):
        for s in db.query(SyslogEntry).filter(SyslogEntry.id.in_(ids_by_atype["syslog"])):
            objs[("syslog", s.id)] = s

    _FILE_ATTR = {
        "files_M": ("M", "mtime"),
        "files_A": ("A", "atime"),
        "files_C": ("C", "ctime"),
        "files_B": ("B", "crtime"),
    }

    events: list[TimelineEvent] = []
    for row in page_rows:
        atype, eid = row.atype, row.eid
        if atype == "processes":
            p = objs.get(("processes", eid))
            if p: events.append(TimelineEvent(timestamp=p.started, artifact_type="processes", id=p.id, summary=_process_summary(p), details=_obj_to_dict(p), **_enrich_event("processes", p, hostname=hostname)))
        elif atype == "auth":
            a = objs.get(("auth", eid))
            if a: events.append(TimelineEvent(timestamp=a.time, artifact_type="auth", id=a.id, summary=_auth_summary(a), details=_obj_to_dict(a), **_enrich_event("auth", a, hostname=hostname)))
        elif atype == "cmdhistory":
            c = objs.get(("cmdhistory", eid))
            if c: events.append(TimelineEvent(timestamp=c.time, artifact_type="cmdhistory", id=c.id, summary=_cmdhistory_summary(c), details=_obj_to_dict(c), **_enrich_event("cmdhistory", c, hostname=hostname)))
        elif atype == "cron":
            cj = objs.get(("cron", eid))
            if cj:
                u = f"{cj.username}: " if cj.username else ""
                summary = f"{u}{cj.command or ''}".strip()
                events.append(TimelineEvent(timestamp=cj.source_file_modified, artifact_type="cron", id=cj.id, summary=summary, details=_obj_to_dict(cj), **_enrich_event("cron", cj, hostname=hostname)))
        elif atype == "services":
            svc = objs.get(("services", eid))
            if svc:
                lbl = f"{svc.unit_name or ''}.{svc.unit_type or ''}".strip('.')
                detail = svc.description or svc.exec_start or ''
                summary = f"{lbl}: {detail}".rstrip(': ')
                events.append(TimelineEvent(timestamp=svc.source_file_modified, artifact_type="services", id=svc.id, summary=summary, details=_obj_to_dict(svc), **_enrich_event("services", svc, hostname=hostname)))
        elif atype == "rcscripts":
            rc = objs.get(("rcscripts", eid))
            if rc:
                user_part = f"{rc.username}: " if rc.username else ""
                summary = f"{user_part}{rc.path or ''}".strip()
                events.append(TimelineEvent(timestamp=rc.source_file_modified, artifact_type="rcscripts", id=rc.id, summary=summary, details=_obj_to_dict(rc), **_enrich_event("rcscripts", rc, hostname=hostname)))
        elif atype in _FILE_ATTR:
            _, attr = _FILE_ATTR[atype]
            f = objs.get(("file", eid))
            if f:
                ts = getattr(f, attr)
                events.append(TimelineEvent(timestamp=ts, artifact_type="files", id=f.id, summary=f.path or '', details=_obj_to_dict(f), **_enrich_event("files", f, file_attr=attr, hostname=hostname)))
        elif atype == "netconns":
            nc = objs.get(("netconns", eid))
            if nc:
                events.append(TimelineEvent(timestamp=None, artifact_type="netconns", id=nc.id, summary=f"{nc.proto} {nc.local_addr}:{nc.local_port} → {nc.remote_addr}:{nc.remote_port} [{nc.state}]", details=_obj_to_dict(nc), **_enrich_event("netconns", nc, hostname=hostname)))
        elif atype == "syslog":
            s = objs.get(("syslog", eid))
            if s:
                events.append(TimelineEvent(timestamp=s.timestamp, artifact_type="syslog", id=s.id, summary=_syslog_summary(s), details=_obj_to_dict(s), **_enrich_event("syslog", s, hostname=hostname)))

    return TimelineResponse(total=total, offset=offset, limit=limit, events=events)


@router.get("/collections/{collection_id}/timeline", response_model=TimelineResponse)
def get_timeline(
    collection_id: int,
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    types: Optional[str] = Query(default=None, description="Comma-separated: processes,netconns,auth,cmdhistory"),
    col_filters: Optional[str] = Query(default=None, description="JSON array of {col,mode,pattern,isRegex} rules"),
    tag_ids: Optional[str] = Query(default=None, description="Comma-separated tag IDs (OR logic)"),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    col = _require_collection(collection_id, db)
    requested_types = {t.strip() for t in types.split(",")} if types else ALL_TYPES
    hostname = col.hostname
    rules = _parse_col_filters(col_filters)

    if rules:
        return _get_timeline_python(collection_id, start, end, requested_types, rules, tag_ids, limit, offset, db, hostname=hostname)
    return _get_timeline_sql(collection_id, start, end, requested_types, tag_ids, limit, offset, db, hostname=hostname)


# ── Per-artifact endpoints ────────────────────────────────────────────────────

@router.get("/collections/{collection_id}/processes", response_model=PaginatedProcesses)
def get_processes(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(Process).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, Process, "processes", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedProcesses(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/netconns", response_model=PaginatedNetconns)
def get_netconns(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(NetworkConnection).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, NetworkConnection, "netconns", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedNetconns(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/auth", response_model=PaginatedAuth)
def get_auth(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(Authentication).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, Authentication, "auth", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedAuth(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/cmdhistory", response_model=PaginatedCmdHistory)
def get_cmdhistory(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(CommandHistory).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, CommandHistory, "cmdhistory", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedCmdHistory(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/users", response_model=PaginatedUsers)
def get_users(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(User).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, User, "users", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedUsers(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/cron", response_model=PaginatedCronJobs)
def get_cron(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(CronJob).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, CronJob, "cron", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedCronJobs(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/services", response_model=PaginatedSystemdServices)
def get_systemd(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(SystemdService).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, SystemdService, "services", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedSystemdServices(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/rcscripts", response_model=PaginatedRcScripts)
def get_rcscripts(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(RcScript).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, RcScript, "rcscripts", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedRcScripts(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


@router.get("/collections/{collection_id}/syslog", response_model=PaginatedSyslog)
def get_syslog(
    collection_id: int,
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(SyslogEntry).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, SyslogEntry, "syslog", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedSyslog(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])


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
    col_filters: Optional[str] = Query(default=None),
    tag_ids: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    _require_collection(collection_id, db)
    q = db.query(File).filter_by(collection_id=collection_id)
    q = _filter_by_tags(q, File, "files", db, collection_id, tag_ids)
    rows = q.all()
    rules = _parse_col_filters(col_filters)
    if rules:
        rows = [r for r in rows if _apply_col_filters_obj(r, rules)]
    total = len(rows)
    return PaginatedFiles(total=total, offset=offset, limit=limit, items=rows[offset: offset + limit])
