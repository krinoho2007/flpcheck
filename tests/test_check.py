"""Tests for missing-sample detection and candidate search."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from flpcheck import check_project, index_by_name
from flpcheck.cli import EXIT_ERROR, EXIT_FOUND, EXIT_OK, main

from ._workspace import drop_workspace, new_workspace

FLP_MAGIC = b"FLhd"


def make_project(*paths: str) -> bytes:
    body = b"".join(path.encode("utf-16-le") for path in paths)
    return FLP_MAGIC + b"\x00" * 8 + body + b"FLdt"


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self):
        self.root = new_workspace(self.__class__.__name__)
        self.addCleanup(drop_workspace, self.root)

    def write_project(self, name: str, *references: str) -> Path:
        project = self.root / name
        project.write_bytes(make_project(*references))
        return project

    def touch_sample(self, relative: str) -> Path:
        sample = self.root / relative
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_bytes(b"RIFF....WAVEfmt ")
        return sample


class CheckProjectTest(WorkspaceTestCase):
    def test_all_present(self):
        sample = self.touch_sample("Samples/kick.wav")
        project = self.write_project("song.flp", str(sample))

        report = check_project(project)

        self.assertEqual(report.total, 1)
        self.assertEqual(report.ok, 1)
        self.assertEqual(report.missing_count, 0)
        self.assertTrue(report.looks_like_flp)

    def test_missing_sample_is_reported(self):
        project = self.write_project("song.flp", r"D:\Gone\bass_final_v3.wav")

        report = check_project(project)

        self.assertEqual(report.total, 1)
        self.assertEqual(report.ok, 0)
        self.assertEqual(report.missing_count, 1)
        self.assertEqual(report.missing[0].filename, "bass_final_v3.wav")

    def test_mixed_present_and_missing(self):
        keep = self.touch_sample("Samples/vox.wav")
        project = self.write_project(
            "song.flp", str(keep), r"D:\Gone\riser.wav", r"E:\Gone\pad.wav"
        )

        report = check_project(project)

        self.assertEqual((report.total, report.ok, report.missing_count), (3, 1, 2))

    def test_directory_named_like_a_sample_is_not_present(self):
        (self.root / "decoy.wav").mkdir()
        project = self.write_project("song.flp", str(self.root / "decoy.wav"))

        report = check_project(project)

        self.assertEqual(report.missing_count, 1, "a directory is not a usable sample")

    def test_candidates_are_found_by_filename(self):
        # The sample moved, but the same filename exists elsewhere.
        moved = self.touch_sample("Elsewhere/bass_final_v3.wav")
        project = self.write_project("song.flp", r"D:\Old\bass_final_v3.wav")

        index, truncated = index_by_name([str(self.root)])
        report = check_project(project, index=index)

        self.assertFalse(truncated)
        self.assertTrue(report.searched)
        self.assertEqual(report.missing[0].candidates, (str(moved),))

    def test_no_candidates_when_index_is_absent(self):
        project = self.write_project("song.flp", r"D:\Old\missing.wav")

        report = check_project(project)

        self.assertFalse(report.searched)
        self.assertEqual(report.missing[0].candidates, ())

    def test_index_ignores_non_audio_files(self):
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        index, _ = index_by_name([str(self.root)])
        self.assertEqual(index, {})

    def test_index_reports_truncation(self):
        self.touch_sample("Samples/a.wav")
        self.touch_sample("Samples/b.wav")
        _, truncated = index_by_name([str(self.root)], max_files=1)
        self.assertTrue(truncated)

    def test_to_dict_is_json_serialisable(self):
        project = self.write_project("song.flp", r"D:\Gone\x.wav")
        payload = check_project(project).to_dict()
        json.dumps(payload)
        self.assertEqual(payload["missing_count"], 1)
        self.assertEqual(payload["missing"][0]["filename"], "x.wav")


class MacroTest(WorkspaceTestCase):
    """References that use an FL Studio macro instead of a drive letter."""

    MACRO = "%FLStudioFactoryData%"
    REF = MACRO + r"\drums\pack\2Hihat.wav"

    def test_unresolved_without_a_mapping(self):
        project = self.write_project("song.flp", self.REF)

        report = check_project(project)

        self.assertEqual(report.total, 1)
        self.assertEqual(report.missing_count, 0, "an unchecked path is not a missing file")
        self.assertEqual(report.unresolved_count, 1)

    def test_resolved_when_mapped_and_present(self):
        factory = self.root / "FactoryData"
        sample = factory / "drums" / "pack" / "2Hihat.wav"
        sample.parent.mkdir(parents=True)
        sample.write_bytes(b"RIFF....WAVEfmt ")
        project = self.write_project("song.flp", self.REF)

        report = check_project(project, macros={self.MACRO: str(factory)})

        self.assertEqual(report.ok, 1)
        self.assertEqual(report.unresolved_count, 0)

    def test_missing_when_mapped_but_absent(self):
        factory = self.root / "FactoryData"
        factory.mkdir()
        project = self.write_project("song.flp", self.REF)

        report = check_project(project, macros={self.MACRO: str(factory)})

        self.assertEqual(report.missing_count, 1)
        self.assertIsNotNone(report.missing[0].resolved)
        self.assertIn("2Hihat.wav", report.missing[0].resolved)

    def test_macro_name_matching_is_case_insensitive(self):
        factory = self.root / "FactoryData"
        sample = factory / "drums" / "pack" / "2Hihat.wav"
        sample.parent.mkdir(parents=True)
        sample.write_bytes(b"RIFF")
        project = self.write_project("song.flp", self.REF)

        report = check_project(project, macros={self.MACRO.lower(): str(factory)})

        self.assertEqual(report.ok, 1)

    def test_to_dict_includes_unresolved(self):
        project = self.write_project("song.flp", self.REF)
        payload = check_project(project).to_dict()
        json.dumps(payload)
        self.assertEqual(payload["unresolved_count"], 1)
        self.assertEqual(payload["unresolved"][0]["filename"], "2Hihat.wav")


class CliTest(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.write_project("song.flp", r"D:\Gone\lost.wav")

    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_check_json_reports_missing(self):
        code, out = self.run_cli(["check", str(self.project), "--json", "--no-search"])
        payload = json.loads(out)
        self.assertEqual(code, EXIT_FOUND)
        self.assertEqual(payload["missing_count"], 1)

    def test_check_returns_ok_when_nothing_missing(self):
        sample = self.touch_sample("here.wav")
        clean = self.write_project("clean.flp", str(sample))

        code, out = self.run_cli(["check", str(clean), "--no-search"])

        self.assertEqual(code, EXIT_OK)
        self.assertIn("0 missing", out)

    def test_check_human_output_names_the_file(self):
        _, out = self.run_cli(["check", str(self.project), "--no-search"])
        self.assertIn("lost.wav", out)
        self.assertIn("referenced as", out)

    def test_check_searches_for_candidates(self):
        self.touch_sample("Found/lost.wav")
        _, out = self.run_cli(
            ["check", str(self.project), "--search-root", str(self.root)]
        )
        self.assertIn("found:", out)

    def test_find_locates_projects_using_a_sample(self):
        code, out = self.run_cli(["find", str(self.root), "--sample", "lost"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("song.flp", out)

    def test_find_reports_no_match(self):
        code, _ = self.run_cli(["find", str(self.root), "--sample", "nothere"])
        self.assertEqual(code, EXIT_FOUND)

    def test_missing_file_is_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(["check", str(self.root / "nope.flp")])
        self.assertEqual(code, EXIT_ERROR)

    def test_macro_reference_is_not_a_failure(self):
        project = self.write_project("macro.flp", r"%FLStudioFactoryData%\drums\2Hihat.wav")

        code, out = self.run_cli(["check", str(project), "--no-search"])

        self.assertEqual(code, EXIT_OK, "an unchecked path must not fail the run")
        self.assertIn("unresolved", out)

    def test_macro_flag_resolves_references(self):
        factory = self.root / "FactoryData"
        sample = factory / "drums" / "2Hihat.wav"
        sample.parent.mkdir(parents=True)
        sample.write_bytes(b"RIFF")
        project = self.write_project(
            "macro.flp", r"%FLStudioFactoryData%\drums\2Hihat.wav"
        )

        code, out = self.run_cli(
            [
                "check",
                str(project),
                "--no-search",
                "--macro",
                f"%FLStudioFactoryData%={factory}",
            ]
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("1 ok", out)
        self.assertNotIn("unresolved", out)


if __name__ == "__main__":
    unittest.main()
