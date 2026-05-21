import datetime
import logging
import os

from uac_parser.models import CronJob


# Directories whose scripts are invoked by cron at the named interval.
# Each file found is recorded as a single CronJob with schedule fields null.
_PERIODIC_DIRS = {
    'etc/cron.hourly':  'cron.hourly',
    'etc/cron.daily':   'cron.daily',
    'etc/cron.weekly':  'cron.weekly',
    'etc/cron.monthly': 'cron.monthly',
    'etc/cron.yearly':  'cron.yearly',
}

# Directories that hold per-user crontab files (filename = username).
# Listed in preference order; all that exist are parsed.
_USER_CRONTAB_DIRS = [
    'var/spool/cron/crontabs',   # Debian / Ubuntu
    'var/spool/cron',            # RHEL / CentOS  (files named by user)
    'var/cron/tabs',             # macOS
    'usr/lib/cron/tabs',         # Solaris
]


def parse_cron(uac_collection_path: str) -> list[CronJob]:
    """
    Parse all cron entries from a UAC collection.

    Sources (all under [root]/):
      - /etc/crontab              system crontab (has username field)
      - /etc/cron.d/*             per-package fragments (has username field)
      - /var/spool/cron/**        per-user crontabs (no username field; filename = user)
      - /etc/cron.{hourly,...}/*  periodic scripts (no schedule line)
    """
    logging.info("Parsing cron jobs")
    root = os.path.join(uac_collection_path, '[root]')
    if not os.path.exists(root):
        logging.warning("[root] directory not found; skipping cron parse")
        return []

    results: list[CronJob] = []

    # 1. /etc/crontab
    _parse_if_file(os.path.join(root, 'etc', 'crontab'),
                   '/etc/crontab', 'system', has_user=True, results=results)

    # 2. /etc/cron.d/*
    cron_d = os.path.join(root, 'etc', 'cron.d')
    if os.path.isdir(cron_d):
        for fname in sorted(os.listdir(cron_d)):
            if fname.startswith('.'):
                continue
            path = os.path.join(cron_d, fname)
            if os.path.isfile(path):
                _parse_if_file(path, f'/etc/cron.d/{fname}', 'cron.d',
                               has_user=True, results=results)

    # 3. User crontab directories
    for rel_dir in _USER_CRONTAB_DIRS:
        dir_path = os.path.join(root, rel_dir)
        if not os.path.isdir(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if fname.startswith('.'):
                continue
            path = os.path.join(dir_path, fname)
            if os.path.isfile(path):
                _parse_if_file(path, f'/{rel_dir}/{fname}', 'user',
                               has_user=False, implicit_user=fname, results=results)

    # 4. Periodic script directories
    for rel_dir, source_type in _PERIODIC_DIRS.items():
        dir_path = os.path.join(root, rel_dir)
        if not os.path.isdir(dir_path):
            continue
        for fname in sorted(os.listdir(dir_path)):
            if fname.startswith('.'):
                continue
            path = os.path.join(dir_path, fname)
            if not os.path.isfile(path):
                continue
            src_file = f'/{rel_dir}/{fname}'
            results.append(CronJob(
                minute=None, hour=None, day_of_month=None,
                month=None, day_of_week=None,
                username='root',
                command=src_file,
                source_file=src_file,
                source_type=source_type,
                source_file_modified=_mtime_utc(path),
            ))

    logging.info("Parsed %d cron entries", len(results))
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mtime_utc(path: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.utcfromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def _parse_if_file(path: str, source_file: str, source_type: str,
                   has_user: bool, results: list,
                   implicit_user: str | None = None) -> None:
    if not os.path.isfile(path):
        return
    entries = _parse_crontab_file(path, source_file, source_type,
                                   has_user, implicit_user)
    results.extend(entries)


def _parse_crontab_file(path: str, source_file: str, source_type: str,
                         has_user: bool,
                         implicit_user: str | None) -> list[CronJob]:
    entries: list[CronJob] = []
    modified = _mtime_utc(path)
    try:
        with open(path, 'r', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                tokens = line.split()
                if not tokens:
                    continue
                # Variable assignment: first token contains '=' (e.g. SHELL=/bin/sh)
                if '=' in tokens[0] and not tokens[0].startswith('@'):
                    continue

                if tokens[0].startswith('@'):
                    entry = _parse_at_entry(tokens, source_file, source_type,
                                            has_user, implicit_user, modified)
                else:
                    entry = _parse_std_entry(tokens, source_file, source_type,
                                              has_user, implicit_user, modified)
                if entry:
                    entries.append(entry)
    except Exception as exc:
        logging.warning("Failed to parse crontab %s: %s", path, exc)
    return entries


def _parse_at_entry(tokens: list[str], source_file: str, source_type: str,
                     has_user: bool, implicit_user: str | None,
                     modified: datetime.datetime | None) -> CronJob | None:
    """Handle @reboot / @daily / @weekly etc. nickname entries."""
    nickname = tokens[0]
    if has_user:
        if len(tokens) < 3:
            return None
        username = tokens[1]
        command = ' '.join(tokens[2:])
    else:
        if len(tokens) < 2:
            return None
        username = implicit_user
        command = ' '.join(tokens[1:])
    return CronJob(
        minute=nickname, hour=None, day_of_month=None,
        month=None, day_of_week=None,
        username=username, command=command,
        source_file=source_file, source_type=source_type,
        source_file_modified=modified,
    )


def _parse_std_entry(tokens: list[str], source_file: str, source_type: str,
                      has_user: bool, implicit_user: str | None,
                      modified: datetime.datetime | None) -> CronJob | None:
    """Handle standard five-field (or six-field with user) cron entries."""
    if has_user:
        if len(tokens) < 7:
            return None
        minute, hour, dom, month, dow, username = tokens[:6]
        command = ' '.join(tokens[6:])
    else:
        if len(tokens) < 6:
            return None
        minute, hour, dom, month, dow = tokens[:5]
        username = implicit_user
        command = ' '.join(tokens[5:])
    return CronJob(
        minute=minute, hour=hour, day_of_month=dom,
        month=month, day_of_week=dow,
        username=username, command=command,
        source_file=source_file, source_type=source_type,
        source_file_modified=modified,
    )
