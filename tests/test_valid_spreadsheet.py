import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from analyze import valid

good = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
        "params": {"cells": [["Month", "Sales"], ["Jan", 100]]}}
assert valid(good), "well-formed spreadsheet spec should be valid"

no_cells = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
            "params": {"features": ["wrap"]}}
assert not valid(no_cells), "missing cells should be invalid"

empty = {"has_concept": True, "widget": "spreadsheet", "title": "t", "explanation": "e",
         "params": {"cells": []}}
assert not valid(empty), "empty cells should be invalid"

print("OK")
