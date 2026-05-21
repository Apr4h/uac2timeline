import datetime
import glob
import logging
import os

from uac_parser.models import SystemdService

_UNIT_DIRS = [
    ('etc/systemd/system',     'system'),
    ('usr/lib/systemd/system', 'lib-system'),
    ('lib/systemd/system',     'lib-system'),
    ('run/systemd/system',     'runtime'),
    ('etc/systemd/user',       'user'),
    ('usr/lib/systemd/user',   'lib-user'),
]

_UNIT_EXTENSIONS = {'.service', '.timer', '.socket', '.mount', '.path', '.target'}


def parse_systemd_services(uac_collection_path: str) -> list[SystemdService]:
    logging.info("Parsing systemd unit files")
    root = os.path.join(uac_collection_path, '[root]')
    if not os.path.exists(root):
        logging.warning("[root] directory not found; skipping systemd parse")
        return []

    results: list[SystemdService] = []
    seen_real: set[str] = set()

    def _scan(dir_path: str, source_dir_type: str) -> None:
        if not os.path.isdir(dir_path):
            return
        for entry in os.scandir(dir_path):
            ext = os.path.splitext(entry.name)[1].lower()
            if ext not in _UNIT_EXTENSIONS:
                continue
            try:
                real = os.path.realpath(entry.path)
            except OSError:
                real = entry.path
            if real in seen_real:
                continue
            seen_real.add(real)
            if not os.path.isfile(entry.path):
                continue
            svc = _parse_unit_file(entry.path, source_dir_type, root)
            if svc is not None:
                results.append(svc)

    for rel_dir, dir_type in _UNIT_DIRS:
        _scan(os.path.join(root, rel_dir), dir_type)

    # Per-user units: home/*/.config/systemd/user/
    for home_entry in glob.glob(os.path.join(root, 'home', '*')):
        if os.path.isdir(home_entry):
            _scan(os.path.join(home_entry, '.config', 'systemd', 'user'), 'user-local')

    logging.info("Parsed %d systemd unit files", len(results))
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mtime_utc(path: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.utcfromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def _read_unit_ini(path: str) -> dict[str, dict[str, list[str]]]:
    """Parse a systemd unit file into {Section: {Key: [val, ...]}}."""
    sections: dict[str, dict[str, list[str]]] = {}
    current_section: dict[str, list[str]] | None = None
    pending_key: str | None = None
    pending_val: str = ''

    def _flush() -> None:
        nonlocal pending_key, pending_val
        if pending_key is not None and current_section is not None:
            current_section.setdefault(pending_key, []).append(pending_val.strip())
        pending_key = None
        pending_val = ''

    try:
        with open(path, 'r', errors='ignore') as fh:
            for raw in fh:
                line = raw.rstrip('\n')
                stripped = line.strip()

                if not stripped or stripped.startswith('#') or stripped.startswith(';'):
                    if pending_key and not (pending_val.endswith('\\')):
                        _flush()
                    continue

                if stripped.startswith('[') and stripped.endswith(']'):
                    _flush()
                    sec_name = stripped[1:-1]
                    current_section = sections.setdefault(sec_name, {})
                    continue

                if current_section is None:
                    continue

                if pending_key is not None:
                    # Continuation line
                    continued = pending_val.rstrip('\\').rstrip()
                    pending_val = continued + ' ' + stripped.lstrip()
                    if not stripped.endswith('\\'):
                        _flush()
                    continue

                if '=' in stripped:
                    _flush()
                    key, _, val = stripped.partition('=')
                    pending_key = key.strip()
                    pending_val = val.strip()
                    if not pending_val.endswith('\\'):
                        _flush()
    except Exception as exc:
        logging.debug("Failed to read unit file %s: %s", path, exc)
    else:
        _flush()

    return sections


def _first(d: dict[str, list[str]], key: str) -> str | None:
    vals = d.get(key)
    return vals[0] if vals else None


def _join(d: dict[str, list[str]], key: str) -> str | None:
    vals = d.get(key)
    if not vals:
        return None
    joined = ' '.join(v for v in vals if v)
    return joined or None


def _parse_unit_file(path: str, source_dir_type: str, root: str) -> SystemdService | None:
    name_with_ext = os.path.basename(path)
    stem, ext = os.path.splitext(name_with_ext)

    try:
        source_path = '/' + os.path.relpath(path, root).replace(os.sep, '/')
    except ValueError:
        source_path = path

    ini = _read_unit_ini(path)
    unit_sec    = ini.get('Unit', {})
    svc_sec     = ini.get('Service', {})
    install_sec = ini.get('Install', {})

    return SystemdService(
        unit_name          = stem,
        unit_type          = ext.lstrip('.'),
        description        = _first(unit_sec,    'Description'),
        after              = _join(unit_sec,     'After'),
        wants              = _join(unit_sec,     'Wants'),
        requires           = _join(unit_sec,     'Requires'),
        exec_start         = _join(svc_sec,      'ExecStart'),
        exec_start_pre     = _join(svc_sec,      'ExecStartPre'),
        exec_start_post    = _join(svc_sec,      'ExecStartPost'),
        exec_stop          = _first(svc_sec,     'ExecStop'),
        run_user           = _first(svc_sec,     'User'),
        run_group          = _first(svc_sec,     'Group'),
        working_directory  = _first(svc_sec,     'WorkingDirectory'),
        service_type       = _first(svc_sec,     'Type'),
        restart            = _first(svc_sec,     'Restart'),
        environment        = _join(svc_sec,      'Environment'),
        wanted_by          = _join(install_sec,  'WantedBy'),
        source_file        = name_with_ext,
        source_path        = source_path,
        source_dir_type    = source_dir_type,
        source_file_modified = _mtime_utc(path),
    )
