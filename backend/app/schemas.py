from __future__ import annotations
from datetime import datetime
from typing import Annotated, Any, Optional
from pydantic import BaseModel, Field
from pydantic.functional_serializers import PlainSerializer


def _fmt_utc(v: datetime | None) -> str | None:
    if v is None:
        return None
    return v.strftime('%Y-%m-%dT%H:%M:%SZ')


# Annotated datetime types that serialise to "<ISO>Z" in JSON output.
# All stored datetimes are naive UTC; the Z suffix signals this to clients.
_UtcDt = Annotated[datetime, PlainSerializer(_fmt_utc, return_type=Optional[str], when_used='json')]
UTCDatetime = Optional[_UtcDt]
UTCDatetimeReq = _UtcDt


# ── Processing job schemas ────────────────────────────────────────────────────

class ProcessingLogOut(BaseModel):
    id: int
    level: str
    message: str
    timestamp: UTCDatetimeReq

    class Config:
        from_attributes = True


class ArtifactJobOut(BaseModel):
    id: int
    artifact_type: str
    status: str
    started_at: UTCDatetime
    completed_at: UTCDatetime
    record_count: int
    error_message: Optional[str]
    logs: list[ProcessingLogOut] = []

    class Config:
        from_attributes = True


class ProcessingJobOut(BaseModel):
    id: int
    collection_id: Optional[int]
    status: str
    created_at: UTCDatetimeReq
    started_at: UTCDatetime
    completed_at: UTCDatetime
    artifact_jobs: list[ArtifactJobOut] = []

    class Config:
        from_attributes = True


# ── Collection schemas ────────────────────────────────────────────────────────

class CollectionOut(BaseModel):
    id: int
    hostname: str
    os: Optional[str]
    timezone_setting: Optional[str]
    primary_ip_address: Optional[str]
    created_at: UTCDatetime
    uac_log_md5: Optional[str]
    # Artifact counts (populated by the endpoint, not ORM)
    process_count: int = 0
    netconn_count: int = 0
    auth_count: int = 0
    cmdhistory_count: int = 0
    user_count: int = 0
    cron_count: int = 0
    systemd_count: int = 0
    rcscripts_count: int = 0
    syslog_count: int = 0
    # Latest processing job summary
    latest_job: Optional[ProcessingJobOut] = None

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    collection_id: int
    job_id: int
    message: str


# ── Artifact schemas ──────────────────────────────────────────────────────────

class ProcessOut(BaseModel):
    id: int
    pid: Optional[int]
    ppid: Optional[int]
    uid: Optional[int]
    user: Optional[str]
    started: UTCDatetime
    command: Optional[str]
    arguments: Optional[str]

    class Config:
        from_attributes = True


class NetworkConnectionOut(BaseModel):
    id: int
    proto: Optional[str]
    local_addr: Optional[str]
    local_port: Optional[int]
    remote_addr: Optional[str]
    remote_port: Optional[int]
    state: Optional[str]
    pid: Optional[int]

    class Config:
        from_attributes = True


class AuthenticationOut(BaseModel):
    id: int
    uid: Optional[int]
    username: Optional[str]
    result: Optional[str]
    time: UTCDatetime
    method: Optional[str]
    source: Optional[str]
    destination: Optional[str]

    class Config:
        from_attributes = True


class CommandHistoryOut(BaseModel):
    id: int
    command: Optional[str]
    user: Optional[str]
    time: UTCDatetime
    history_file: Optional[str]
    file_index: Optional[int]

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    username: Optional[str]
    uid: Optional[int]
    gid: Optional[int]
    gecos: Optional[str]
    home: Optional[str]
    shell: Optional[str]

    class Config:
        from_attributes = True


# ── Timeline schemas ──────────────────────────────────────────────────────────

class TimelineEvent(BaseModel):
    timestamp: UTCDatetime
    artifact_type: str
    id: int
    summary: str
    details: dict[str, Any]


class TimelineResponse(BaseModel):
    total: int
    offset: int
    limit: int
    events: list[TimelineEvent]


# ── Paginated wrappers ────────────────────────────────────────────────────────

class PaginatedProcesses(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[ProcessOut]


class PaginatedNetconns(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[NetworkConnectionOut]


class PaginatedAuth(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[AuthenticationOut]


class PaginatedCmdHistory(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[CommandHistoryOut]


class PaginatedUsers(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[UserOut]


class FileOut(BaseModel):
    id: int
    path: Optional[str]
    size: Optional[int]
    mode: Optional[str]
    uid: Optional[int]
    gid: Optional[int]
    md5: Optional[str]
    inode: Optional[int]
    atime: UTCDatetime
    mtime: UTCDatetime
    ctime: UTCDatetime
    crtime: UTCDatetime

    class Config:
        from_attributes = True


class PaginatedFiles(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[FileOut]


class CronJobOut(BaseModel):
    id: int
    minute: Optional[str]
    hour: Optional[str]
    day_of_month: Optional[str]
    month: Optional[str]
    day_of_week: Optional[str]
    username: Optional[str]
    command: Optional[str]
    source_file: Optional[str]
    source_type: Optional[str]
    source_file_modified: UTCDatetime

    class Config:
        from_attributes = True


class PaginatedCronJobs(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[CronJobOut]


class SystemdServiceOut(BaseModel):
    id: int
    unit_name: Optional[str]
    unit_type: Optional[str]
    description: Optional[str]
    after: Optional[str]
    wants: Optional[str]
    requires: Optional[str]
    exec_start: Optional[str]
    exec_start_pre: Optional[str]
    exec_start_post: Optional[str]
    exec_stop: Optional[str]
    run_user: Optional[str]
    run_group: Optional[str]
    working_directory: Optional[str]
    service_type: Optional[str]
    restart: Optional[str]
    environment: Optional[str]
    wanted_by: Optional[str]
    source_file: Optional[str]
    source_path: Optional[str]
    source_dir_type: Optional[str]
    source_file_modified: UTCDatetime

    class Config:
        from_attributes = True


class PaginatedSystemdServices(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[SystemdServiceOut]


class RcScriptOut(BaseModel):
    id: int
    path: Optional[str]
    source_type: Optional[str]
    run_context: Optional[str]
    username: Optional[str]
    shell: Optional[str]
    interpreter: Optional[str]
    file_size: Optional[int]
    content_snippet: Optional[str]
    source_file_modified: UTCDatetime

    class Config:
        from_attributes = True


class PaginatedRcScripts(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[RcScriptOut]


class SyslogEntryOut(BaseModel):
    id: int
    timestamp: UTCDatetime
    hostname: Optional[str]
    program: Optional[str]
    pid: Optional[int]
    severity: Optional[str]
    message: Optional[str]
    source_file: Optional[str]
    event_type: Optional[str]
    actor_user: Optional[str]
    target_user: Optional[str]
    source_ip: Optional[str]
    command: Optional[str]

    class Config:
        from_attributes = True


class PaginatedSyslog(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[SyslogEntryOut]


class TagOut(BaseModel):
    id: int
    name: str
    color: str
    is_default: bool

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    name: str
    color: str = "gray"


class TagUpdate(BaseModel):
    name: Optional[str]
    color: Optional[str]


class TaggingOut(BaseModel):
    id: int
    tag_id: int
    artifact_type: str
    artifact_id: int
    collection_id: int

    class Config:
        from_attributes = True


class TaggingApply(BaseModel):
    tag_id: int
    artifact_type: str
    artifact_ids: list[int]


class TaggingRemove(BaseModel):
    tag_id: int
    artifact_type: str
    artifact_ids: list[int]


class NoteOut(BaseModel):
    id: int
    collection_id: int
    artifact_type: str
    artifact_id: int
    content: str
    created_at: UTCDatetimeReq
    updated_at: UTCDatetimeReq

    class Config:
        from_attributes = True


class NoteUpsert(BaseModel):
    collection_id: int
    artifact_type: str
    artifact_ids: list[int]
    content: str = Field(max_length=500)


class NoteDelete(BaseModel):
    artifact_type: str
    artifact_ids: list[int]


class FilePreviewResponse(BaseModel):
    path: str
    available: bool
    binary: bool = False
    content: Optional[str] = None
    size: Optional[int] = None
    truncated: bool = False


class SystemInfoOut(BaseModel):
    hostname: Optional[str]
    fqdn: Optional[str]
    primary_ip: Optional[str]
    os_name: Optional[str]
    kernel: Optional[str]
    cpu_arch: Optional[str]
    timezone_name: Optional[str]
    timezone_offset: Optional[str]
    memory_bytes: Optional[int]
    domain: Optional[str]
    hardware_model: Optional[str]
    virtualization: Optional[str]

    class Config:
        from_attributes = True
