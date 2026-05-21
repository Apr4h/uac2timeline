"""
Drop-in replacement for pygrok.Grok.

Uses the `regex` package (superset of `re`) which allows duplicate named
groups inside alternation branches — required by patterns like SS_LINUX.
"""
import re
import regex
from typing import Optional

_GROK_REF = re.compile(r'%\{(\w+)(?::(\w+))?\}')
_NAMED_GROUP = re.compile(r'\(\?P?<\w+>')

BASE_PATTERNS: dict[str, str] = {
    "INT":              r"[+-]?[0-9]+",
    "NUMBER":           r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)",
    "POSINT":           r"[1-9][0-9]*",
    "NONNEGINT":        r"[0-9]+",
    "WORD":             r"\b\w+\b",
    "NOTSPACE":         r"\S+",
    "SPACE":            r"\s*",
    "DATA":             r".*?",
    "GREEDYDATA":       r".*",

    # Network
    "IP":       (
        r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
        r"(?:\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)){3}"
    ),
    "HOSTNAME": (
        r"(?:[0-9A-Za-z][0-9A-Za-z\-]{0,62})"
        r"(?:\.(?:[0-9A-Za-z][0-9A-Za-z\-]{0,62}))*\.?"
    ),
    "IPORHOST": (
        r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?:\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)){3}"
        r"|(?:[0-9A-Za-z][0-9A-Za-z\-]{0,62})(?:\.(?:[0-9A-Za-z][0-9A-Za-z\-]{0,62}))*\.?)"
    ),
    "HOST": (
        r"(?:[0-9A-Za-z][0-9A-Za-z\-]{0,62})"
        r"(?:\.(?:[0-9A-Za-z][0-9A-Za-z\-]{0,62}))*\.?"
    ),

    # Paths
    "UNIXPATH": r"(?:/[\w_%!$@:.,+\-]*)+",

    # Auth / identity
    "USERNAME": r"[a-zA-Z0-9._-]+",
    "USER":     r"[a-zA-Z0-9._-]+",

    # Date / time components
    "MONTH":    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)",
    "MONTHNUM": r"(?:0?[1-9]|1[0-2])",
    "MONTHNUM2":r"(?:0[1-9]|1[0-2])",
    "MONTHDAY": r"(?:0[1-9]|[12][0-9]|3[01]|[1-9])",
    "DAY":      r"(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)",
    "YEAR":     r"(?:\d\d){1,2}",
    "HOUR":     r"(?:2[0123]|[01]?[0-9])",
    "MINUTE":   r"[0-5][0-9]",
    "SECOND":   r"(?:[0-5]?[0-9]|60)(?:[.,][0-9]+)?",
    "TIME":     r"(?:2[0123]|[01]?[0-9]):[0-5][0-9](?::(?:[0-5]?[0-9]|60)(?:[.,][0-9]+)?)?",

    # ISO 8601
    "ISO8601_TIMEZONE":  r"(?:Z|[+-](?:2[0123]|[01]?[0-9]):?[0-5][0-9])",
    "TIMESTAMP_ISO8601": (
        r"(?:\d\d){1,2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
        r"[T ](?:2[0123]|[01]?[0-9]):?[0-5][0-9]"
        r"(?::?(?:[0-5]?[0-9]|60)(?:[.,][0-9]+)?)?"
        r"(?:Z|[+-](?:2[0123]|[01]?[0-9]):?[0-5][0-9])?"
    ),
}


class Grok:
    """
    Compiles a grok pattern to a Python regex and matches lines against it.

    Supported syntax:
      %{PATTERN_NAME}            – expand pattern, non-capturing
      %{PATTERN_NAME:field}      – expand pattern, capture as 'field'
      (?<field>...)  /  (?P<field>...)  – inline named capture
    """

    def __init__(self, pattern: str, custom_patterns: Optional[dict] = None):
        self._pats = dict(BASE_PATTERNS)
        if custom_patterns:
            self._pats.update(custom_patterns)

        regex_str = self._compile(pattern)
        try:
            self._regex = regex.compile(regex_str)
        except regex.error as exc:
            raise ValueError(f"Failed to compile grok pattern: {exc}\nResolved: {regex_str}") from exc

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve(self, name: str, _seen: frozenset = frozenset()) -> str:
        """Expand a named pattern to a plain regex (no named groups, no %{} refs)."""
        if name in _seen or name not in self._pats:
            return ".*?"
        pat = self._pats[name]
        seen = _seen | {name}

        def rep(m: re.Match) -> str:
            return f"(?:{self._resolve(m.group(1), seen)})"

        expanded = _GROK_REF.sub(rep, pat)
        # Strip any named groups that crept in from stored patterns
        expanded = _NAMED_GROUP.sub("(?:", expanded)
        return expanded

    def _compile(self, pattern: str) -> str:
        """Convert a grok pattern to a Python/regex named-group regex string."""
        # Step 1 – expand %{NAME:field} and %{NAME}
        def expand_ref(m: re.Match) -> str:
            pname, cname = m.group(1), m.group(2)
            resolved = self._resolve(pname)
            if cname:
                return f"(?P<{cname}>{resolved})"
            return f"(?:{resolved})"

        result = _GROK_REF.sub(expand_ref, pattern)

        # Step 2 – normalise inline (?<name>...) to (?P<name>...)
        result = re.sub(r"\(\?<(\w+)>", r"(?P<\1>", result)

        return result

    # ── Public API ────────────────────────────────────────────────────────────

    def match(self, text: str) -> Optional[dict]:
        """
        Match *text* against the compiled pattern.

        Returns a dict of captured fields (omitting None values), or None if
        the line does not match.
        """
        m = self._regex.match(text.rstrip("\n\r"))
        if m is None:
            return None
        return {k: v for k, v in m.groupdict().items() if v is not None}
