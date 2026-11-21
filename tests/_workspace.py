"""Scratch directories for tests.

``tempfile.mkdtemp`` creates directories with mode ``0o700``. On Windows that
maps to permissions that a restricted token cannot write into, and tools such
as DSH sandboxes run tests under exactly such a token. A plain ``mkdir`` keeps
the inherited permissions, so tests create their own uniquely named directory
instead.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

__all__ = ["drop_workspace", "new_workspace"]


def _base() -> Path:
    return Path(tempfile.gettempdir()) / "flpcheck-tests"


def new_workspace(label: str = "case") -> Path:
    """Create and return a fresh, writable scratch directory."""
    base = _base()
    base.mkdir(parents=True, exist_ok=True)
    workspace = base / f"{label}-{uuid.uuid4().hex[:12]}"
    workspace.mkdir()
    return workspace


def drop_workspace(workspace: Path) -> None:
    """Remove a scratch directory, ignoring failures (Windows holds handles)."""
    shutil.rmtree(workspace, ignore_errors=True)
