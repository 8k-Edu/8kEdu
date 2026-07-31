"""The bug these cover: keyframes are gitignored, so /api/widget on a video whose jpgs
live on another machine answered "aren't on disk" with no way to recover. Nothing tested
that branch, the /api/region exists() gate, or any remote-frame path."""
import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import serve

SPEC = ('{"has_concept":true,"widget":"softmax","title":"Softmax",'
        '"explanation":"Normalize logits","params":{"logits":[1,2]}}')


class FakeBackend:
    def __init__(self):
        self.asked = []

    def ask(self, frame, _context, **_kwargs):
        self.asked.append(Path(frame))
        return SPEC


class MissingBackend(FakeBackend):
    def ask(self, frame, _context, **_kwargs):
        Path(frame).read_bytes()  # what _jpeg_bytes does, and what raises
        return SPEC


def _patches(backend, resolved):
    return (
        patch.object(serve, "backend", backend),
        patch.object(serve, "_db", None),
        patch.object(serve, "nearest_frame", return_value={"file": "f_000300.jpg", "time": 300.0}),
        patch.object(serve, "resolve_frame", return_value=resolved),
        patch.object(serve, "_genre_for", return_value="general"),
        patch.object(serve, "_cache_get_first", return_value=None),
        patch.object(serve, "_cache_put"),
    )


class WidgetFrameFallbackTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _call(self, backend, resolved):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(serve, "_fire_event", self.events.append))
            for p in _patches(backend, resolved):
                stack.enter_context(p)
            return serve.make_widget(serve.Ask(text="logits", time=300, video="vid"))

    def test_both_missing_keeps_the_existing_answer_and_records_the_miss(self):
        absent = Path(self.tmp.name) / "f_000300.jpg"
        result = self._call(MissingBackend(), (absent, "miss", 42))

        self.assertIn("keyframes aren't on disk", result["error"])
        ev = self.events[-1]
        self.assertEqual(ev["frame_source"], "miss")
        self.assertEqual(ev["t_frame_fetch_ms"], 42)
        self.assertEqual(ev["error"], "frames missing on disk")
        self.assertFalse(ev["cache_hit"])

    def test_a_remote_frame_produces_a_real_widget(self):
        fetched = Path(self.tmp.name) / "f_000300.jpg"
        fetched.write_bytes(b"\xff\xd8jpeg")
        backend = FakeBackend()
        result = self._call(backend, (fetched, "remote", 87))

        self.assertEqual(result["widget"], "softmax")
        self.assertEqual(backend.asked, [fetched])
        ev = self.events[-1]
        self.assertEqual(ev["frame_source"], "remote")
        self.assertEqual(ev["t_frame_fetch_ms"], 87)

    def test_storage_disabled_still_degrades_rather_than_raising(self):
        absent = Path(self.tmp.name) / "f_000300.jpg"
        result = self._call(MissingBackend(), (absent, "off", 0))

        self.assertIn("keyframes aren't on disk", result["error"])
        self.assertEqual(self.events[-1]["frame_source"], "off")


class ManifestFallbackTests(unittest.TestCase):
    """frames.json is only git-tracked for some videos; a bare read_text() here used to 500
    before any frame handling ran."""

    def setUp(self):
        serve._frames_cache.pop("vid", None)

    def tearDown(self):
        serve._frames_cache.pop("vid", None)

    def test_manifest_comes_from_the_frames_table_when_the_file_is_absent(self):
        class DB:
            @staticmethod
            def frames_manifest(_video):
                return [{"time": 213.0, "file": "f_000212.jpg"}, {"time": 300.0, "file": "f_000300.jpg"}]

        with patch.object(serve, "DATA", Path("/nonexistent")), patch.object(serve, "_db", DB()):
            fr = serve.nearest_frame("vid", 299)

        # Not f_000299.jpg: the stored filename is the only truth about a frame's name.
        self.assertEqual(fr, {"time": 300.0, "file": "f_000300.jpg"})

    def test_no_manifest_anywhere_is_an_error_dict_not_a_500(self):
        class DB:
            @staticmethod
            def frames_manifest(_video):
                return []

        events = []
        with patch.object(serve, "DATA", Path("/nonexistent")), \
                patch.object(serve, "_db", DB()), \
                patch.object(serve, "_fire_event", events.append):
            self.assertIsNone(serve.nearest_frame("vid", 10))
            result = serve.make_widget(serve.Ask(text="x", time=10, video="vid"))

        self.assertIn("hasn't been processed yet", result["error"])
        # The no-manifest branch should still be visible in widget_events, like every other
        # error path in these handlers.
        self.assertEqual(events[-1]["error"], "no manifest")
        self.assertEqual(events[-1]["kind"], "widget")

    def test_a_database_failure_is_not_cached_as_an_empty_manifest(self):
        class DB:
            @staticmethod
            def frames_manifest(_video):
                raise RuntimeError("pooler down")

        with patch.object(serve, "DATA", Path("/nonexistent")), patch.object(serve, "_db", DB()):
            self.assertEqual(serve.frames_for("vid"), [])
        self.assertNotIn("vid", serve._frames_cache)


if __name__ == "__main__":
    unittest.main()
