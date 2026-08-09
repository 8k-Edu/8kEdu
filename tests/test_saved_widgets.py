"""The bug these cover: a widget generated from the video (touch-the-screen or the ask box)
lived only in React state, so navigating away lost it. Nothing persisted the spec and nothing
could list it back per video.

The cache-hit cases are the load-bearing ones — both handlers return early on an
inference_cache hit, so a persist call bolted onto the success path alone never runs for a
box that was already generated once."""
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import serve
from agent import flags, widget_store

SPEC = ('{"has_concept":true,"widget":"softmax","title":"Softmax",'
        '"explanation":"Normalize logits","params":{"logits":[1,2]}}')
ANSWER_ONLY = '{"has_concept":true,"explanation":"just prose, no widget"}'


class FakeBackend:
    def __init__(self, raw=SPEC):
        self.raw = raw
        self.calls = 0

    def ask(self, _frame, _context, **_kwargs):
        self.calls += 1
        return self.raw


class SavedWidgetTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "vid").mkdir()
        self.frame = self.root / "f_000300.jpg"
        Image.new("RGB", (640, 360), "white").save(self.frame)
        self.events = []
        self.addCleanup(self.tmp.cleanup)

    @contextlib.contextmanager
    def _serving(self, backend=None, cached=None, owner="auth-alice"):
        backend = backend or FakeBackend()
        with contextlib.ExitStack() as stack:
            for p in (
                patch.object(serve, "backend", backend),
                patch.object(serve, "_db", None),
                patch.object(serve, "DATA", self.root),
                patch.object(widget_store, "DATA", self.root),
                patch.object(serve, "nearest_frame",
                             return_value={"file": "f_000300.jpg", "time": 300.0}),
                patch.object(serve, "_frame_path", return_value=self.frame),
                patch.object(serve, "_genre_for", return_value="general"),
                patch.object(serve, "_cache_get_first", return_value=cached),
                patch.object(serve, "_cache_put"),
                patch.object(serve, "_fire_event", self.events.append),
                patch.object(serve, "_owner_for", return_value=owner),
            ):
                stack.enter_context(p)
            yield backend

    def _region(self, owner="auth-alice", cached=None, backend=None, **kwargs):
        with self._serving(backend=backend, cached=cached, owner=owner):
            req = serve.RegionAsk(text="logits", time=300, x=0.1, y=0.1, w=0.3, h=0.3,
                                  video="vid", **kwargs)
            return serve.make_region_widget(req, authorization="Bearer t")

    def _widget(self, owner="auth-alice", cached=None, backend=None, **kwargs):
        with self._serving(backend=backend, cached=cached, owner=owner):
            req = serve.Ask(text="logits", time=300, video="vid", **kwargs)
            return serve.make_widget(req, authorization="Bearer t")

    def _saved(self, video="vid"):
        with patch.object(widget_store, "DATA", self.root):
            return widget_store.load(video)

    def _stored_file(self, video="vid"):
        return self.root / video / "user_concepts.json"


class RegionPersistenceTests(SavedWidgetTestCase):
    def test_a_region_widget_is_readable_back_from_the_store(self):
        result = self._region()

        self.assertEqual(result["widget"], "softmax")
        self.assertTrue(result["saved"])
        with patch.object(widget_store, "DATA", self.root):
            listed = serve.saved_widgets(video="vid")
        self.assertEqual([c["widget"] for c in listed], ["softmax"])
        self.assertEqual(listed[0]["time"], 300)
        self.assertEqual(listed[0]["owner"], "auth-alice")
        self.assertTrue(listed[0]["id"])

    def test_an_ask_box_widget_is_persisted_too(self):
        result = self._widget()

        self.assertTrue(result["saved"])
        self.assertEqual([c["widget"] for c in self._saved()], ["softmax"])

    def test_a_cache_hit_still_persists(self):
        cached = {"has_concept": True, "widget": "softmax", "title": "Softmax",
                  "params": {"logits": [1, 2]}, "time": 300, "frame": "f_000300.jpg"}
        backend = FakeBackend()

        result = self._region(cached=cached, backend=backend)

        self.assertTrue(result["cached"])
        self.assertEqual(backend.calls, 0)
        self.assertEqual([c["widget"] for c in self._saved()], ["softmax"])

    def test_the_same_region_twice_stores_one_entry(self):
        self._region()
        self._region()

        self.assertEqual(len(self._saved()), 1)

    def test_an_answer_fallback_is_never_persisted(self):
        result = self._region(backend=FakeBackend(ANSWER_ONLY))

        self.assertIn("answer", result)
        self.assertEqual(self._saved(), [])


class GuestTests(SavedWidgetTestCase):
    def test_a_signed_out_visitor_saves_under_the_shared_guest_owner(self):
        result = self._region(owner=widget_store.GUEST_OWNER)

        self.assertTrue(result["saved"])
        self.assertEqual([c["owner"] for c in self._saved()], [widget_store.GUEST_OWNER])

    def test_no_authorization_header_resolves_to_the_guest_owner(self):
        self.assertEqual(serve._owner_for(None), widget_store.GUEST_OWNER)
        self.assertEqual(serve._owner_for("not a bearer token"), widget_store.GUEST_OWNER)
        self.assertIsNone(serve._team_member(None))

    def test_the_team_flag_turns_guest_saving_off_without_touching_team_saving(self):
        with patch.object(flags, "DATA", self.root):
            flags.update({"guest_saves": False})

            guest = self._region(owner=widget_store.GUEST_OWNER)
            self.assertFalse(guest["saved"])
            self.assertIn("sign in", guest["save_error"])
            self.assertEqual(self._saved(), [])

            team = self._region(owner="auth-alice", cached={
                "has_concept": True, "widget": "matrix_mul", "title": "M",
                "params": {"a": [[1]], "b": [[2]]}, "time": 5})
            self.assertTrue(team["saved"])

    def test_a_guest_cannot_replace_a_team_members_widget(self):
        self._region(owner="auth-alice")
        victim = self._saved()[0]

        with patch.object(widget_store, "DATA", self.root):
            widget_store.save("vid", {"widget": "softmax", "title": "guest edit",
                                      "params": {"logits": [7, 8]}, "time": 300},
                              owner=widget_store.GUEST_OWNER, replaces=victim["id"])

        self.assertIn(victim["id"], {c["id"] for c in self._saved()})


class FlagEndpointTests(SavedWidgetTestCase):
    def test_a_guest_cannot_change_the_flags(self):
        with patch.object(flags, "DATA", self.root), \
                patch.object(serve, "_owner_for", return_value=widget_store.GUEST_OWNER):
            response = serve.set_flags(serve.FlagUpdate(guest_saves=False), authorization=None)

        self.assertEqual(response.status_code, 403)
        with patch.object(flags, "DATA", self.root):
            self.assertTrue(flags.load()["guest_saves"])

    def test_a_team_member_can_change_the_flags(self):
        with patch.object(flags, "DATA", self.root), \
                patch.object(serve, "_owner_for", return_value="auth-alice"):
            updated = serve.set_flags(serve.FlagUpdate(guest_saves=False),
                                      authorization="Bearer t")

        self.assertEqual(updated["guest_saves"], False)
        with patch.object(flags, "DATA", self.root):
            self.assertFalse(flags.load()["guest_saves"])

    def test_a_damaged_flag_file_falls_back_to_defaults_instead_of_raising(self):
        (self.root / "flags.json").write_text("{broken")

        with patch.object(flags, "DATA", self.root):
            self.assertEqual(flags.load(), flags.DEFAULTS)


class OwnershipTests(SavedWidgetTestCase):
    def test_one_owner_cannot_replace_another_owners_widget(self):
        self._region(owner="auth-alice")
        victim = self._saved()[0]

        with patch.object(widget_store, "DATA", self.root):
            widget_store.save("vid", {"widget": "spreadsheet", "title": "Bob's",
                                      "params": {"cells": [["a"]]}, "time": 10},
                              owner="auth-bob", replaces=victim["id"])

        ids = {c["id"] for c in self._saved()}
        self.assertIn(victim["id"], ids)
        self.assertEqual(len(ids), 2)

    def test_an_owner_can_replace_their_own_widget(self):
        self._region()
        first = self._saved()[0]

        with patch.object(widget_store, "DATA", self.root):
            widget_store.save("vid", {"widget": "softmax", "title": "Refined",
                                      "params": {"logits": [3, 4]}, "time": 300},
                              owner="auth-alice", replaces=first["id"])

        saved = self._saved()
        self.assertEqual([c["title"] for c in saved], ["Refined"])


class CapTests(SavedWidgetTestCase):
    def _fill(self, n, owner):
        with patch.object(widget_store, "DATA", self.root):
            for i in range(n):
                widget_store.save("vid", {"widget": "softmax", "title": f"w{i}",
                                          "params": {"logits": [i, i + 1]}, "time": i},
                                  owner=owner)

    def test_the_per_owner_cap_rejects_rather_than_evicting(self):
        with patch.object(widget_store, "MAX_PER_OWNER", 2):
            self._fill(2, "auth-alice")
            with patch.object(widget_store, "DATA", self.root), \
                    self.assertRaises(widget_store.SaveRejected):
                widget_store.save("vid", {"widget": "softmax", "title": "over",
                                          "params": {"logits": [9, 9]}, "time": 99},
                                  owner="auth-alice")

        self.assertEqual(len(self._saved()), 2)

    def test_the_per_video_cap_counts_every_owner(self):
        with patch.object(widget_store, "MAX_PER_VIDEO", 2):
            self._fill(2, "auth-alice")
            with patch.object(widget_store, "DATA", self.root), \
                    self.assertRaises(widget_store.SaveRejected):
                widget_store.save("vid", {"widget": "softmax", "title": "over",
                                          "params": {"logits": [9, 9]}, "time": 99},
                                  owner="auth-bob")

        self.assertEqual(len(self._saved()), 2)


class PathAndSwitchTests(SavedWidgetTestCase):
    def test_a_traversing_video_id_is_refused(self):
        for bad in ("../../etc", "", "a/b", "."):
            with patch.object(widget_store, "DATA", self.root), \
                    self.assertRaises(widget_store.StoreUnavailable):
                widget_store.load(bad)

    def test_the_operator_kill_switch_restores_the_old_behaviour(self):
        with patch.dict(os.environ, {"KEDU_SAVE_WIDGETS": "0"}):
            result = self._region()

        self.assertEqual(result["widget"], "softmax")
        self.assertEqual(self._saved(), [])

    def test_notebooks_can_be_excluded_without_disabling_the_feature(self):
        notebook = ('{"has_concept":true,"widget":"notebook","title":"NB",'
                    '"params":{"cells":["print(1)"]}}')
        with patch.dict(os.environ, {"KEDU_SAVE_NOTEBOOKS": "0"}):
            result = self._region(backend=FakeBackend(notebook))

        self.assertEqual(result["widget"], "notebook")
        self.assertFalse(result["saved"])
        self.assertEqual(self._saved(), [])

    def test_a_missing_video_directory_is_created_on_save(self):
        with patch.object(widget_store, "DATA", self.root):
            widget_store.save("fresh", {"widget": "softmax", "title": "t",
                                        "params": {"logits": [1, 2]}, "time": 1},
                              owner="auth-alice")
            self.assertEqual(len(widget_store.load("fresh")), 1)


class CorruptionTests(SavedWidgetTestCase):
    def test_a_corrupt_store_is_never_silently_overwritten(self):
        path = self._stored_file()
        path.write_text("{not json at all")

        with patch.object(widget_store, "DATA", self.root):
            with self.assertRaises(widget_store.StoreUnavailable):
                widget_store.load("vid")
            with self.assertRaises(widget_store.StoreUnavailable):
                widget_store.save("vid", {"widget": "softmax", "title": "t",
                                          "params": {"logits": [1, 2]}, "time": 1},
                                  owner="auth-alice")

        quarantined = self.root / "vid" / "user_concepts.corrupt.json"
        self.assertEqual(quarantined.read_text(), "{not json at all")
        self.assertFalse(path.exists())

    def test_a_json_object_root_counts_as_corrupt(self):
        self._stored_file().write_text(json.dumps({"widget": "softmax"}))

        with patch.object(widget_store, "DATA", self.root), \
                self.assertRaises(widget_store.StoreUnavailable):
            widget_store.load("vid")

    def test_a_read_failure_surfaces_as_an_error_response_not_an_empty_list(self):
        self._stored_file().write_text("{nope")

        with patch.object(widget_store, "DATA", self.root):
            response = serve.saved_widgets(video="vid")

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
