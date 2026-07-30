"""A live ask on a moment whose keyframe exists on no disk and in no bucket used to dead-end.
These cover pulling that one frame from YouTube, publishing it so it never happens twice, and
the reconcile that stops a reprocess from throwing recovered frames away."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent
import agent.db       # noqa: F401  — importing binds these as `agent` package attributes,
import agent.storage  # noqa: F401    which is the seam `from agent import db, storage` reads
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


class FakeStorageModule:
    def __init__(self):
        self.uploaded, self.removed = [], []

    def enabled(self):
        return True

    def ensure_bucket(self):
        pass

    def object_key(self, vid, frame_file):
        return f"{vid}/{frame_file}"

    def upload_frame(self, vid, path):
        self.uploaded.append(path.name)
        return f"{vid}/{path.name}"

    def remove_objects(self, keys):
        self.removed.extend(keys)
        return len(keys)


class FakeDbModule:
    def __init__(self, existing):
        self.existing, self.upserted, self.deleted = existing, [], []

    def load_env(self):
        pass

    def frames_rows(self, vid):
        return dict(self.existing)

    def upsert_frames(self, vid, rows, title=""):
        self.upserted.extend(rows)
        return len(rows)

    def delete_frames_at(self, vid, t_values):
        self.deleted.extend(t_values)
        return len(t_values)


class ReconcileTests(unittest.TestCase):
    """A reprocess used to drop every object and re-upload, throwing away frames that had been
    recovered on demand — and already analyzed under their filename."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        (self.out / "frames").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, *names):
        for n in names:
            (self.out / "frames" / n).write_bytes(b"\xff\xd8jpeg")

    def _run(self, frames, existing):
        storage, db = FakeStorageModule(), FakeDbModule(existing)
        with patch.object(agent, "storage", storage), patch.object(agent, "db", db):
            n = ingest.upload_frames("vid", self.out, frames)
        return n, storage, db

    def test_already_published_frames_are_skipped(self):
        self._write("f_000000.jpg", "f_000030.jpg")
        frames = [{"time": 0.0, "file": "f_000000.jpg"}, {"time": 30.4, "file": "f_000030.jpg"}]
        n, storage, db = self._run(frames, {0.0: "vid/f_000000.jpg", 30.4: "vid/f_000030.jpg"})
        self.assertEqual(storage.uploaded, [])
        self.assertEqual(storage.removed, [])
        self.assertEqual(n, 0)

    def test_new_frames_upload_and_upsert(self):
        self._write("f_000000.jpg", "f_000030.jpg")
        frames = [{"time": 0.0, "file": "f_000000.jpg"}, {"time": 30.4, "file": "f_000030.jpg"}]
        n, storage, db = self._run(frames, {0.0: "vid/f_000000.jpg"})
        self.assertEqual(storage.uploaded, ["f_000030.jpg"])
        self.assertEqual(db.upserted, [(30.4, "vid/f_000030.jpg")])
        self.assertEqual(n, 1)

    def test_renamed_frame_uploads_and_drops_the_old_object(self):
        self._write("f_000031.jpg")
        n, storage, db = self._run([{"time": 31.0, "file": "f_000031.jpg"}],
                                   {31.0: "vid/f_000030.jpg"})
        self.assertEqual(storage.uploaded, ["f_000031.jpg"])
        self.assertEqual(storage.removed, ["vid/f_000030.jpg"])

    def test_orphaned_timestamps_are_deleted_not_the_survivors(self):
        self._write("f_000000.jpg")
        n, storage, db = self._run([{"time": 0.0, "file": "f_000000.jpg"}],
                                   {0.0: "vid/f_000000.jpg", 999.0: "vid/f_000999.jpg"})
        self.assertEqual(storage.removed, ["vid/f_000999.jpg"])
        self.assertEqual(db.deleted, [999.0])
        self.assertEqual(storage.uploaded, [])

    def test_a_published_frame_absent_from_disk_stays_published(self):
        n, storage, db = self._run([{"time": 0.0, "file": "f_000000.jpg"}],
                                   {0.0: "vid/f_000000.jpg"})
        self.assertEqual(storage.removed, [])
        self.assertEqual(db.deleted, [])


if __name__ == "__main__":
    unittest.main()
