"""
Extracts system-level metadata from a UAC collection directory.

Uses a priority-ordered extractor registry: for each field, extractors are
tried in sequence and the first non-None result wins. Adding support for a new
OS or tool variant means writing a new extractor function and appending it to
the relevant list in EXTRACTORS — the core parse loop never changes.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

log = logging.getLogger(__name__)

# Matches UTC offset in forms: +1030, +10:30, -0500, -05:00
_OFFSET_RE = re.compile(r'([+-])(\d{2}):?(\d{2})')

# Known CPU architecture tokens
_ARCH_RE = re.compile(
    r'\b(x86_64|i[3-6]86|aarch64|arm64|armv[0-9]+l?|ppc64le?|s390x|riscv64|mips[0-9a-z]*)\b',
    re.IGNORECASE,
)


# ── Shared utilities ──────────────────────────────────────────────────────────

def normalise_offset(raw: str) -> Optional[str]:
    """Convert +1030, +10:30, -0500 etc. to +10:30 / -05:00 (ISO 8601)."""
    m = _OFFSET_RE.search(raw.strip())
    if not m:
        return None
    sign, hours, mins = m.groups()
    return f"{sign}{hours}:{mins}"


def _read(collection_path: str, *parts: str) -> Optional[str]:
    try:
        with open(os.path.join(collection_path, *parts), "r", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _first_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    line = text.strip().splitlines()[0].strip()
    return line or None


# ── Hostname ──────────────────────────────────────────────────────────────────

def _hostname_from_network_hostname_txt(p: str) -> Optional[str]:
    return _first_line(_read(p, "live_response", "network", "hostname.txt"))


def _hostname_from_etc_hostname(p: str) -> Optional[str]:
    return _first_line(_read(p, "[root]", "etc", "hostname"))


def _hostname_from_hostnamectl(p: str) -> Optional[str]:
    text = _read(p, "live_response", "network", "hostnamectl.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Static hostname:" in line:
            return line.split(":", 1)[1].strip() or None
    return None


def _hostname_from_uname(p: str) -> Optional[str]:
    text = _first_line(_read(p, "live_response", "system", "uname_-a.txt"))
    if text:
        parts = text.split()
        return parts[1] if len(parts) > 1 else None
    return None


# ── FQDN ──────────────────────────────────────────────────────────────────────

def _fqdn_from_hostname_f(p: str) -> Optional[str]:
    val = _first_line(_read(p, "live_response", "network", "hostname_-f.txt"))
    # Only meaningful if it contains a dot (i.e. is actually qualified)
    return val if val and "." in val else None


# ── Primary IP ────────────────────────────────────────────────────────────────

def _ip_from_ip_addr_show(p: str) -> Optional[str]:
    """Linux iproute2: skip loopback, return first inet address."""
    text = _read(p, "live_response", "network", "ip_addr_show.txt")
    if not text:
        return None
    skip_iface = False
    for line in text.splitlines():
        if re.match(r'^\d+:\s+lo:', line):
            skip_iface = True
        elif re.match(r'^\d+:\s+\S+:', line):
            skip_iface = False
        elif not skip_iface and "inet " in line:
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', line)
            if m:
                return m.group(1)
    return None


def _ip_from_netstat_v(p: str) -> Optional[str]:
    """macOS netstat -v: first non-loopback, non-wildcard tcp4 local address."""
    text = _read(p, "live_response", "network", "netstat_-v.txt")
    if not text:
        return None
    for line in text.splitlines():
        if not line.startswith("tcp4"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]  # "172.20.10.6.59712"
        ip = local.rsplit(".", 1)[0]
        if ip.startswith("127.") or ip in ("*", "localhost"):
            continue
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
            return ip
    return None


def _ip_from_ifconfig_txt(p: str) -> Optional[str]:
    """BSD/Solaris/older Linux ifconfig output."""
    text = _read(p, "live_response", "network", "ifconfig.txt")
    if not text:
        return None
    skip = False
    for line in text.splitlines():
        if re.match(r'^lo[0-9:]?\s', line) or re.match(r'^lo\b', line):
            skip = True
        elif re.match(r'^\S', line):
            skip = False
        if not skip:
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', line)
            if m and not m.group(1).startswith("127."):
                return m.group(1)
    return None


# ── OS name ───────────────────────────────────────────────────────────────────

def _os_from_sw_vers(p: str) -> Optional[str]:
    """macOS sw_vers."""
    text = _read(p, "live_response", "system", "sw_vers.txt")
    if not text:
        return None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    name = fields.get("ProductName")
    version = fields.get("ProductVersion")
    if name:
        return f"{name} {version}".strip() if version else name
    return None


def _os_from_lsb_release(p: str) -> Optional[str]:
    """Linux /etc/lsb-release DISTRIB_DESCRIPTION."""
    text = _read(p, "[root]", "etc", "lsb-release")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("DISTRIB_DESCRIPTION="):
            return line.split("=", 1)[1].strip().strip('"') or None
    return None


def _os_from_os_release(p: str) -> Optional[str]:
    """Linux/BSD /etc/os-release PRETTY_NAME."""
    text = _read(p, "[root]", "etc", "os-release")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"') or None
    return None


def _os_from_hostnamectl(p: str) -> Optional[str]:
    """Linux hostnamectl Operating System field."""
    text = _read(p, "live_response", "network", "hostnamectl.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Operating System:" in line:
            return line.split(":", 1)[1].strip() or None
    return None


def _os_from_issue(p: str) -> Optional[str]:
    """Linux /etc/issue — strip escape sequences like \\n \\l."""
    text = _first_line(_read(p, "[root]", "etc", "issue"))
    if not text:
        return None
    val = re.sub(r'\\\S+', '', text).strip()
    return val or None


def _os_from_uname(p: str) -> Optional[str]:
    """Last-resort: kernel type token from uname -a (e.g. 'Linux', 'Darwin')."""
    text = _first_line(_read(p, "live_response", "system", "uname_-a.txt"))
    if text:
        return text.split()[0] or None
    return None


# ── Kernel ────────────────────────────────────────────────────────────────────

def _kernel_from_uname(p: str) -> Optional[str]:
    return _first_line(_read(p, "live_response", "system", "uname_-a.txt"))


# ── CPU architecture ──────────────────────────────────────────────────────────

def _arch_from_uname(p: str) -> Optional[str]:
    """Scan uname -a for a known architecture token; take the last match."""
    text = _first_line(_read(p, "live_response", "system", "uname_-a.txt"))
    if not text:
        return None
    matches = _ARCH_RE.findall(text)
    return matches[-1].lower() if matches else None


def _arch_from_hostnamectl(p: str) -> Optional[str]:
    text = _read(p, "live_response", "network", "hostnamectl.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Architecture:" in line:
            return line.split(":", 1)[1].strip() or None
    return None


def _arch_from_sysctl(p: str) -> Optional[str]:
    """kernel.arch (Linux) or hw.machine (macOS/BSD) from sysctl -a."""
    text = _read(p, "live_response", "system", "sysctl_-a.txt")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("kernel.arch"):
            return line.split("=", 1)[1].strip() or None
        if line.startswith("hw.machine"):
            return line.split(":", 1)[1].strip() or None
    return None


# ── Timezone name ─────────────────────────────────────────────────────────────

def _tz_name_from_etc_timezone(p: str) -> Optional[str]:
    """Linux /etc/timezone — single IANA name."""
    return _first_line(_read(p, "[root]", "etc", "timezone"))


def _tz_name_from_timedatectl(p: str) -> Optional[str]:
    """Linux timedatectl: 'Time zone: Australia/Adelaide (ACDT, +1030)'."""
    text = _read(p, "live_response", "system", "timedatectl_status.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Time zone:" in line:
            val = line.split("Time zone:", 1)[1].strip()
            iana = val.split()[0]
            return iana if ("/" in iana or iana.upper() == "UTC") else None
    return None


# ── Timezone offset ───────────────────────────────────────────────────────────

def _tz_offset_from_timedatectl(p: str) -> Optional[str]:
    """Linux timedatectl: parse (+1030) from the Time zone line."""
    text = _read(p, "live_response", "system", "timedatectl_status.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Time zone:" in line:
            m = _OFFSET_RE.search(line)
            if m:
                return normalise_offset(m.group(0))
    return None


def _tz_offset_from_uac_log(p: str) -> Optional[str]:
    """Universal: parse offset from first timestamp line in uac.log."""
    text = _read(p, "uac.log")
    if not text:
        return None
    first = text.strip().splitlines()[0] if text.strip() else ""
    m = _OFFSET_RE.search(first)
    return normalise_offset(m.group(0)) if m else None


def _tz_offset_from_date_txt(p: str) -> Optional[str]:
    """Fallback: parse offset from system/date.txt if present."""
    text = _first_line(_read(p, "live_response", "system", "date.txt"))
    if not text:
        return None
    m = _OFFSET_RE.search(text)
    return normalise_offset(m.group(0)) if m else None


# ── Memory ────────────────────────────────────────────────────────────────────

def _memory_from_free(p: str) -> Optional[int]:
    """Linux 'free': Mem total in kibibytes → bytes."""
    text = _read(p, "live_response", "system", "free.txt")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            try:
                return int(parts[1]) * 1024
            except (IndexError, ValueError):
                pass
    return None


def _memory_from_sysctl_hw_memsize(p: str) -> Optional[int]:
    """macOS sysctl hw.memsize (bytes)."""
    text = _read(p, "live_response", "system", "sysctl_-a.txt")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("hw.memsize:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return None


def _memory_from_sysctl_hw_physmem(p: str) -> Optional[int]:
    """BSD sysctl hw.physmem (bytes)."""
    text = _read(p, "live_response", "system", "sysctl_-a.txt")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("hw.physmem:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return None


# ── Domain / realm ────────────────────────────────────────────────────────────

def _domain_from_sysctl_kernel(p: str) -> Optional[str]:
    """Linux kernel.domainname — None when unset."""
    text = _read(p, "live_response", "system", "sysctl_-a.txt")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("kernel.domainname"):
            val = line.split("=", 1)[1].strip()
            return None if val in ("(none)", "", "localdomain") else val
    return None


def _domain_from_scutil_dns(p: str) -> Optional[str]:
    """macOS scutil --dns: first search domain (skip Tailscale magic DNS)."""
    text = _read(p, "live_response", "network", "scutil_--dns.txt")
    if not text:
        return None
    for line in text.splitlines():
        m = re.search(r'search domain\[0\]\s*:\s*(\S+)', line)
        if m:
            val = m.group(1)
            return None if val.endswith(".ts.net") else val
    return None


def _domain_from_fqdn(p: str) -> Optional[str]:
    """Derive domain from FQDN if hostname_-f gives a qualified name."""
    fqdn = _fqdn_from_hostname_f(p)
    if fqdn and fqdn.count(".") >= 1:
        return fqdn.split(".", 1)[1]
    return None


# ── Hardware model ────────────────────────────────────────────────────────────

def _hwmodel_from_hostnamectl(p: str) -> Optional[str]:
    text = _read(p, "live_response", "network", "hostnamectl.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Hardware Model:" in line:
            return line.split(":", 1)[1].strip() or None
    return None


def _hwmodel_from_sysctl(p: str) -> Optional[str]:
    """macOS hw.model."""
    text = _read(p, "live_response", "system", "sysctl_-a.txt")
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith("hw.model:"):
            return line.split(":", 1)[1].strip() or None
    return None


# ── Virtualization ────────────────────────────────────────────────────────────

def _virt_from_hostnamectl(p: str) -> Optional[str]:
    """Linux systemd-detect-virt result from hostnamectl."""
    text = _read(p, "live_response", "network", "hostnamectl.txt")
    if not text:
        return None
    for line in text.splitlines():
        if "Virtualization:" in line:
            return line.split(":", 1)[1].strip() or None
    return None


# ── Registry ──────────────────────────────────────────────────────────────────
# Each value is an ordered list of extractor functions. The first non-None
# result is used. To support a new OS, add extractor functions above and
# append them here — the parse loop below never needs to change.

EXTRACTORS: dict[str, list] = {
    "hostname":        [_hostname_from_network_hostname_txt,
                        _hostname_from_etc_hostname,
                        _hostname_from_hostnamectl,
                        _hostname_from_uname],
    "fqdn":            [_fqdn_from_hostname_f],
    "primary_ip":      [_ip_from_ip_addr_show,
                        _ip_from_netstat_v,
                        _ip_from_ifconfig_txt],
    "os_name":         [_os_from_sw_vers,
                        _os_from_lsb_release,
                        _os_from_os_release,
                        _os_from_hostnamectl,
                        _os_from_issue,
                        _os_from_uname],
    "kernel":          [_kernel_from_uname],
    "cpu_arch":        [_arch_from_uname,
                        _arch_from_hostnamectl,
                        _arch_from_sysctl],
    "timezone_name":   [_tz_name_from_etc_timezone,
                        _tz_name_from_timedatectl],
    "timezone_offset": [_tz_offset_from_timedatectl,
                        _tz_offset_from_uac_log,
                        _tz_offset_from_date_txt],
    "memory_bytes":    [_memory_from_free,
                        _memory_from_sysctl_hw_memsize,
                        _memory_from_sysctl_hw_physmem],
    "domain":          [_domain_from_sysctl_kernel,
                        _domain_from_scutil_dns,
                        _domain_from_fqdn],
    "hardware_model":  [_hwmodel_from_hostnamectl,
                        _hwmodel_from_sysctl],
    "virtualization":  [_virt_from_hostnamectl],
}


def parse_system_info(uac_collection_path: str):
    """
    Run all extractor chains and return a SystemInfo ORM object, or None if
    nothing could be extracted. Import is deferred to avoid circular imports
    at module load time.
    """
    from uac_parser.models import SystemInfo

    result: dict = {}
    for field, extractors in EXTRACTORS.items():
        for fn in extractors:
            try:
                val = fn(uac_collection_path)
            except Exception:
                log.debug("Extractor %s raised an exception", fn.__name__, exc_info=True)
                val = None
            if val is not None:
                result[field] = val
                break

    if not result:
        log.warning("SystemInfo: no fields could be extracted from %s", uac_collection_path)
        return None

    log.info("SystemInfo extracted %d fields from %s", len(result), uac_collection_path)
    return SystemInfo(**result)
