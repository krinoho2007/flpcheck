"""Locate sample references inside FL Studio project files (``.flp``).

``.flp`` is a binary format. Rather than depend on a third-party parser for
v0.1, this module looks for path-shaped strings: FL Studio stores them as
UTF-16LE, which is why a plain ASCII/UTF-8 grep over the raw bytes finds
nothing.

Design rule: this module is strictly read-only. It opens project files with
``read_bytes`` and never writes to them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "FLP_MAGIC",
    "SampleRef",
    "looks_like_flp",
    "scan_bytes",
    "scan_file",
]

# Every FL Studio project file starts with this chunk id.
FLP_MAGIC = b"FLhd"

# Longest alternative first, so ``.wave`` is not truncated to ``.wav``.
#
# The two long forms need a guard, and it is not a cosmetic one. Paths are
# stored back to back, so ``...\riser.wav`` can be followed immediately by
# ``E:\...``. With IGNORECASE, ``.wavE`` then matches the ``wave`` branch and
# swallows the next path's drive letter. A drive letter is always followed by
# ``:``, so excluding that one character keeps ``wave``/``aiff`` working while
# leaving the next path intact.
_AUDIO_EXT = (
    r"(?:"
    r"wave(?![A-Za-z0-9:])"
    r"|aiff(?![A-Za-z0-9:])"
    r"|wav|aif|flac|mp3|opus|ogg|sf2|rx2|rex"
    r")"
)

# Characters Windows forbids in a path. Excluding them stops a match from
# running past the end of a string and into adjacent binary data.
_FORBIDDEN = r'[^\x00<>:"|?*\r\n]'

# No trailing ``(?![A-Za-z0-9])`` guard on purpose: FL Studio stores strings
# back to back, so requiring a separator after the extension would drop the
# first of two adjacent paths.
_WIN_PATH = re.compile(
    r"[A-Za-z]:[\\/]" + _FORBIDDEN + r"{1,400}\." + _AUDIO_EXT,
    re.IGNORECASE,
)

# FL Studio 20.8+ also runs on macOS and projects get shared across
# platforms, so absolute POSIX paths are worth collecting too.
_POSIX_PATH = re.compile(
    r"/(?:Users|Volumes|home)/" + _FORBIDDEN + r"{1,400}\." + _AUDIO_EXT,
    re.IGNORECASE,
)

# Not every reference is absolute. Factory and user packs are referenced
# through FL Studio's own macros, and on real projects these outnumber
# drive-letter paths several times over:
#   %FLStudioFactoryData%\drums\...\2Hihat.wav
# They cannot be checked without knowing where the macro points, but they must
# still be found, or a project silently looks like it has no samples at all.
_MACRO_PATH = re.compile(
    r"%[A-Za-z][A-Za-z0-9_]*%[\\/]" + _FORBIDDEN + r"{1,400}\." + _AUDIO_EXT,
    re.IGNORECASE,
)
_MACRO_NAME = re.compile(r"%[A-Za-z][A-Za-z0-9_]*%")

_PATTERNS = (
    ("drive", _WIN_PATH),
    ("posix", _POSIX_PATH),
    ("macro", _MACRO_PATH),
)


@dataclass(frozen=True)
class SampleRef:
    """A single sample reference exactly as it is embedded in the project."""

    path: str
    source: str = "utf16"
    macro: str | None = None

    @property
    def filename(self) -> str:
        """Basename, tolerant of whatever separator the project used."""
        return Path(self.path.replace("\\", "/")).name


def _dedupe_key(path: str) -> str:
    """Case-insensitive key: Windows paths are case-insensitive in practice."""
    return path.replace("\\", "/").casefold()


def _decode_variants(raw: bytes):
    """Yield ``(source, text)`` pairs worth scanning.

    FL Studio writes UTF-16LE, but the alignment is not fixed: an event header
    is a one-byte id plus a variable-width length, so a string can begin at an
    even or an odd byte offset. On a real project, one of six sample paths
    started at an odd offset and was invisible to an aligned-only scan, so both
    offsets are decoded and the results merged.

    The UTF-8 pass costs nothing and covers builds that store occasional
    strings differently.
    """
    yield "utf16", raw.decode("utf-16-le", errors="ignore")
    if len(raw) > 1:
        yield "utf16+1", raw[1:].decode("utf-16-le", errors="ignore")
    yield "utf8", raw.decode("utf-8", errors="ignore")


def scan_bytes(raw: bytes) -> list[SampleRef]:
    """Return every distinct sample reference found in ``raw`` project bytes."""
    found: dict[str, SampleRef] = {}
    for source, text in _decode_variants(raw):
        for kind, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                candidate = match.group(0)
                key = _dedupe_key(candidate)
                if key in found:
                    continue
                macro = None
                if kind == "macro":
                    name = _MACRO_NAME.match(candidate)
                    macro = name.group(0) if name else None
                found[key] = SampleRef(candidate, source, macro)
    return sorted(found.values(), key=lambda ref: ref.path.casefold())


def looks_like_flp(raw: bytes) -> bool:
    """Cheap sanity check so a wrong file produces a warning, not silence."""
    return raw[:4] == FLP_MAGIC


def scan_file(project_path: str | Path) -> list[SampleRef]:
    """Read ``project_path`` and return its sample references."""
    return scan_bytes(Path(project_path).read_bytes())
