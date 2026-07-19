import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from analyze import OpenAIBackend
from agent.kg import paired_quality_metrics
from agent.paired import ConditionResult, PairedExperimentConfig, run_paired_experiment


def _spec(title, *, reused=False):
    spec = {
        "has_concept": True,
        "widget": "softmax",
        "title": title,
        "explanation": title,
        "params": {"logits": [1, 2]},
    }
    if reused:
        spec["recursive_reuse"] = {"concept": title}
    return spec


class PairedQualityMetricsTests(unittest.TestCase):
    def test_scores_actual_warm_output_against_cold_ground_truth(self):
        cold = [_spec("Self-attention"), _spec("Softmax"), _spec("Layer normalization")]
        warm = [
            _spec("Self-attention", reused=True),
            _spec("Mortgage payment", reused=True),
            _spec("Layer normalization"),
        ]
        seed_nodes = [{"name": "self-attention"}, {"name": "softmax"}]

        metrics = paired_quality_metrics(cold, warm, seed_nodes)

        self.assertEqual(metrics["known_concepts"], 2)
        self.assertEqual(metrics["retrieved_concepts"], 2)
        self.assertEqual(metrics["known_concept_recall"], 0.5)
        self.assertEqual(metrics["retrieval_precision"], 0.5)
        self.assertEqual(metrics["overall_concept_recall"], 0.667)


class PairedExperimentSequenceTests(unittest.TestCase):
    def test_condition_commands_share_model_prompt_frame_and_image_settings(self):
        config = PairedExperimentConfig(
            experiment_id="pair123",
            topic="ai_stem_pair123",
            backend="vllm",
            genre="ai_stem",
            max_px=512,
        )

        cold = config.analysis_command("cold")
        warm = config.analysis_command("warm")

        for flag in ("--backend", "--data", "--video", "--genre", "--experiment-id", "--max-px"):
            self.assertEqual(cold[cold.index(flag) + 1], warm[warm.index(flag) + 1])
        self.assertIn("--defer-admission", cold)
        self.assertIn("--defer-admission", warm)
        self.assertEqual(cold[cold.index("--recursive-mode") + 1], "cold")
        self.assertEqual(warm[warm.index("--recursive-mode") + 1], "warm")

    def test_target_is_admitted_only_after_both_conditions_and_metrics(self):
        events = []
        config = PairedExperimentConfig(
            experiment_id="pair123",
            topic="ai_stem_pair123",
            backend="vllm",
            max_px=512,
        )

        class FakeStore:
            def prepare(self, _config):
                events.append("prepare_seed_only")
                return [{"name": "self-attention"}]

            def assert_target_absent(self, _config):
                events.append("target_absent")

            def finalize(self, _config, _cold, _warm, metrics):
                events.append("metrics_persisted")
                self.metrics = metrics

            def admit(self, _config, _specs):
                events.append("target_admitted")

            def summary(self, _config):
                return {"node_count": 2}

        def run_condition(_config, mode):
            events.append(mode)
            specs = [_spec("Self-attention", reused=mode == "warm")]
            return ConditionResult(
                mode=mode,
                run={"vlm_calls": 64 if mode == "cold" else 8, "build_ms": 1000},
                specs=specs,
            )

        result = run_paired_experiment(
            config,
            store=FakeStore(),
            condition_runner=run_condition,
        )

        self.assertEqual(events, [
            "prepare_seed_only",
            "cold",
            "target_absent",
            "warm",
            "target_absent",
            "metrics_persisted",
            "target_admitted",
        ])
        self.assertEqual(result["cold"]["vlm_calls"], 64)
        self.assertEqual(result["warm"]["vlm_calls"], 8)
        self.assertEqual(result["delta"]["actual_calls_saved"], 56)


class ActualCallInstrumentationTests(unittest.TestCase):
    def test_openai_backend_counts_each_executed_model_request(self):
        class Message:
            def __init__(self, content):
                self.content = content

        class Completions:
            def __init__(self):
                self.responses = ["", '{"has_concept": false}']

            def create(self, **_kwargs):
                content = self.responses.pop(0)
                return type("Response", (), {
                    "choices": [type("Choice", (), {"message": Message(content)})()],
                })()

        backend = OpenAIBackend.__new__(OpenAIBackend)
        backend.model = "nemotron-test"
        backend.model_name = "nemotron-test"
        backend.client = type("Client", (), {
            "chat": type("Chat", (), {"completions": Completions()})(),
        })()
        backend.call_count = 0

        with NamedTemporaryFile(suffix=".jpg") as frame:
            Path(frame.name).write_bytes(b"not-a-real-jpeg")
            backend.ask(Path(frame.name), "teacher context")

        self.assertEqual(backend.call_count, 2)


if __name__ == "__main__":
    unittest.main()
