"""flpcheck - find the samples an FL Studio project is missing."""

from __future__ import annotations

__version__ = "0.1.0"

from .check import (
    ProjectReport,
    SampleStatus,
    check_project,
    index_by_name,
)
from .scan import (
    FLP_MAGIC,
    SampleRef,
    looks_like_flp,
    scan_bytes,
    scan_file,
)

__all__ = [
    "FLP_MAGIC",
    "ProjectReport",
    "SampleRef",
    "SampleStatus",
    "__version__",
    "check_project",
    "index_by_name",
    "looks_like_flp",
    "scan_bytes",
    "scan_file",
]
