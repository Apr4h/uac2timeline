import datetime
import logging
import os

from uac_parser.models import RcScript

# Maximum content snippet length stored per file
_SNIPPET_MAX_CHARS = 4000
_SNIPPET_MAX_LINES = 50

# System-wide files and directories to scan.
# Each entry: (relative_path, source_type, run_context, is_dir)
_SYSTEM_ENTRIES = [
    # SysV / common Linux
    ('etc/rc.local',            'system-init', 'boot',        False),
    ('etc/rc',                  'system-init', 'boot',        False),
    ('etc/rc.conf',             'system-init', 'boot',        False),
    ('etc/rc.conf.d',           'system-init', 'boot',        True),
    ('etc/rc.d',                'bsd-rcd',     'boot',        True),
    ('etc/init.d',              'system-init', 'boot',        True),
    ('usr/local/etc/rc.d',      'bsd-rcd',     'boot',        True),
    # Runlevel symlink directories — record the link targets that are regular files
    ('etc/rc0.d',  'system-init', 'boot', True),
    ('etc/rc1.d',  'system-init', 'boot', True),
    ('etc/rc2.d',  'system-init', 'boot', True),
    ('etc/rc3.d',  'system-init', 'boot', True),
    ('etc/rc4.d',  'system-init', 'boot', True),
    ('etc/rc5.d',  'system-init', 'boot', True),
    ('etc/rc6.d',  'system-init', 'boot', True),
    ('etc/rcS.d',  'system-init', 'boot', True),
    # macOS startup items (pre-launchd, still observed in forensic collections)
    ('Library/StartupItems',        'startup-item', 'boot', True),
    ('System/Library/StartupItems', 'startup-item', 'boot', True),
    # System-wide shell profile / rc files
    ('etc/profile',        'profile', 'login',       False),
    ('etc/profile.d',      'profile-d', 'login',     True),
    ('etc/bashrc',         'shellrc', 'interactive',  False),
    ('etc/bash.bashrc',    'shellrc', 'interactive',  False),
    ('etc/zshrc',          'shellrc', 'interactive',  False),
    ('etc/zsh/zshrc',      'shellrc', 'interactive',  False),
    ('etc/zsh/zprofile',   'profile', 'login',        False),
    ('etc/zsh/zshenv',     'profile', 'login',        False),
    ('etc/zsh/zlogin',     'profile', 'login',        False),
    ('etc/csh.cshrc',      'shellrc', 'interactive',  False),
    ('etc/csh.login',      'profile', 'login',        False),
    ('etc/kshrc',          'shellrc', 'interactive',  False),
]

# Per-user dotfiles to look for inside each home directory.
# (filename, source_type, run_context)
_USER_DOTFILES = [
    ('.profile',       'profile', 'login'),
    ('.bash_profile',  'profile', 'login'),
    ('.bash_login',    'profile', 'login'),
    ('.bashrc',        'shellrc', 'interactive'),
    ('.bash_logout',   'profile', 'logout'),
    ('.zshrc',         'shellrc', 'interactive'),
    ('.zprofile',      'profile', 'login'),
    ('.zlogin',        'profile', 'login'),
    ('.zlogout',       'profile', 'logout'),
    ('.zshenv',        'profile', 'login'),
    ('.kshrc',         'shellrc', 'interactive'),
    ('.mkshrc',        'shellrc', 'interactive'),
    ('.tcshrc',        'shellrc', 'interactive'),
    ('.cshrc',         'shellrc', 'interactive'),
    ('.xinitrc',       'session', 'session'),
    ('.xsession',      'session', 'session'),
]

# Shell inferred from filename; checked before shebang (shebang takes priority)
_FILENAME_SHELL = {
    '.bashrc': 'bash', '.bash_profile': 'bash', '.bash_login': 'bash',
    '.bash_logout': 'bash', 'bashrc': 'bash', 'bash.bashrc': 'bash',
    '.zshrc': 'zsh', '.zprofile': 'zsh', '.zlogin': 'zsh', '.zlogout': 'zsh',
    '.zshenv': 'zsh', 'zshrc': 'zsh', 'zprofile': 'zsh',
    '.kshrc': 'ksh', '.mkshrc': 'ksh', 'kshrc': 'ksh',
    '.tcshrc': 'tcsh', '.cshrc': 'csh', 'csh.cshrc': 'csh', 'csh.login': 'csh',
    '.xinitrc': 'sh', '.xsession': 'sh',
    'rc.local': 'sh', 'rc': 'sh', 'rc.conf': 'sh',
    '.profile': 'sh', 'profile': 'sh',
}

# Shebang → normalised shell name
_SHEBANG_SHELL = {
    'bash': 'bash', 'sh': 'sh', 'zsh': 'zsh', 'ksh': 'ksh', 'ksh93': 'ksh',
    'mksh': 'ksh', 'dash': 'sh', 'ash': 'sh', 'csh': 'csh', 'tcsh': 'tcsh',
    'fish': 'fish', 'python': 'python', 'python3': 'python', 'perl': 'perl',
    'ruby': 'ruby',
}


def parse_rc_scripts(uac_collection_path: str) -> list[RcScript]:
    logging.info("Parsing RC scripts")
    root = os.path.join(uac_collection_path, '[root]')
    if not os.path.exists(root):
        logging.warning("[root] directory not found; skipping rc scripts parse")
        return []

    results: list[RcScript] = []
    seen: set[str] = set()  # deduplicate by resolved real path

    # 1. System-wide entries
    for rel, source_type, run_context, is_dir in _SYSTEM_ENTRIES:
        abs_path = os.path.join(root, rel)
        if is_dir:
            if not os.path.isdir(abs_path):
                continue
            for fname in sorted(os.listdir(abs_path)):
                fpath = os.path.join(abs_path, fname)
                # Resolve symlinks so we don't double-count init.d entries
                # that appear in both init.d/ and rcN.d/
                real = os.path.realpath(fpath)
                if not os.path.isfile(real) or real in seen:
                    continue
                seen.add(real)
                virtual_path = f'/{rel}/{fname}'
                rec = _make_record(fpath, virtual_path, source_type, run_context, username=None)
                if rec:
                    results.append(rec)
        else:
            if not os.path.isfile(abs_path):
                continue
            real = os.path.realpath(abs_path)
            if real in seen:
                continue
            seen.add(real)
            rec = _make_record(abs_path, f'/{rel}', source_type, run_context, username=None)
            if rec:
                results.append(rec)

    # 2. Per-user dotfiles
    for homes_dir in ('home', 'Users'):
        homes_abs = os.path.join(root, homes_dir)
        if not os.path.isdir(homes_abs):
            continue
        for username in sorted(os.listdir(homes_abs)):
            user_home = os.path.join(homes_abs, username)
            if not os.path.isdir(user_home):
                continue
            for fname, source_type, run_context in _USER_DOTFILES:
                fpath = os.path.join(user_home, fname)
                if not os.path.isfile(fpath):
                    continue
                real = os.path.realpath(fpath)
                if real in seen:
                    continue
                seen.add(real)
                virtual_path = f'/{homes_dir}/{username}/{fname}'
                rec = _make_record(fpath, virtual_path, source_type, run_context, username=username)
                if rec:
                    results.append(rec)

    # 3. root user dotfiles (home is typically /root)
    root_home = os.path.join(root, 'root')
    if os.path.isdir(root_home):
        for fname, source_type, run_context in _USER_DOTFILES:
            fpath = os.path.join(root_home, fname)
            if not os.path.isfile(fpath):
                continue
            real = os.path.realpath(fpath)
            if real in seen:
                continue
            seen.add(real)
            rec = _make_record(fpath, f'/root/{fname}', source_type, run_context, username='root')
            if rec:
                results.append(rec)

    logging.info("Parsed %d RC script entries", len(results))
    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mtime_utc(path: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.utcfromtimestamp(os.path.getmtime(path))
    except OSError:
        return None


def _is_binary(path: str) -> bool:
    try:
        with open(path, 'rb') as f:
            return b'\x00' in f.read(512)
    except OSError:
        return True


def _read_content(path: str) -> tuple[str | None, str | None]:
    """Return (interpreter, content_snippet). interpreter is the shebang line or None."""
    try:
        with open(path, 'r', errors='replace') as f:
            lines = []
            interpreter = None
            collected = 0
            for raw in f:
                line = raw.rstrip('\n')
                if interpreter is None and line.startswith('#!'):
                    interpreter = line.strip()
                # include non-blank, non-pure-comment lines in snippet
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    lines.append(line)
                    collected += 1
                    if collected >= _SNIPPET_MAX_LINES:
                        break
        snippet = '\n'.join(lines)
        if len(snippet) > _SNIPPET_MAX_CHARS:
            snippet = snippet[:_SNIPPET_MAX_CHARS]
        return interpreter, snippet or None
    except OSError:
        return None, None


def _detect_shell(filename: str, interpreter: str | None) -> str:
    # Shebang takes priority
    if interpreter:
        # e.g. #!/usr/bin/env bash  or  #!/bin/bash
        parts = interpreter.lstrip('#!').split()
        if parts:
            binary = os.path.basename(parts[-1] if parts[0] in ('env', '/usr/bin/env') else parts[0])
            shell = _SHEBANG_SHELL.get(binary)
            if shell:
                return shell
    # Fall back to filename
    return _FILENAME_SHELL.get(os.path.basename(filename), 'unknown')


def _make_record(
    abs_path: str,
    virtual_path: str,
    source_type: str,
    run_context: str,
    username: str | None,
) -> RcScript | None:
    if _is_binary(abs_path):
        return None
    interpreter, snippet = _read_content(abs_path)
    shell = _detect_shell(abs_path, interpreter)
    try:
        size = os.path.getsize(abs_path)
    except OSError:
        size = None
    return RcScript(
        path=virtual_path,
        source_type=source_type,
        run_context=run_context,
        username=username,
        shell=shell,
        interpreter=interpreter,
        file_size=size,
        content_snippet=snippet,
        source_file_modified=_mtime_utc(abs_path),
    )
