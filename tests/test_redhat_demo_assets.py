import json
import stat
import unittest
from pathlib import Path

from analyze import valid


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "5IgOP7Lpk5g"
ASSETS = ROOT / "docs" / "assets" / "redhat-vllm-demo"


class RedHatDemoAssetsTests(unittest.TestCase):
    def test_portable_excel_lesson_is_complete(self):
        for name in ("chapters.json", "concepts.json", "frames.json", "metadata.json", "transcript.json", "user_concepts.json"):
            self.assertTrue((DEMO / name).is_file(), name)
        self.assertEqual(json.loads((DEMO / "metadata.json").read_text()), {"duration": 331.0})

    def test_demo_moments_are_valid_portable_spreadsheets(self):
        concepts = json.loads((DEMO / "concepts.json").read_text())
        self.assertEqual([round(concept["time"]) for concept in concepts], [0, 40, 142, 266])
        self.assertTrue(all(concept["widget"] == "spreadsheet" and valid(concept) for concept in concepts))
        runtime_fields = {"user_made", "id", "owner", "created_at", "replaces_key", "supersedes"}
        self.assertTrue(all(runtime_fields.isdisjoint(concept) for concept in concepts))
        frame_names = {frame["file"] for frame in json.loads((DEMO / "frames.json").read_text())}
        self.assertTrue(all(concept["frame"] in frame_names for concept in concepts))

    def test_demo_includes_one_valid_viewer_shared_widget(self):
        shared = json.loads((DEMO / "user_concepts.json").read_text())
        self.assertEqual(len(shared), 1)
        self.assertTrue(valid(shared[0]))
        self.assertEqual(round(shared[0]["time"]), 40)
        self.assertTrue(shared[0]["user_made"])
        self.assertEqual(shared[0]["owner"], "community-demo")
        self.assertTrue(shared[0]["id"])

    def test_runbook_links_every_fallback_asset_and_metric(self):
        runbook = (ROOT / "docs" / "RED_HAT_VLLM_DEMO.md").read_text()
        self.assertIn("http://localhost:5173/", runbook)
        self.assertIn("http://localhost:5173/?v=5IgOP7Lpk5g", runbook)
        self.assertIn("http://localhost:8106/perf.html#throughput", runbook)
        self.assertIn("touch the screen", runbook)
        self.assertIn("Add a Quarter column.", runbook)
        for claim in ("0.40", "0.67", "1.70×", "0.17", "0.47", "2.70×", "9.78×"):
            self.assertIn(claim, runbook)
        for name in ("excel-widget", "community-reuse", "refined-quarter-widget", "vllm-engine-live", "vllm-throughput", "paged-attention"):
            path = ASSETS / f"{name}.png"
            self.assertTrue(path.is_file(), path)
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), path)
            self.assertIn(f"assets/redhat-vllm-demo/{name}.png", runbook)

    def test_preflight_is_executable(self):
        mode = (ROOT / "scripts" / "preflight-redhat-demo.sh").stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
