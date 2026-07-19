"""Rebuild the post-experiment Recursive Intelligence source library from cached specs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import kg


SOURCE_VIDEOS = [
    "kCc8FmEb1nY",
    "42L1q1Z4Ojc",
    "l8pRSuU81PU",
    "4Bdc55j80l8",
    "qg4PchTECck",
    "jmmW0F0biz0",
    "LudWfvu3ong",
    "csWluHwfsB8",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="ai_stem_pair_p20260719a")
    args = parser.parse_args()
    kg.build_graph(args.topic, SOURCE_VIDEOS)
    # Admission stays after the source build to preserve the paired experiment's isolation.
    warm_path = kg.DATA / "42L1q1Z4Ojc" / "concepts.paired.p20260719a.warm.json"
    kg.ingest_specs(args.topic, "42L1q1Z4Ojc", json.loads(warm_path.read_text()))
    result = kg.graph_snapshot(args.topic)["summary"]
    print(
        f"{args.topic}: {result['node_count']} concepts, "
        f"{result['exemplar_count']} exemplars, {result['video_count']} videos, "
        f"{result['teacher_count']} teachers"
    )


if __name__ == "__main__":
    main()
