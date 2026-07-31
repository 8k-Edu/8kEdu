import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import analyze
from agent import storage

AGENT_PKG = importlib.import_module("agent")


class FakeStorage:
    """Stands in for agent.storage. Patched onto the `agent` package, not sys.modules —
    `from agent import storage` reads the package attribute, so that's the only seam."""

    def __init__(self, data=b"\xff\xd8jpeg", on=True, boom=False):
        self.data, self.on, self.boom = data, on, boom
        self.calls = []

    def enabled(self):
        return self.on

    def fetch_frame(self, video_id, frame_file):
        self.calls.append((video_id, frame_file))
        if self.boom:
            raise RuntimeError("storage down")
        return self.data


class ObjectKeyTests(unittest.TestCase):
    def test_key_comes_from_the_filename_not_the_timestamp(self):
        # ingest.py writes time=213.0 alongside f_000212.jpg for the same frame, so a
        # t_s-derived key would 404 on roughly a third of the library.
        self.assertEqual(storage.object_key("vid", "f_000212.jpg"), "vid/f_000212.jpg")

    def test_disabled_by_env(self):
        with patch.dict(os.environ, {"KEDU_FRAME_REMOTE": "0", "SUPABASE_URL": "https://x",
                                     "SUPABASE_SECRET_KEY": "sb_secret_x"}):
            self.assertFalse(storage.enabled())

    def test_disabled_without_credentials(self):
        with patch.dict(os.environ, {"KEDU_FRAME_REMOTE": "1"}, clear=True):
            self.assertFalse(storage.enabled())


class ResolveFrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.frames = Path(self.tmp.name) / "vid" / "frames"
        self.frames.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _resolve(self, fake, name="f_000300.jpg"):
        with patch.object(AGENT_PKG, "storage", fake):
            return analyze.resolve_frame(self.frames / name, "vid")

    def test_local_hit_never_touches_storage(self):
        (self.frames / "f_000300.jpg").write_bytes(b"local")
        fake = FakeStorage(boom=True)
        path, source, ms = self._resolve(fake)
        self.assertEqual((source, ms), ("local", 0))
        self.assertEqual(path.read_bytes(), b"local")
        self.assertEqual(fake.calls, [])

    def test_remote_hit_materializes_at_the_canonical_path(self):
        fake = FakeStorage(data=b"\xff\xd8remote")
        path, source, _ms = self._resolve(fake)
        self.assertEqual(source, "remote")
        self.assertEqual(path, self.frames / "f_000300.jpg")
        self.assertEqual(path.read_bytes(), b"\xff\xd8remote")
        self.assertEqual(fake.calls, [("vid", "f_000300.jpg")])

    def test_materialize_leaves_no_temp_behind(self):
        self._resolve(FakeStorage())
        self.assertEqual([p.name for p in self.frames.iterdir()], ["f_000300.jpg"])

    def test_remote_miss_returns_the_original_path(self):
        # serve.py's FileNotFoundError branch only fires if the path is still the missing one.
        path, source, _ms = self._resolve(FakeStorage(data=b""))
        self.assertEqual(source, "miss")
        self.assertEqual(path, self.frames / "f_000300.jpg")
        self.assertFalse(path.exists())

    def test_a_raising_fetch_degrades_to_a_miss_without_propagating(self):
        path, source, _ms = self._resolve(FakeStorage(boom=True))
        self.assertEqual(source, "miss")
        self.assertFalse(path.exists())

    def test_storage_off_is_distinct_from_a_miss(self):
        fake = FakeStorage(on=False)
        _path, source, ms = self._resolve(fake)
        self.assertEqual((source, ms), ("off", 0))
        self.assertEqual(fake.calls, [])

    def test_unusable_storage_module_is_not_an_error(self):
        _path, source, _ms = self._resolve(None)
        self.assertEqual(source, "off")

    def test_read_only_directory_falls_back_to_the_cache_dir(self):
        cache = Path(self.tmp.name) / "cache"
        os.chmod(self.frames, 0o500)
        try:
            with patch.dict(os.environ, {"KEDU_FRAME_CACHE_DIR": str(cache)}):
                path, source, _ms = self._resolve(FakeStorage(data=b"\xff\xd8ro"))
        finally:
            os.chmod(self.frames, 0o700)
        self.assertEqual(source, "remote")
        self.assertEqual(path.read_bytes(), b"\xff\xd8ro")
        self.assertEqual(path, cache / "vid" / "frames" / "f_000300.jpg")


class NegativeCacheTests(unittest.TestCase):
    def setUp(self):
        storage._neg.clear()

    def tearDown(self):
        storage._neg.clear()

    def test_a_miss_is_not_fetched_twice(self):
        env = {"SUPABASE_URL": "https://x", "SUPABASE_SECRET_KEY": "sb_secret_x",
               "KEDU_FRAME_REMOTE": "1"}
        with patch.dict(os.environ, env), patch.object(storage, "_bucket") as bucket:
            bucket.return_value.download.side_effect = RuntimeError("404")
            self.assertIsNone(storage.fetch_frame("vid", "f_000300.jpg"))
            self.assertIsNone(storage.fetch_frame("vid", "f_000300.jpg"))
            self.assertEqual(bucket.return_value.download.call_count, 1)


if __name__ == "__main__":
    unittest.main()
