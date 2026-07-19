"""Executed cold/warm recursive-intelligence experiment orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from agent import db, kg
from agent.kg import paired_quality_metrics


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PairedExperimentConfig:
    experiment_id: str
    topic: str
    seed_video_id: str = "kCc8FmEb1nY"
    target_video_id: str = "42L1q1Z4Ojc"
    backend: str = "vllm"
    genre: str = "ai_stem"
    max_px: int = 512
    exploration_rate: float = 0.125
    data_dir: str = "data"
    expected_frames: int = 64

    def analysis_command(self, mode: str) -> list[str]:
        if mode not in {"cold", "warm"}:
            raise ValueError(f"unsupported paired condition: {mode}")
        return [
            sys.executable,
            "analyze.py",
            "--backend", self.backend,
            "--data", self.data_dir,
            "--video", self.target_video_id,
            "--genre", self.genre,
            "--recursive-topic", self.topic,
            "--recursive-mode", mode,
            "--experiment-id", self.experiment_id,
            "--exploration-rate", str(self.exploration_rate),
            "--max-px", str(self.max_px),
            "--out-name", f"concepts.paired.{self.experiment_id}.{mode}.json",
            "--run-kind", "paired",
            "--defer-admission",
        ]


@dataclass(frozen=True)
class ConditionResult:
    mode: str
    run: dict
    specs: list[dict]


class ExperimentStore(Protocol):
    def prepare(self, config: PairedExperimentConfig) -> list[dict]: ...
    def assert_target_absent(self, config: PairedExperimentConfig) -> None: ...
    def finalize(self, config: PairedExperimentConfig, cold: ConditionResult,
                 warm: ConditionResult, metrics: dict) -> None: ...
    def admit(self, config: PairedExperimentConfig, specs: list[dict]) -> dict | None: ...
    def summary(self, config: PairedExperimentConfig) -> dict: ...


ConditionRunner = Callable[[PairedExperimentConfig, str], ConditionResult]


class KgExperimentStore:
    def prepare(self, config: PairedExperimentConfig) -> list[dict]:
        frames_path = ROOT / config.data_dir / config.target_video_id / "frames.json"
        frames = json.loads(frames_path.read_text())
        if len(frames) != config.expected_frames:
            raise RuntimeError(
                f"paired target must contain exactly {config.expected_frames} frames; found {len(frames)}"
            )
        kg.ensure_schema()
        with db.conn() as connection, connection.cursor() as cursor:
            cursor.execute(
                "select (select count(*) from kg_concept where topic=%s) + "
                "(select count(*) from topic_runs where topic=%s)",
                (config.topic, config.topic),
            )
            if int(cursor.fetchone()[0]) != 0:
                raise RuntimeError(f"paired topic must be fresh and isolated: {config.topic}")
        kg.build_graph(config.topic, [config.seed_video_id])
        snapshot = kg.graph_snapshot(config.topic)
        source_videos = {
            exemplar["video_id"]
            for node in snapshot["nodes"]
            for exemplar in node.get("exemplars", [])
        }
        if source_videos != {config.seed_video_id}:
            raise RuntimeError(f"seed memory is not isolated: {sorted(source_videos)}")
        return snapshot["nodes"]

    def assert_target_absent(self, config: PairedExperimentConfig) -> None:
        snapshot = kg.graph_snapshot(config.topic)
        admitted = any(
            exemplar["video_id"] == config.target_video_id
            for node in snapshot["nodes"]
            for exemplar in node.get("exemplars", [])
        )
        if admitted:
            raise RuntimeError("held-out target entered memory before the pair completed")

    def finalize(self, config: PairedExperimentConfig, cold: ConditionResult,
                 warm: ConditionResult, metrics: dict) -> None:
        persisted = kg.finalize_paired_experiment(config.topic, config.experiment_id, metrics)
        cold.run.update(persisted["cold"])
        warm.run.update(persisted["warm"])

    def admit(self, config: PairedExperimentConfig, specs: list[dict]) -> dict:
        kg.ingest_specs(config.topic, config.target_video_id, specs)
        kg.mark_paired_target_admitted(config.topic, config.experiment_id)
        return {
            "cold": kg.paired_condition_run(config.topic, config.experiment_id, "cold"),
            "warm": kg.paired_condition_run(config.topic, config.experiment_id, "warm"),
        }

    def summary(self, config: PairedExperimentConfig) -> dict:
        return kg.graph_snapshot(config.topic)["summary"]


def run_analysis_condition(config: PairedExperimentConfig, mode: str) -> ConditionResult:
    subprocess.run(config.analysis_command(mode), cwd=ROOT, check=True)
    output = ROOT / config.data_dir / config.target_video_id / (
        f"concepts.paired.{config.experiment_id}.{mode}.json"
    )
    specs = json.loads(output.read_text())
    run = kg.paired_condition_run(config.topic, config.experiment_id, mode)
    return ConditionResult(mode=mode, run=run, specs=specs)


def run_paired_experiment(config: PairedExperimentConfig, *,
                          store: ExperimentStore | None = None,
                          condition_runner: ConditionRunner | None = None) -> dict:
    """Run both conditions before persisting metrics and admitting the target."""
    store = store or KgExperimentStore()
    condition_runner = condition_runner or run_analysis_condition
    seed_nodes = store.prepare(config)
    cold = condition_runner(config, "cold")
    store.assert_target_absent(config)
    warm = condition_runner(config, "warm")
    store.assert_target_absent(config)
    metrics = paired_quality_metrics(cold.specs, warm.specs, seed_nodes)
    store.finalize(config, cold, warm, metrics)
    admitted = store.admit(config, warm.specs)
    if admitted:
        cold.run.update(admitted["cold"])
        warm.run.update(admitted["warm"])

    cold_calls = int(cold.run.get("vlm_calls") or 0)
    warm_calls = int(warm.run.get("vlm_calls") or 0)
    cold_ms = int(cold.run.get("build_ms") or 0)
    warm_ms = int(warm.run.get("build_ms") or 0)
    return {
        "ok": True,
        "experiment_id": config.experiment_id,
        "topic": config.topic,
        "cold": cold.run,
        "warm": warm.run,
        "quality": metrics,
        "delta": {
            "actual_calls_saved": cold_calls - warm_calls,
            "actual_call_reduction_pct": round((1 - warm_calls / max(1, cold_calls)) * 100, 1),
            "elapsed_ms_saved": cold_ms - warm_ms,
            "elapsed_reduction_pct": round((1 - warm_ms / max(1, cold_ms)) * 100, 1),
        },
        "graph": store.summary(config),
    }


def _fresh_id() -> str:
    return hashlib.sha1(str(__import__("time").time_ns()).encode(), usedforsecurity=False).hexdigest()[:12]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a fresh executed cold/warm recursive experiment")
    parser.add_argument("--experiment-id", default="")
    parser.add_argument("--topic", default="", help="must be unused; defaults to ai_stem_pair_<id>")
    parser.add_argument("--seed-video", default="kCc8FmEb1nY")
    parser.add_argument("--target-video", default="42L1q1Z4Ojc")
    parser.add_argument("--backend", default="vllm", choices=["mlx", "lmstudio", "vllm", "gemini", "openai"])
    parser.add_argument("--genre", default="ai_stem")
    parser.add_argument("--max-px", type=int, default=512)
    parser.add_argument("--exploration-rate", type=float, default=0.125)
    parser.add_argument("--data", default="data")
    args = parser.parse_args()

    experiment_id = args.experiment_id or _fresh_id()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{4,48}", experiment_id):
        raise SystemExit("experiment id must contain only letters, numbers, underscore, or dash")
    topic = args.topic or f"ai_stem_pair_{experiment_id}"
    config = PairedExperimentConfig(
        experiment_id=experiment_id,
        topic=topic,
        seed_video_id=args.seed_video,
        target_video_id=args.target_video,
        backend=args.backend,
        genre=args.genre,
        max_px=args.max_px,
        exploration_rate=args.exploration_rate,
        data_dir=args.data,
    )
    result = run_paired_experiment(config)
    manifest = ROOT / args.data / args.target_video / f"paired.{experiment_id}.json"
    manifest.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))
    print(f"paired manifest: {manifest}")


if __name__ == "__main__":
    main()
