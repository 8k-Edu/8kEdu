import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from analyze import valid
from serve import SS_MAX_COLS, _clamp_spreadsheet

good = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
        "params": {"cells": [["Month", "Sales"], ["Jan", 100]]}}
assert valid(good), "well-formed spreadsheet spec should be valid"

no_cells = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
            "params": {"features": ["wrap"]}}
assert not valid(no_cells), "missing cells should be invalid"

empty = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
         "params": {"cells": []}}
assert not valid(empty), "empty cells should be invalid"

wide = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
        "params": {"cells": [[str(i) for i in range(SS_MAX_COLS + 1)], [1] * (SS_MAX_COLS + 1)],
                   "highlight": {"row": 1, "col": SS_MAX_COLS}}}
clamped = _clamp_spreadsheet(wide)
assert len(clamped["params"]["cells"][0]) == SS_MAX_COLS
assert clamped["params"]["highlight"] is None

print("OK")
