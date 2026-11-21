"""Decide which of a project's samples are still reachable."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .scan import SampleRef, looks_like_flp, scan_bytes

__all__ = [
    "AUDIO_SUFFIXES",
    "ProjectReport",
    "SampleStatus",
    "check_project",
    "index_by_name",
]

AUDIO_SUFFIXES = frozenset(
    {".wav", ".wave", ".mp3", ".flac", ".aif", ".aiff", ".ogg", ".opus", ".sf2", ".rx2", ".rex"}
)


@dataclass(frozen=True)
class SampleStatus:
    """One sample reference and what we know about it.

    ``unresolved`` marks a reference that cannot be checked at all: it uses an
    FL Studio macro (``%FLStudioFactoryData%``) that the caller did not map to a
    directory. Those are reported separately from missing files, because
    calling them "missing" would be a false alarm.
    """

    path: str
    filename: str
    unresolved: bool = False
    resolved: str | None = None
    candidates: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "filename": self.filename,
            "resolved": self.resolved,
            "candidates": list(self.candidates),
        }


@dataclass
class ProjectReport:
    """The result of checking one project file."""

    project: str
    looks_like_flp: bool
    total: int
    ok: int
    missing: list[SampleStatus] = field(default_factory=list)
    unresolved: list[SampleStatus] = field(default_factory=list)
    searched: bool = False
    index_truncated: bool = False

    @property
    def missing_count(self) -> int:
        return len(self.missing)

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved)

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "looks_like_flp": self.looks_like_flp,
            "total": self.total,
            "ok": self.ok,
            "missing_count": self.missing_count,
            "unresolved_count": self.unresolved_count,
            "searched": self.searched,
            "index_truncated": self.index_truncated,
            "missing": [item.to_dict() for item in self.missing],
            "unresolved": [item.to_dict() for item in self.unresolved],
        }


def index_by_name(
    roots: Iterable[str], *, max_files: int = 200_000
) -> tuple[dict[str, list[str]], bool]:
    """Map lowercase filename -> absolute paths, walking each root once.

    Walking once and then looking up by name is far cheaper than running a
    recursive glob per missing sample: a project with 40 missing samples would
    otherwise walk the whole library 40 times.

    Returns ``(index, truncated)``. ``truncated`` is True when ``max_files``
    was hit, so the caller can say the search was incomplete instead of
    implying "not found".
    """
    index: dict[str, list[str]] = {}
    seen = 0
    truncated = False

    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in filenames:
                if os.path.splitext(name)[1].lower() not in AUDIO_SUFFIXES:
                    continue
                if seen >= max_files:
                    truncated = True
                    break
                index.setdefault(name.casefold(), []).append(os.path.join(dirpath, name))
                seen += 1
            if truncated:
                break
        if truncated:
            break

    return index, truncated


def _resolve(ref: SampleRef, macros: dict[str, str]) -> Path | None:
    """Absolute path for ``ref``, or None when it cannot be resolved."""
    if not ref.macro:
        return Path(ref.path)

    target = macros.get(ref.macro.casefold())
    if target is None:
        return None

    rest = ref.path[len(ref.macro) :].lstrip("\\/").replace("\\", "/")
    return Path(target) / rest


def check_project(
    project_path: str | Path,
    *,
    index: dict[str, list[str]] | None = None,
    max_candidates: int = 3,
    macros: dict[str, str] | None = None,
) -> ProjectReport:
    """Check one project file. Read-only; the project file is never modified.

    ``macros`` maps a macro name (``%FLStudioFactoryData%``) to the directory
    it expands to. Unmapped macros are reported as unresolved, not missing.
    """
    project = Path(project_path)
    raw = project.read_bytes()
    refs = scan_bytes(raw)

    # Macro names are matched case-insensitively; users should not have to
    # reproduce FL Studio's capitalisation exactly.
    lookup = {name.casefold(): value for name, value in (macros or {}).items()}

    missing: list[SampleStatus] = []
    unresolved: list[SampleStatus] = []
    ok = 0

    for ref in refs:
        target = _resolve(ref, lookup)
        candidates: tuple[str, ...] = ()
        if index is not None:
            hits = index.get(ref.filename.casefold(), ())
            candidates = tuple(hits[:max_candidates])

        if target is None:
            unresolved.append(
                SampleStatus(
                    path=ref.path, filename=ref.filename, unresolved=True, candidates=candidates
                )
            )
            continue

        # is_file() rather than exists(): a directory named like a sample is
        # not a usable sample, and reporting it as present would mislead.
        if target.is_file():
            ok += 1
            continue

        missing.append(
            SampleStatus(
                path=ref.path,
                filename=ref.filename,
                resolved=str(target) if ref.macro else None,
                candidates=candidates,
            )
        )

    return ProjectReport(
        project=str(project),
        looks_like_flp=looks_like_flp(raw),
        total=len(refs),
        ok=ok,
        missing=missing,
        unresolved=unresolved,
        searched=index is not None,
    )
