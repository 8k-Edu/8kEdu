"""The bug these cover: a widget generated from the video (touch-the-screen or the ask box)
lived only in React state, so navigating away lost it. Nothing persisted the spec and nothing
could list it back per video.

The cache-hit cases are the load-bearing ones — both handlers return early on an
inference_cache hit, so a persist call bolted onto the success path alone never runs for a
box that was already generated once."""
import base64
import contextlib
import json
import os
import tempfile
import time
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
        self.assertTrue(listed[0]["id"])
        self.assertNotIn("owner", listed[0])  # public read, so no ownership metadata
        self.assertEqual(self._saved()[0]["owner"], "auth-alice")

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

    def test_an_identical_spec_from_a_guest_leaves_the_team_widget_alone(self):
        """Ids are content-addressed, so a guest replaying a cached team widget produces the
        same id — it must not carry ownership across with it."""
        self._region(owner="auth-alice")
        original = self._saved()[0]

        with patch.object(widget_store, "DATA", self.root):
            returned = widget_store.save("vid", {
                "has_concept": True, "widget": "softmax", "title": "Softmax",
                "explanation": "Normalize logits", "params": {"logits": [1, 2]},
                "time": 300.0, "frame": "f_000300.jpg", "user_made": True,
            }, owner=widget_store.GUEST_OWNER)

        self.assertEqual([(c["id"], c["owner"]) for c in self._saved()],
                         [(original["id"], "auth-alice")])
        self.assertEqual(returned["owner"], "auth-alice")

    def test_a_guest_cannot_replace_a_team_members_widget(self):
        self._region(owner="auth-alice")
        victim = self._saved()[0]

        with patch.object(widget_store, "DATA", self.root):
            widget_store.save("vid", {"widget": "softmax", "title": "guest edit",
                                      "params": {"logits": [7, 8]}, "time": 300},
                              owner=widget_store.GUEST_OWNER, replaces=victim["id"])

        self.assertIn(victim["id"], {c["id"] for c in self._saved()})


class FlagEndpointTests(SavedWidgetTestCase):
    @contextlib.contextmanager
    def _as(self, email, team=""):
        """Patch below the authorization decision, so the allowlist itself is under test."""
        identity = {"handle": f"auth-{email}", "email": email, "expires_at": 1e12}
        with patch.object(flags, "DATA", self.root), \
                patch.dict(os.environ, {"KEDU_TEAM": team}), \
                patch.object(serve, "_identify", return_value=identity):
            yield

    def test_a_guest_cannot_change_the_flags(self):
        with patch.object(flags, "DATA", self.root), \
                patch.object(serve, "_identify",
                             side_effect=serve.CloudUnavailable("no session")):
            response = serve.set_flags(serve.FlagUpdate(guest_saves=False), authorization=None)

        self.assertEqual(response.status_code, 403)
        with patch.object(flags, "DATA", self.root):
            self.assertTrue(flags.load()["guest_saves"])

    def test_a_signed_in_stranger_is_not_a_team_member(self):
        with self._as("stranger@example.com", team="alice@perspectivity.co"):
            response = serve.set_flags(serve.FlagUpdate(guest_saves=False),
                                       authorization="Bearer t")

        self.assertEqual(response.status_code, 403)
        with patch.object(flags, "DATA", self.root):
            self.assertTrue(flags.load()["guest_saves"])

    def test_an_unset_allowlist_means_nobody_is_a_team_member(self):
        with self._as("alice@perspectivity.co", team=""):
            response = serve.set_flags(serve.FlagUpdate(guest_saves=False),
                                       authorization="Bearer t")

        self.assertEqual(response.status_code, 403)

    def test_a_team_member_can_change_the_flags(self):
        with self._as("Alice@Perspectivity.co", team=" alice@perspectivity.co , bob@x.io "):
            updated = serve.set_flags(serve.FlagUpdate(guest_saves=False),
                                      authorization="Bearer t")

        self.assertEqual(updated["guest_saves"], False)
        with patch.object(flags, "DATA", self.root):
            self.assertFalse(flags.load()["guest_saves"])

    def test_a_domain_entry_admits_the_whole_team_without_listing_it(self):
        with self._as("azehady@perspectivity.co", team="@perspectivity.co"):
            updated = serve.set_flags(serve.FlagUpdate(guest_saves=False),
                                      authorization="Bearer t")
        self.assertEqual(updated["guest_saves"], False)

    def test_a_domain_entry_does_not_admit_a_lookalike_address(self):
        for impostor in ("attacker@notperspectivity.co", "perspectivity.co@evil.com",
                         "someone@sub.perspectivity.co.evil.com"):
            with self._as(impostor, team="@perspectivity.co"):
                response = serve.set_flags(serve.FlagUpdate(guest_saves=False),
                                           authorization="Bearer t")
            self.assertEqual(response.status_code, 403, impostor)

    def test_a_damaged_flag_file_fails_closed_rather_than_re_enabling_guest_saves(self):
        (self.root / "flags.json").write_text("{broken")

        with patch.object(flags, "DATA", self.root):
            self.assertFalse(flags.load()["guest_saves"])

    def test_a_missing_flag_file_is_first_run_not_corruption(self):
        with patch.object(flags, "DATA", self.root):
            self.assertEqual(flags.load(), flags.DEFAULTS)


class TokenCacheTests(unittest.TestCase):
    def setUp(self):
        serve._auth_cache.clear()
        self.addCleanup(serve._auth_cache.clear)

    def _reply(self, body):
        return contextlib.nullcontext(type("R", (), {"read": staticmethod(lambda: body)})())

    def test_a_revoked_token_stops_working_once_its_cache_entry_lapses(self):
        env = {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "k"}
        ok = self._reply(b'{"id":"u1","email":"alice@perspectivity.co"}')

        with patch.dict(os.environ, env), patch.object(serve, "urlopen", return_value=ok):
            self.assertEqual(serve._identify("Bearer t")["handle"], "auth-u1")

        serve._auth_cache["t"]["expires_at"] = 0  # the JWT's own exp, now behind us
        with patch.dict(os.environ, env), \
                patch.object(serve, "urlopen", side_effect=OSError("401 revoked")):
            with self.assertRaises(serve.CloudUnavailable):
                serve._identify("Bearer t")

        self.assertNotIn("t", serve._auth_cache)

    def test_the_cache_never_outlives_the_tokens_own_expiry(self):
        claims = base64.urlsafe_b64encode(b'{"exp":1}').decode().rstrip("=")
        self.assertEqual(serve._token_expiry(f"h.{claims}.sig"), 1)
        self.assertLessEqual(serve._token_expiry("not-a-jwt"),
                             time.time() + serve._AUTH_TTL_MAX)


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

    def test_notebooks_are_not_shared_by_default_because_they_execute_on_open(self):
        notebook = ('{"has_concept":true,"widget":"notebook","title":"NB",'
                    '"params":{"cells":["import js; js.localStorage.clear()"]}}')
        result = self._region(backend=FakeBackend(notebook))

        self.assertEqual(result["widget"], "notebook")
        self.assertFalse(result["saved"])
        self.assertEqual(self._saved(), [])

    def test_notebook_sharing_is_available_as_an_explicit_opt_in(self):
        notebook = ('{"has_concept":true,"widget":"notebook","title":"NB",'
                    '"params":{"cells":["print(1)"]}}')
        with patch.dict(os.environ, {"KEDU_SAVE_NOTEBOOKS": "1"}):
            result = self._region(backend=FakeBackend(notebook))

        self.assertTrue(result["saved"])

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

    def test_a_disk_failure_still_returns_the_generated_widget(self):
        """A full disk loses the save, not the generation the learner just paid for."""
        with patch.object(Path, "write_text", side_effect=OSError("No space left")):
            result = self._region()

        self.assertEqual(result["widget"], "softmax")
        self.assertFalse(result["saved"])
        self.assertIn("couldn't be saved", result["save_error"])

    def test_every_write_failure_is_reported_as_the_store_being_unavailable(self):
        spec = {"widget": "softmax", "title": "t", "params": {"logits": [1, 2]}, "time": 1}
        for boom in (OSError("no space"), PermissionError("read-only"), OSError("replace")):
            with patch.object(widget_store, "DATA", self.root), \
                    patch.object(Path, "write_text", side_effect=boom), \
                    self.assertRaises(widget_store.StoreUnavailable):
                widget_store.save("vid", dict(spec), owner="auth-alice")

    def test_undecodable_bytes_read_as_corruption_not_a_crash(self):
        self._stored_file().write_bytes(b"\xff\xfe not utf-8")

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
