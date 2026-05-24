"""
Parse syslog entries from UAC collections.

Targets well-known syslog file names in [root]/var/log/ (Linux) and
[root]/private/var/log/ (macOS), including rotated and gzip-compressed
variants (e.g., syslog.1, syslog.2.gz, system.log.0.gz).

Three patterns are tried against each file:
  SYSLOG_BSD     – classic "Nov 28 00:01:52 host prog[pid]: msg"
  SYSLOG_ISO     – ISO-8601 timestamp variant used by rsyslog/journald
  SYSLOG_RFC5424 – structured syslog with <priority> prefix

Year inference for BSD format (no year in timestamp):
  The modification time of the log file is used as a year hint so that
  entries in rotated files (syslog.1, syslog.2.gz) get an appropriate year
  rather than defaulting blindly to the current calendar year.

After generic line parsing, a second-pass enrichment step applies
program-specific regex patterns to the message body to extract structured
fields: event_type, actor_user, target_user, source_ip, command.
"""
import gzip
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from tqdm import tqdm

from uac_parser.grok import Grok
from uac_parser.grok_patterns import custom_patterns, syslog_patterns
from uac_parser.models import SyslogEntry
from uac_parser.utils import parse_timestamp_from_match

# Files whose base names are recognised as syslog sources.
_SYSLOG_BASE_NAMES = {
    "syslog",
    "messages",
    "secure",
    "auth.log",
    "kern.log",
    "daemon.log",
    "user.log",
    "system.log",
}

_ROTATION_NUM = re.compile(r"\.\d+$")          # strips trailing .N
_ROTATION_DATE = re.compile(r"-\d{8}$")        # strips trailing -YYYYMMDD


def _is_syslog_file(filename: str) -> bool:
    """Return True if *filename* looks like a syslog or rotated syslog file."""
    name = filename.lower()
    # Strip compression suffix
    for ext in (".gz", ".bz2", ".xz"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    # Strip rotation suffix
    name = _ROTATION_NUM.sub("", name)
    name = _ROTATION_DATE.sub("", name)
    return name in _SYSLOG_BASE_NAMES


@contextmanager
def _open_log(file_path: str) -> Iterator:
    """Open a plain or gzip-compressed log file for text reading."""
    if file_path.endswith(".gz"):
        fh = gzip.open(file_path, "rt", encoding="utf-8", errors="ignore")
    elif file_path.endswith(".bz2"):
        import bz2
        fh = bz2.open(file_path, "rt", encoding="utf-8", errors="ignore")
    else:
        fh = open(file_path, "r", errors="ignore")
    try:
        yield fh
    finally:
        fh.close()


def _file_mtime_year(file_path: str) -> int:
    """Return the year of the file's modification time, or current year on error."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path)).year
    except OSError:
        return datetime.now().year


def _collect_syslog_files(uac_collection_path: str) -> list[str]:
    """Return paths of candidate syslog files from known log directories."""
    log_dirs = [
        os.path.join(uac_collection_path, "[root]", "var", "log"),
        os.path.join(uac_collection_path, "[root]", "private", "var", "log"),
    ]

    paths: list[str] = []
    for log_dir in log_dirs:
        if not os.path.isdir(log_dir):
            continue
        for fname in os.listdir(log_dir):
            if _is_syslog_file(fname):
                full = os.path.join(log_dir, fname)
                if os.path.isfile(full):
                    paths.append(full)

    return paths


# ── Second-pass message enrichment ───────────────────────────────────────────

# Each entry: (event_type, regex, group_map)
# group_map keys: "actor_user", "target_user", "source_ip", "command"
# The regex is applied to the message body (case-insensitive where useful).
# Patterns are ordered from most specific to least specific within each program.

_F = re.IGNORECASE

_SSHD_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "ssh_login_success",
        re.compile(r"^Accepted (?P<method>\S+) for (?P<actor_user>\S+) from (?P<source_ip>\S+) port \d+"),
        {"actor_user": "actor_user", "source_ip": "source_ip"},
    ),
    (
        "ssh_login_failed",
        re.compile(r"^Failed \S+ for (?:invalid user )?(?P<actor_user>\S+) from (?P<source_ip>\S+) port \d+"),
        {"actor_user": "actor_user", "source_ip": "source_ip"},
    ),
    (
        "ssh_invalid_user",
        re.compile(r"^Invalid user (?P<actor_user>\S+) from (?P<source_ip>\S+)"),
        {"actor_user": "actor_user", "source_ip": "source_ip"},
    ),
    (
        "ssh_disconnect",
        re.compile(
            r"^(?:Disconnected from|Connection closed by)"
            r"(?:\s+(?:invalid|authenticating)\s+user)?"
            r"(?:\s+(?P<actor_user>[a-zA-Z0-9_.\-]+))?"
            r"\s+(?P<source_ip>\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]+)\s+port"
        ),
        {"actor_user": "actor_user", "source_ip": "source_ip"},
    ),
    (
        "ssh_max_auth_exceeded",
        re.compile(r"^error: maximum authentication attempts exceeded for (?:invalid user )?(?P<actor_user>\S+) from (?P<source_ip>\S+)"),
        {"actor_user": "actor_user", "source_ip": "source_ip"},
    ),
]

_SUDO_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "sudo_command",
        re.compile(
            r"^\s*(?P<actor_user>\S+)\s*:\s*(?:(?!command not allowed)\S.*?;)?\s*"
            r"TTY=\S+\s*;\s*PWD=\S+\s*;\s*USER=(?P<target_user>\S+)\s*;\s*COMMAND=(?P<command>.+)$"
        ),
        {"actor_user": "actor_user", "target_user": "target_user", "command": "command"},
    ),
    (
        "sudo_failed",
        re.compile(r"^\s*(?P<actor_user>\S+)\s*:\s*\d+ incorrect password attempt"),
        {"actor_user": "actor_user"},
    ),
    (
        "sudo_not_allowed",
        re.compile(r"^\s*(?P<actor_user>\S+)\s*:\s*command not allowed\s*;.*?USER=(?P<target_user>\S+)\s*;\s*COMMAND=(?P<command>.+)$"),
        {"actor_user": "actor_user", "target_user": "target_user", "command": "command"},
    ),
]

_SU_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "su_success",
        re.compile(r"^\(to (?P<target_user>\S+)\) (?P<actor_user>\S+) on"),
        {"actor_user": "actor_user", "target_user": "target_user"},
    ),
    (
        "su_failed",
        re.compile(r"^FAILED SU \(to (?P<target_user>\S+)\) (?P<actor_user>\S+) on"),
        {"actor_user": "actor_user", "target_user": "target_user"},
    ),
]

# PAM session/auth messages appear under many programs (sshd, sudo, su, login, etc.)
_PAM_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "session_opened",
        re.compile(r"pam_unix\([^:]+:session\): session opened for user (?P<target_user>\S+)"),
        {"target_user": "target_user"},
    ),
    (
        "session_closed",
        re.compile(r"pam_unix\([^:]+:session\): session closed for user (?P<target_user>\S+)"),
        {"target_user": "target_user"},
    ),
    (
        "auth_failed",
        re.compile(r"pam_unix\([^:]+:auth\): authentication failure;.*?(?:ruser=(?P<actor_user>\S+)|user=(?P<target_user>\S+))"),
        {"actor_user": "actor_user", "target_user": "target_user"},
    ),
]

_USERADD_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "user_created",
        re.compile(r"^new user: name=(?P<actor_user>[^,\s]+)"),
        {"actor_user": "actor_user"},
    ),
]

_USERDEL_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "user_deleted",
        re.compile(r"^(?:delete user|removed user) ['\"]?(?P<actor_user>[^'\"\s]+)"),
        {"actor_user": "actor_user"},
    ),
]

_GROUPADD_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "group_created",
        re.compile(r"^new group: name=(?P<actor_user>[^,\s]+)"),
        {"actor_user": "actor_user"},
    ),
]

_USERMOD_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "user_modified",
        re.compile(r"^(?:change|add) user ['\"]?(?P<actor_user>[^'\"\s]+)"),
        {"actor_user": "actor_user"},
    ),
]

_PASSWD_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "password_changed",
        re.compile(r"^password for (?P<target_user>\S+) changed(?: by (?P<actor_user>\S+))?"),
        {"actor_user": "actor_user", "target_user": "target_user"},
    ),
]

_CRON_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "cron_exec",
        re.compile(r"^\((?P<actor_user>[^)]+)\) CMD \((?P<command>.+)\)$"),
        {"actor_user": "actor_user", "command": "command"},
    ),
]

_LOGIND_PATTERNS: list[tuple[str, re.Pattern, dict]] = [
    (
        "session_opened",
        re.compile(r"^New session \S+ of user (?P<actor_user>\S+)"),
        {"actor_user": "actor_user"},
    ),
    (
        "session_closed",
        re.compile(r"^(?:Session \S+ logged out|Removed session \S+)"),
        {},
    ),
]

# Map normalised program name → list of (event_type, pattern, group_map) tuples.
# Programs that emit PAM messages also check _PAM_PATTERNS as a fallback.
_PROGRAM_PATTERNS: dict[str, list[tuple[str, re.Pattern, dict]]] = {
    "sshd":             _SSHD_PATTERNS,
    "sudo":             _SUDO_PATTERNS,
    "su":               _SU_PATTERNS,
    "useradd":          _USERADD_PATTERNS,
    "userdel":          _USERDEL_PATTERNS,
    "groupadd":         _GROUPADD_PATTERNS,
    "usermod":          _USERMOD_PATTERNS,
    "passwd":           _PASSWD_PATTERNS,
    "cron":             _CRON_PATTERNS,
    "crond":            _CRON_PATTERNS,
    "systemd-logind":   _LOGIND_PATTERNS,
}

# Programs that should also fall back to PAM pattern matching
_PAM_PROGRAMS = {"sshd", "sudo", "su", "login", "sshd-session"}


def _enrich_entry(entry: SyslogEntry) -> None:
    """Populate event_type and structured fields by pattern-matching the message."""
    if not entry.message or not entry.program:
        return

    prog = entry.program.lower()
    msg = entry.message

    patterns = _PROGRAM_PATTERNS.get(prog, [])

    for event_type, rx, group_map in patterns:
        m = rx.search(msg)
        if m:
            entry.event_type = event_type
            for field, group_name in group_map.items():
                try:
                    val = m.group(group_name)
                    if val:
                        setattr(entry, field, val.strip())
                except IndexError:
                    pass
            return

    # PAM fallback for programs that embed pam_unix() messages
    if prog in _PAM_PROGRAMS:
        for event_type, rx, group_map in _PAM_PATTERNS:
            m = rx.search(msg)
            if m:
                entry.event_type = event_type
                for field, group_name in group_map.items():
                    try:
                        val = m.group(group_name)
                        if val:
                            setattr(entry, field, val.strip())
                    except IndexError:
                        pass
                return


# ── Entry construction ────────────────────────────────────────────────────────

def _create_entry(match: dict, pattern_name: str, source_file: str, year_hint: int) -> Optional[SyslogEntry]:
    """Build a SyslogEntry from a grok match dict and run enrichment."""
    try:
        # Inject year hint for BSD timestamps that have no year field
        if "TIMESTAMP_ISO8601" not in match and "YEAR" not in match:
            match = dict(match)
            match["YEAR"] = year_hint

        timestamp = parse_timestamp_from_match(match)

        pid_raw = match.get("pid")
        pid = int(pid_raw) if pid_raw and pid_raw.isdigit() else None

        entry = SyslogEntry(
            timestamp=timestamp,
            hostname=match.get("hostname") or None,
            program=match.get("program") or None,
            pid=pid,
            severity=match.get("severity") or None,
            message=(match.get("message") or "").strip() or None,
            source_file=source_file,
        )

        _enrich_entry(entry)
        return entry
    except Exception as exc:
        logging.debug("Failed to create SyslogEntry from match: %s", exc)
        return None


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_syslog(uac_collection_path: str, threshold: int = 25) -> list[SyslogEntry]:
    """
    Parse syslog entries from a UAC collection.

    Args:
        uac_collection_path: Root of the extracted UAC collection.
        threshold: Minimum percentage of lines that must match for a
                   file/pattern combination to be accepted. Defaults to 25
                   (lower than other parsers because syslog files often
                   contain multi-line continuation entries that don't match).

    Returns:
        Deduplicated list of SyslogEntry objects.
    """
    logging.info("Parsing syslog files")

    candidate_files = _collect_syslog_files(uac_collection_path)
    if not candidate_files:
        logging.warning("No syslog files found in collection")
        return []

    logging.info("Found %d candidate syslog file(s)", len(candidate_files))

    # Pre-compile all patterns
    compiled: dict[str, Grok] = {}
    for pname, pat in syslog_patterns.items():
        try:
            compiled[pname] = Grok(pat, custom_patterns=custom_patterns)
        except Exception as exc:
            logging.warning("Failed to compile syslog pattern %s: %s", pname, exc)

    if not compiled:
        logging.error("No syslog patterns compiled successfully")
        return []

    entries: list[SyslogEntry] = []

    for file_path in tqdm(candidate_files, desc="Parsing syslog files", unit="files"):
        filename = os.path.basename(file_path)
        year_hint = _file_mtime_year(file_path)
        rel_path = file_path.split("[root]", 1)[-1] if "[root]" in file_path else file_path

        # Try each pattern; keep the one with the highest match rate above threshold
        best_matches: list[dict] = []
        best_pattern: str = ""
        best_rate: float = 0.0

        for pname, grok in compiled.items():
            line_matches: list[dict] = []
            total_lines = 0

            try:
                with _open_log(file_path) as fh:
                    for line in fh:
                        total_lines += 1
                        m = grok.match(line)
                        if m:
                            line_matches.append(m)
            except Exception as exc:
                logging.warning("Error reading %s with pattern %s: %s", filename, pname, exc)
                continue

            if total_lines == 0:
                continue

            rate = len(line_matches) / total_lines * 100
            if rate >= threshold and rate > best_rate:
                best_matches = line_matches
                best_pattern = pname
                best_rate = rate

        if not best_matches:
            logging.debug("No pattern met threshold (%.0f%%) for %s", threshold, filename)
            continue

        logging.info(
            "Pattern %s matched %.1f%% of %s — converting %d entries",
            best_pattern, best_rate, filename, len(best_matches),
        )

        for m in best_matches:
            entry = _create_entry(m, best_pattern, rel_path, year_hint)
            if entry:
                entries.append(entry)

    # Deduplicate on (timestamp, hostname, program, pid, message)
    seen: set[tuple] = set()
    unique: list[SyslogEntry] = []
    for e in entries:
        key = (str(e.timestamp), str(e.hostname), str(e.program), str(e.pid), str(e.message))
        if key not in seen:
            seen.add(key)
            unique.append(e)

    logging.info("Parsed %d syslog entries, deduplicated to %d", len(entries), len(unique))
    return unique
