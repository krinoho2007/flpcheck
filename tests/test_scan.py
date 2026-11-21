"""Tests for locating sample references in .flp bytes."""

from __future__ import annotations

import unittest

from flpcheck import FLP_MAGIC, looks_like_flp, scan_bytes


def make_project(*paths: str) -> bytes:
    """Build bytes shaped like an .flp: header chunk, UTF-16LE strings, data chunk."""
    body = b"".join(path.encode("utf-16-le") for path in paths)
    return FLP_MAGIC + b"\x00" * 8 + body + b"FLdt"


class ScanBytesTest(unittest.TestCase):
    def test_finds_windows_path(self):
        raw = make_project(r"D:\Samples\Bass\bass_final_v3.wav")
        refs = scan_bytes(raw)
        self.assertEqual([r.path for r in refs], [r"D:\Samples\Bass\bass_final_v3.wav"])

    def test_finds_forward_slash_windows_path(self):
        refs = scan_bytes(make_project("E:/Samples/kick.wav"))
        self.assertEqual(len(refs), 1)

    def test_finds_posix_path(self):
        refs = scan_bytes(make_project("/Users/me/Music/loop.aiff"))
        self.assertEqual([r.path for r in refs], ["/Users/me/Music/loop.aiff"])

    def test_finds_non_ascii_path(self):
        # Chinese folder and file names are common among the target users.
        path = "D:\\音乐\\采样\\贝斯.wav"
        refs = scan_bytes(make_project(path))
        self.assertEqual([r.path for r in refs], [path])

    def test_deduplicates_exact_repeats(self):
        path = r"D:\Samples\kick.wav"
        refs = scan_bytes(make_project(path, path, path))
        self.assertEqual(len(refs), 1)

    def test_deduplicates_case_and_separator_variants(self):
        refs = scan_bytes(make_project(r"D:\Samples\Kick.WAV", "d:/samples/kick.wav"))
        self.assertEqual(len(refs), 1, "Windows paths are case-insensitive")

    def test_ignores_non_audio_extensions(self):
        refs = scan_bytes(make_project(r"D:\Docs\notes.txt", r"D:\Images\cover.png"))
        self.assertEqual(refs, [])

    def test_wave_extension_is_not_truncated(self):
        refs = scan_bytes(make_project(r"D:\Samples\pad.wave"))
        self.assertEqual([r.filename for r in refs], ["pad.wave"])

    def test_adjacent_strings_are_both_found(self):
        # FL Studio stores strings back to back with no separator, so a path
        # can be followed immediately by the next one.
        refs = scan_bytes(make_project(r"D:\Samples\zzz.wav", r"D:\Samples\aaa.wav"))
        self.assertEqual([r.filename for r in refs], ["aaa.wav", "zzz.wav"])

    def test_extension_does_not_swallow_the_next_drive_letter(self):
        # "riser.wav" followed by "E:\..." must not be read as ".wave".
        refs = scan_bytes(make_project(r"D:\Gone\riser.wav", r"E:\Gone\pad.wav"))
        self.assertEqual(
            [r.path for r in refs], [r"D:\Gone\riser.wav", r"E:\Gone\pad.wav"]
        )

    def test_aif_does_not_swallow_the_next_f_drive(self):
        refs = scan_bytes(make_project(r"D:\Gone\loop.aif", r"F:\Gone\pad.wav"))
        self.assertEqual(
            [r.path for r in refs], [r"D:\Gone\loop.aif", r"F:\Gone\pad.wav"]
        )

    def test_finds_path_at_odd_byte_offset(self):
        # Event headers vary in width, so a string can start at an odd byte
        # offset. A real project had one sample path stored that way.
        body = b"\x01" + r"D:\Samples\pad.wav".encode("utf-16-le")
        raw = FLP_MAGIC + b"\x00" * 8 + body + b"FLdt"
        refs = scan_bytes(raw)
        self.assertEqual([r.path for r in refs], [r"D:\Samples\pad.wav"])

    def test_finds_paths_at_both_alignments_together(self):
        even_path = r"D:\Samples\kick.wav"
        odd_path = r"D:\Samples\snare.wav"
        body = (
            even_path.encode("utf-16-le")
            + b"\x01"
            + odd_path.encode("utf-16-le")
        )
        raw = FLP_MAGIC + b"\x00" * 8 + body + b"FLdt"
        refs = scan_bytes(raw)
        self.assertEqual([r.filename for r in refs], ["kick.wav", "snare.wav"])

    def test_finds_macro_path(self):
        # Factory-pack samples are referenced through FL Studio macros; on a
        # real project these outnumbered drive-letter paths four to one.
        path = r"%FLStudioFactoryData%\drums\pack\2Hihat.wav"
        refs = scan_bytes(make_project(path))
        self.assertEqual([r.path for r in refs], [path])
        self.assertEqual(refs[0].macro, "%FLStudioFactoryData%")

    def test_drive_path_has_no_macro(self):
        refs = scan_bytes(make_project(r"D:\Samples\kick.wav"))
        self.assertIsNone(refs[0].macro)

    def test_filename_property_handles_both_separators(self):
        for raw_path, expected in (
            (r"D:\Samples\Bass\kick.wav", "kick.wav"),
            ("/Users/me/kick.wav", "kick.wav"),
        ):
            refs = scan_bytes(make_project(raw_path))
            self.assertEqual(refs[0].filename, expected)

    def test_empty_input_is_not_an_error(self):
        self.assertEqual(scan_bytes(b""), [])


class MagicTest(unittest.TestCase):
    def test_recognises_flp_header(self):
        self.assertTrue(looks_like_flp(make_project(r"D:\a.wav")))

    def test_rejects_other_files(self):
        self.assertFalse(looks_like_flp(b"RIFF....WAVEfmt "))
        self.assertFalse(looks_like_flp(b""))


if __name__ == "__main__":
    unittest.main()
