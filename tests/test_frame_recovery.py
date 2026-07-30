"""A live ask on a moment whose keyframe exists on no disk and in no bucket used to dead-end.
These cover pulling that one frame from YouTube, publishing it so it never happens twice, and
the reconcile that stops a reprocess from throwing recovered frames away."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ingest


class FetchOneFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.frames = Path(self.tmp.name) / "frames"

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _writing_run(calls=None):
        def fake_run(cmd, **kwargs):
            if calls is not None:
                calls.append(cmd)
            if cmd[0] == "ffmpeg":
                Path(cmd[-1]).write_bytes(b"\xff\xd8jpeg")
            else:
                Path(cmd[cmd.index("-o") + 1].replace("%(ext)s", "mp4")).write_bytes(b"clip")
            return 0
        return fake_run

    def test_uses_the_library_download_selector_and_extract_recipe(self):
        calls = []
        with patch.object(ingest, "run", self._writing_run(calls)):
            out = ingest.fetch_one_frame("vid", 210.0, "f_000210.jpg", self.frames)

        self.assertEqual(out, self.frames / "f_000210.jpg")
        self.assertEqual(out.read_bytes(), b"\xff\xd8jpeg")
        ytdlp, ffmpeg = calls
        # must match ingest.download(): the library is 480p upscaled to 720, so a 720p source
        # would hand the VLM a sharper frame than any of its neighbours
        self.assertIn("bv*[height<=480]+ba/b[height<=480]/b", ytdlp)
        self.assertIn("*208.0-215.0", " ".join(ytdlp))
        self.assertIn("--force-keyframes-at-cuts", ytdlp)
        self.assertIn("scale=-2:720", ffmpeg)
        self.assertIn("-q:v", ffmpeg)
        self.assertEqual(ffmpeg[ffmpeg.index("-ss") + 1], "2.0")   # the lead-in, not t_s

    def test_uses_the_manifest_filename_not_the_timestamp(self):
        # ingest writes time=213.0 next to f_000212.jpg for the same frame.
        with patch.object(ingest, "run", self._writing_run()):
            out = ingest.fetch_one_frame("vid", 213.0, "f_000212.jpg", self.frames)
        self.assertEqual(out.name, "f_000212.jpg")

    def test_early_frame_clamps_the_section_start_at_zero(self):
        calls = []
        with patch.object(ingest, "run", self._writing_run(calls)):
            ingest.fetch_one_frame("vid", 1.0, "f_000001.jpg", self.frames)
        self.assertIn("*0.0-6.0", " ".join(calls[0]))
        self.assertEqual(calls[1][calls[1].index("-ss") + 1], "1.0")

    def test_download_failure_returns_none(self):
        def boom(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd)

        with patch.object(ingest, "run", boom):
            self.assertIsNone(ingest.fetch_one_frame("vid", 210.0, "f_000210.jpg", self.frames))

    def test_no_frame_written_returns_none(self):
        with patch.object(ingest, "run", lambda cmd, **kw: 0):
            self.assertIsNone(ingest.fetch_one_frame("vid", 210.0, "f_000210.jpg", self.frames))


if __name__ == "__main__":
    unittest.main()
