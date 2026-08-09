import contextlib
import json
import unittest
from unittest.mock import patch

import serve
from analyze import valid


NOTEBOOK = {
    "has_concept": True, "widget": "notebook", "title": "Notebook", "explanation": "e",
    "params": {"cells": ["total = 1\nprint(total)"]},
}
SHEET = {
    "has_concept": True, "widget": "spreadsheet", "title": "Sheet", "explanation": "e",
    "params": {"cells": [["Name", "Score", "Date", "Note"], ["Ada", 1, "Jan", "ok"]]},
}


class FakeBackend:
    def __init__(self, spec):
        self.raw = json.dumps(spec)
        self.contexts = []

    def ask(self, _frame, context, **_kwargs):
        self.contexts.append(context)
        return self.raw


class RefinementTests(unittest.TestCase):
    @contextlib.contextmanager
    def serving(self, backend, cached=None):
        with contextlib.ExitStack() as stack:
            for target, value in (
                ("backend", backend), ("_db", None), ("_genre_for", lambda *_: "general"),
                ("nearest_frame", lambda *_: {"file": "f.jpg", "time": 1}),
                ("_frame_path", lambda *_: "frame.jpg"), ("_cache_get_first", lambda *_: cached),
                ("_cache_put", lambda *_: None), ("_persisted", lambda spec, *_args: spec),
                ("_fire_event", lambda *_: None), ("_owner_for", lambda *_: "guest"),
            ):
                stack.enter_context(patch.object(serve, target, value))
            yield

    def refine(self, source, instruction, backend, cached=None):
        req = serve.Ask(text="nearby transcript", time=1, ask=instruction, video="video",
                        current_spec=source)
        with self.serving(backend, cached):
            return serve.make_widget(req)

    def test_notebook_validation_parses_each_cell(self):
        self.assertTrue(valid(NOTEBOOK))
        bad = {**NOTEBOOK, "params": {"cells": ["if True:\n    print(1)\n  print(2)"]}}
        self.assertFalse(valid(bad))

    def test_refinement_context_contains_authoritative_notebook_and_edit(self):
        source = {**NOTEBOOK, "params": {"cells": ["if True:\n  print('repair me')"]}}
        backend = FakeBackend(NOTEBOOK)
        result = self.refine(source, "fix the indentation", backend)
        self.assertEqual(result["widget"], "notebook")
        self.assertIn("fix the indentation", backend.contexts[0])
        self.assertIn("print('repair me')", backend.contexts[0])

    def test_refinement_context_contains_spreadsheet_source_and_edit(self):
        source = {**SHEET, "params": {"cells": [["Old name", "Score"], ["Ada", 9]]}}
        backend = FakeBackend({**SHEET, "params": {"cells": [["New name", "Score"], ["Ada", 9]]}})
        result = self.refine(source, "rename the first column", backend)
        self.assertEqual(result["params"]["cells"][0][0], "New name")
        self.assertIn("Old name", backend.contexts[0])
        self.assertIn("rename the first column", backend.contexts[0])

    def test_different_sources_produce_different_cache_keys(self):
        backend = FakeBackend(NOTEBOOK)
        with patch.object(serve, "nearest_frame", return_value={"file": "f.jpg", "time": 1}), \
             patch.object(serve, "_genre_for", return_value="general"), \
             patch.object(serve, "_cache_get_first", return_value=None), \
             patch.object(serve, "_frame_path", return_value="frame.jpg"), \
             patch.object(serve, "_cache_put"), patch.object(serve, "_persisted", side_effect=lambda s, *_: s), \
             patch.object(serve, "backend", backend), patch.object(serve, "_db", None):
            first = serve.Ask(text="t", time=1, ask="edit", video="video", current_spec=NOTEBOOK)
            second = serve.Ask(text="t", time=1, ask="edit", video="video",
                               current_spec={**NOTEBOOK, "params": {"cells": ["print(2)"]}})
            a = serve._refinement_context(first, serve._bounded_refinement_source(NOTEBOOK)[0])
            b = serve._refinement_context(second, serve._bounded_refinement_source(second.current_spec)[0])
            self.assertNotEqual(serve._prompt_hash("video", "f.jpg", a), serve._prompt_hash("video", "f.jpg", b))

    def test_source_bounding_drops_whole_cells_or_rows(self):
        cell = "x" * 7000
        source, error = serve._bounded_refinement_source({**NOTEBOOK, "params": {"cells": [cell, cell]}})
        self.assertIsNone(error)
        self.assertEqual(source["params"]["cells"], [cell])
        row = ["x" * 2500] * 3
        source, error = serve._bounded_refinement_source({**SHEET, "params": {"cells": [row, row]}})
        self.assertIsNone(error)
        self.assertEqual(source["params"]["cells"], [row])

    def test_invalid_refinement_is_not_returned_or_cached(self):
        invalid = {**NOTEBOOK, "params": {"cells": ["if True:\n print(1)\n  print(2)"]}}
        backend = FakeBackend(invalid)
        result = self.refine(NOTEBOOK, "fix it", backend)
        self.assertIn("error", result)
        self.assertIn("unchanged", result["error"])

    def test_invalid_cached_widget_is_a_miss_but_answer_card_is_served(self):
        invalid = {**NOTEBOOK, "params": {"cells": ["if True:\n print(1)\n  print(2)"]}}
        backend = FakeBackend(NOTEBOOK)
        req = serve.Ask(text="t", time=1, video="video")
        with self.serving(backend, invalid):
            result = serve.make_widget(req)
        self.assertEqual(result["widget"], "notebook")
        self.assertEqual(len(backend.contexts), 1)
        with self.serving(backend, {"answer": "cached answer"}):
            result = serve.make_widget(req)
        self.assertEqual(result["answer"], "cached answer")
        self.assertTrue(result["cached"])

    def test_spreadsheet_fifth_column_survives_and_highlight_is_normalized(self):
        added = {**SHEET, "params": {"cells": [["A", "B", "C", "D", "E"], [1, 2, 3, 4, 5]],
                                       "highlight": {"row": 1, "col": 4}}}
        result = self.refine(SHEET, "add a fifth column", FakeBackend(added))
        self.assertEqual(len(result["params"]["cells"][0]), 5)
        self.assertEqual(result["params"]["highlight"]["col"], 4)
        oversized = {**added, "params": {"cells": [[str(n) for n in range(9)]], "highlight": {"row": 0, "col": 8}}}
        clamped = serve._clamp_spreadsheet(oversized)
        self.assertEqual(len(clamped["params"]["cells"][0]), serve.SS_MAX_COLS)
        self.assertIsNone(clamped["params"]["highlight"])

    def test_prompt_version_changed(self):
        self.assertEqual(serve.PROMPT_VERSION, "v2")


if __name__ == "__main__":
    unittest.main()
