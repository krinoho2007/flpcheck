"""Command line interface for flpcheck."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .check import check_project, index_by_name
from .scan import scan_bytes

__all__ = ["main"]

TICK = "\u2713"  # heavy check mark
CROSS = "\u2717"  # ballot x
QUESTION = "?"

EXIT_OK = 0
EXIT_FOUND = 1
EXIT_ERROR = 2


def _use_utf8_stdout() -> None:
    """Windows consoles default to a legacy code page that cannot encode
    check marks; without this the tool crashes on output rather than on logic.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def _parse_macros(specs: list[str], parser: argparse.ArgumentParser) -> dict[str, str]:
    """Turn ``NAME=DIR`` strings into a macro map."""
    macros: dict[str, str] = {}
    for spec in specs:
        name, separator, value = spec.partition("=")
        if not separator or not name or not value:
            parser.error(f"--macro expects NAME=DIR, got {spec!r}")
        macros[name] = value
    return macros


def _iter_flp_files(directory: Path):
    """Yield .flp files under ``directory`` (case-insensitive extension)."""
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".flp":
            yield path


def _print_report(report, stream) -> None:
    print(report.project, file=stream)
    if not report.looks_like_flp:
        print("  ! missing 'FLhd' header: this may not be an FL Studio project", file=stream)

    summary = f"  samples: {report.total} referenced, {report.ok} ok, {report.missing_count} missing"
    if report.unresolved_count:
        summary += f", {report.unresolved_count} unresolved"
    print(summary, file=stream)

    if not report.missing and not report.unresolved:
        return

    if report.missing:
        print("", file=stream)
        for item in report.missing:
            print(f"  {CROSS} {item.filename}", file=stream)
            print(f"      referenced as: {item.path}", file=stream)
            if item.resolved:
                print(f"      resolved to:   {item.resolved}", file=stream)
            if item.candidates:
                print("      found:", file=stream)
                for candidate in item.candidates:
                    print(f"        {candidate}", file=stream)
            elif report.searched:
                print("      not found in the search roots", file=stream)

    if report.unresolved:
        print("", file=stream)
        for item in report.unresolved:
            print(f"  {QUESTION} {item.filename}", file=stream)
            print(f"      referenced as: {item.path}", file=stream)
            print(
                "      not checked: this path uses an FL Studio macro. "
                "Map it with --macro NAME=DIR",
                file=stream,
            )
            if item.candidates:
                print("      found by name:", file=stream)
                for candidate in item.candidates:
                    print(f"        {candidate}", file=stream)

    if report.index_truncated:
        print(
            "\n  ! the file index was truncated; some samples may be marked as "
            "missing only because the search stopped early",
            file=stream,
        )


def _build_index(roots: list[str], max_files: int):
    if not roots:
        return None, False
    return index_by_name(roots, max_files=max_files)


def _cmd_check(args, parser: argparse.ArgumentParser) -> int:
    macros = _parse_macros(args.macro, parser)

    index, truncated = (None, False)
    if not args.no_search:
        index, truncated = _build_index(args.search_root, args.max_index_files)

    reports = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if not path.is_file():
            print(f"error: not a file: {path}", file=sys.stderr)
            return EXIT_ERROR
        try:
            report = check_project(
                path, index=index, max_candidates=args.max_candidates, macros=macros
            )
        except OSError as exc:
            print(f"error: cannot read {path}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        report.index_truncated = truncated
        reports.append(report)

    if args.json:
        payload = reports[0].to_dict() if len(reports) == 1 else [r.to_dict() for r in reports]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for position, report in enumerate(reports):
            if position:
                print()
            _print_report(report, sys.stdout)

    return EXIT_FOUND if any(r.missing_count for r in reports) else EXIT_OK


def _cmd_find(args, parser: argparse.ArgumentParser) -> int:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return EXIT_ERROR

    needle = args.sample.casefold()
    matches = []

    for project in _iter_flp_files(directory):
        try:
            refs = scan_bytes(project.read_bytes())
        except OSError as exc:
            print(f"warning: cannot read {project}: {exc}", file=sys.stderr)
            continue

        if args.exact:
            hits = [r for r in refs if r.filename.casefold() == needle]
        else:
            hits = [r for r in refs if needle in r.filename.casefold()]

        if hits:
            matches.append((project, hits))

    if args.json:
        payload = [
            {"project": str(project), "samples": [r.path for r in hits]}
            for project, hits in matches
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if not matches:
            print(f"no project under {directory} references {args.sample!r}")
        for project, hits in matches:
            print(f"{project}  ({len(hits)} match{'es' if len(hits) > 1 else ''})")
            for ref in hits:
                print(f"  {ref.path}")

    return EXIT_OK if matches else EXIT_FOUND


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flpcheck",
        description="Report which samples an FL Studio project references and which are missing.",
    )
    parser.add_argument("--version", action="version", version=f"flpcheck {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check", help="check one or more .flp files for missing samples"
    )
    check.add_argument("paths", nargs="+", metavar="PATH", help=".flp file(s) to check")
    check.add_argument(
        "--search-root",
        action="append",
        default=[],
        metavar="DIR",
        help="directory to search for samples that are no longer at their referenced "
        "path (repeatable)",
    )
    check.add_argument(
        "--macro",
        action="append",
        default=[],
        metavar="NAME=DIR",
        help="directory an FL Studio macro expands to, e.g. "
        "'%%FLStudioFactoryData%%=D:\\FL\\Data' (repeatable)",
    )
    check.add_argument(
        "--no-search", action="store_true", help="only report, do not look for candidates"
    )
    check.add_argument(
        "--max-candidates", type=int, default=3, metavar="N", help="candidates per sample (default: 3)"
    )
    check.add_argument(
        "--max-index-files",
        type=int,
        default=200_000,
        metavar="N",
        help="cap on files indexed per search root (default: 200000)",
    )
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.set_defaults(func=_cmd_check)

    find = subparsers.add_parser(
        "find", help="search across many .flp files for a sample name"
    )
    find.add_argument("directory", metavar="DIR", help="directory to scan for .flp files")
    find.add_argument("--sample", required=True, metavar="NAME", help="sample filename or fragment")
    find.add_argument(
        "--exact", action="store_true", help="match the whole filename instead of a fragment"
    )
    find.add_argument("--json", action="store_true", help="machine-readable output")
    find.set_defaults(func=_cmd_find)

    return parser


def main(argv: list[str] | None = None) -> int:
    _use_utf8_stdout()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
