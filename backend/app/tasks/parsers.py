"""
Celery tasks for parsing UAC collection artifacts.

Each per-artifact task:
  1. Updates ArtifactJob status in the DB
  2. Runs the corresponding uac_parser function (which returns plain ORM objects)
  3. Sets collection_id on each result and bulk-inserts
  4. Saves captured log records to ProcessingLog
  5. Updates ArtifactJob with final status and record count
"""
from __future__ import annotations

import datetime
import logging
import re as _re
import traceback
from typing import Any

from celery import chord, group
from sqlalchemy.orm import Session

from backend.app.config import DB_PATH, PARSE_THRESHOLD
from backend.app.tasks.celery_app import celery

# Importing backend.app.database ensures uac_parser.models AND backend.app.models
# are both registered with Base before any session or create_all is called.
from backend.app.database import engine as _get_engine


# ── Log capture ───────────────────────────────────────────────────────────────

class CapturingHandler(logging.Handler):
    """Intercepts log records during a parse run."""

    def __init__(self):
        super().__init__()
        self.records: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord):
        self.records.append({
            "level": record.levelname,
            "message": self.format(record),
            "timestamp": datetime.datetime.utcnow(),
        })


def _parse_tz_offset(tz_str: str | None) -> datetime.timedelta | None:
    """Parse '+HH:MM' / '-HH:MM' offset string into a timedelta (positive = east of UTC)."""
    if not tz_str:
        return None
    m = _re.match(r'^([+-])(\d{2}):(\d{2})$', tz_str.strip())
    if not m:
        return None
    sign = 1 if m.group(1) == '+' else -1
    return sign * datetime.timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))


def _apply_utc_offset(results: list, tz_offset: datetime.timedelta, *fields: str) -> None:
    """Subtract tz_offset from naive local timestamps to produce naive UTC values."""
    for obj in results:
        for field in fields:
            val = getattr(obj, field, None)
            if isinstance(val, datetime.datetime) and val.tzinfo is None:
                setattr(obj, field, val - tz_offset)


def _make_session() -> Session:
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=_get_engine(), autocommit=False, autoflush=False)()


def _update_artifact_job(session: Session, artifact_job_id: int, **kwargs):
    from backend.app.models import ArtifactJob
    job = session.query(ArtifactJob).filter_by(id=artifact_job_id).first()
    if job:
        for k, v in kwargs.items():
            setattr(job, k, v)
        session.commit()


def _save_logs(session: Session, artifact_job_id: int, processing_job_id: int, records: list[dict]):
    from backend.app.models import ProcessingLog
    logs = [
        ProcessingLog(
            artifact_job_id=artifact_job_id,
            processing_job_id=processing_job_id,
            level=r["level"],
            message=r["message"],
            timestamp=r["timestamp"],
        )
        for r in records
    ]
    if logs:
        session.bulk_save_objects(logs)
        session.commit()


def _run_artifact_task(
    artifact_job_id: int,
    collection_id: int,
    processing_job_id: int,
    parse_fn,
    set_id_fn,
    tz_offset_str: str | None = None,
    ts_fields: tuple[str, ...] = (),
    **parse_kwargs,
):
    """Generic runner shared by all per-artifact tasks."""
    session = _make_session()
    handler = CapturingHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        _update_artifact_job(session, artifact_job_id, status="running", started_at=datetime.datetime.utcnow())

        results = parse_fn(**parse_kwargs)

        if tz_offset_str and ts_fields and results:
            tz_offset = _parse_tz_offset(tz_offset_str)
            if tz_offset:
                _apply_utc_offset(results, tz_offset, *ts_fields)

        for obj in results:
            set_id_fn(obj, collection_id)

        if results:
            session.bulk_save_objects(results)
            session.commit()

        _update_artifact_job(
            session, artifact_job_id,
            status="completed",
            completed_at=datetime.datetime.utcnow(),
            record_count=len(results),
        )
        return {"status": "completed", "count": len(results)}

    except Exception as exc:
        session.rollback()
        _update_artifact_job(
            session, artifact_job_id,
            status="failed",
            completed_at=datetime.datetime.utcnow(),
            error_message=str(exc)[:500],
        )
        handler.records.append({
            "level": "ERROR",
            "message": f"Task failed: {traceback.format_exc()}",
            "timestamp": datetime.datetime.utcnow(),
        })
        return {"status": "failed", "error": str(exc)}

    finally:
        root_logger.removeHandler(handler)
        _save_logs(session, artifact_job_id, processing_job_id, handler.records)
        session.close()


# ── Per-artifact tasks ────────────────────────────────────────────────────────

@celery.task(bind=True, name="tasks.parse_processes")
def parse_processes_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str, threshold: int, tz_offset_str: str | None = None):
    from uac_parser.artifacts.processes import parse_processes
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_processes,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        tz_offset_str=tz_offset_str,
        ts_fields=("started",),
        uac_collection_path=collection_path,
        threshold=threshold,
    )


@celery.task(bind=True, name="tasks.parse_netconns")
def parse_netconns_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str, threshold: int):
    from uac_parser.artifacts.netconns import parse_network_connections
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_network_connections,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        uac_collection_path=collection_path,
        threshold=threshold,
    )


@celery.task(bind=True, name="tasks.parse_auth")
def parse_auth_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str, threshold: int, tz_offset_str: str | None = None):
    from uac_parser.artifacts.authentications import parse_authentications
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_authentications,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        tz_offset_str=tz_offset_str,
        ts_fields=("time",),
        uac_collection_path=collection_path,
        threshold=threshold,
    )


@celery.task(bind=True, name="tasks.parse_cmdhistory")
def parse_cmdhistory_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str, tz_offset_str: str | None = None):
    from uac_parser.artifacts.command_history import parse_command_history
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_command_history,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        tz_offset_str=tz_offset_str,
        ts_fields=("time",),
        uac_collection_path=collection_path,
    )


@celery.task(bind=True, name="tasks.parse_users")
def parse_users_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str, collection_os: str | None):
    from uac_parser.artifacts.users import parse_users
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_users,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        uac_collection_path=collection_path,
        collection_os=collection_os,
    )


@celery.task(bind=True, name="tasks.parse_cron")
def parse_cron_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str):
    from uac_parser.artifacts.cron import parse_cron
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_cron,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        uac_collection_path=collection_path,
    )


@celery.task(bind=True, name="tasks.parse_systemd")
def parse_systemd_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str):
    from uac_parser.artifacts.systemd import parse_systemd_services
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_systemd_services,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        uac_collection_path=collection_path,
    )


@celery.task(bind=True, name="tasks.parse_bodyfile")
def parse_bodyfile_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str):
    from uac_parser.artifacts.files import parse_bodyfile
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_bodyfile,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        uac_collection_path=collection_path,
    )


@celery.task(bind=True, name="tasks.parse_rcscripts")
def parse_rcscripts_task(self, artifact_job_id: int, collection_id: int, processing_job_id: int, collection_path: str):
    from uac_parser.artifacts.rcscripts import parse_rc_scripts
    return _run_artifact_task(
        artifact_job_id, collection_id, processing_job_id,
        parse_fn=parse_rc_scripts,
        set_id_fn=lambda obj, cid: setattr(obj, "collection_id", cid),
        uac_collection_path=collection_path,
    )


# ── Orchestrator task ─────────────────────────────────────────────────────────

ARTIFACT_TASKS = {
    "processes": parse_processes_task,
    "netconns": parse_netconns_task,
    "auth": parse_auth_task,
    "cmdhistory": parse_cmdhistory_task,
    "users": parse_users_task,
    "cron": parse_cron_task,
    "systemd": parse_systemd_task,
    "bodyfile": parse_bodyfile_task,
    "rcscripts": parse_rcscripts_task,
}


@celery.task(bind=True, name="tasks.process_collection")
def process_collection(self, job_id: int, collection_path: str, collection_id: int, collection_os: str | None, threshold: int = PARSE_THRESHOLD):
    from backend.app.models import ProcessingJob, ArtifactJob

    session = _make_session()
    try:
        pjob = session.query(ProcessingJob).filter_by(id=job_id).first()
        if not pjob:
            return {"error": f"ProcessingJob {job_id} not found"}

        pjob.status = "running"
        pjob.started_at = datetime.datetime.utcnow()
        session.commit()

        # Parse system info synchronously — it's fast (small text files) and
        # provides context needed before artifact parsing begins.
        tz_offset_str: str | None = None
        try:
            from uac_parser.artifacts.system_info import parse_system_info
            from uac_parser.models import UACCollection
            sys_info = parse_system_info(collection_path)
            if sys_info:
                sys_info.collection_id = collection_id
                session.add(sys_info)
                coll = session.query(UACCollection).filter_by(id=collection_id).first()
                if coll:
                    if sys_info.primary_ip and not coll.primary_ip_address:
                        coll.primary_ip_address = sys_info.primary_ip
                    if sys_info.timezone_offset and not coll.timezone_setting:
                        coll.timezone_setting = sys_info.timezone_offset
                tz_offset_str = sys_info.timezone_offset
                session.commit()
        except Exception as exc:
            session.rollback()
            logging.warning("SystemInfo parse failed: %s", exc)

        # Create one ArtifactJob per artifact type
        artifact_job_ids: dict[str, int] = {}
        for artifact_type in ARTIFACT_TASKS:
            aj = ArtifactJob(
                processing_job_id=job_id,
                artifact_type=artifact_type,
                status="pending",
            )
            session.add(aj)
            session.flush()
            artifact_job_ids[artifact_type] = aj.id
        session.commit()

    finally:
        session.close()

    # Build Celery subtasks
    subtasks = []

    subtasks.append(parse_processes_task.s(
        artifact_job_ids["processes"], collection_id, job_id, collection_path, threshold, tz_offset_str
    ))
    subtasks.append(parse_netconns_task.s(
        artifact_job_ids["netconns"], collection_id, job_id, collection_path, threshold
    ))
    subtasks.append(parse_auth_task.s(
        artifact_job_ids["auth"], collection_id, job_id, collection_path, threshold, tz_offset_str
    ))
    subtasks.append(parse_cmdhistory_task.s(
        artifact_job_ids["cmdhistory"], collection_id, job_id, collection_path, tz_offset_str
    ))
    subtasks.append(parse_users_task.s(
        artifact_job_ids["users"], collection_id, job_id, collection_path, collection_os
    ))
    subtasks.append(parse_cron_task.s(
        artifact_job_ids["cron"], collection_id, job_id, collection_path
    ))
    subtasks.append(parse_systemd_task.s(
        artifact_job_ids["systemd"], collection_id, job_id, collection_path
    ))
    subtasks.append(parse_bodyfile_task.s(
        artifact_job_ids["bodyfile"], collection_id, job_id, collection_path
    ))
    subtasks.append(parse_rcscripts_task.s(
        artifact_job_ids["rcscripts"], collection_id, job_id, collection_path
    ))

    # Run all subtasks in parallel, then finalize
    chord(group(subtasks))(finalize_collection.s(job_id=job_id))


@celery.task(name="tasks.finalize_collection")
def finalize_collection(results: list[dict], job_id: int):
    from backend.app.models import ProcessingJob

    session = _make_session()
    try:
        pjob = session.query(ProcessingJob).filter_by(id=job_id).first()
        if pjob:
            any_failed = any(r.get("status") == "failed" for r in (results or []))
            pjob.status = "partial" if any_failed else "completed"
            pjob.completed_at = datetime.datetime.utcnow()
            session.commit()
    finally:
        session.close()
