"""Persistent cross-teacher concept memory and recursive-processing benchmarks."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import time
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import psycopg2.extras

from agent import db


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MIGRATION = ROOT / "supabase" / "migrations" / "20260719043000_recursive_intelligence.sql"

DEMO_VIDEO_META = {
    "kCc8FmEb1nY": {
        "title": "Let's build GPT: from scratch, in code, spelled out",
        "channel": "Andrej Karpathy",
    },
    "42L1q1Z4Ojc": {
        "title": "Multi-Head Attention Explained Visually",
        "channel": "VisualAI",
    },
}

CONCEPT_ALIASES = (
    ("multi-head-attention", "Multi-head attention", (r"multi[ -]?head",)),
    ("cross-entropy", "Cross-entropy loss", (r"cross[ -]?entropy",)),
    ("causal-masking", "Causal attention masking", (r"causal.*mask", r"mask.*causal", r"tril trick")),
    ("scaled-dot-product-attention", "Scaled dot-product attention", (r"scaled dot", r"scaling.*softmax")),
    ("self-attention", "Self-attention", (r"self[ -]?attention", r"query[ -]?key", r"attention weight", r"attention score")),
    ("softmax", "Softmax", (r"softmax", r"logits? to probabilit")),
    ("token-embedding", "Token embeddings", (r"embedding",)),
    ("matrix-multiplication", "Matrix multiplication", (r"matrix multip", r"linear weighted sum")),
    ("residual-connection", "Residual connections", (r"residual", r"gradient highway")),
    ("layer-normalization", "Layer normalization", (r"layer norm", r"normalization transform")),
    ("gelu", "GELU activation", (r"gelu",)),
    ("relu", "ReLU activation", (r"relu",)),
    ("learning-rate", "Learning rate", (r"learning rate",)),
    ("transformer-scaling", "Transformer scaling", (r"parameter scaling", r"transformer.*scal")),
    ("linear-regression", "Linear regression", (r"linear regression",)),
    ("mortgage-payment", "Mortgage payment", (r"mortgage", r"pmi")),
    ("cash-flow", "Cash flow", (r"cash flow", r"cash-on-cash")),
    ("compound-growth", "Compound growth", (r"compound", r"dividend.*growth", r"dollar cost averaging")),
)

STOPWORDS = {
    "a", "an", "and", "as", "at", "based", "by", "effect", "for", "from", "in", "into",
    "live", "mechanism", "model", "of", "on", "the", "to", "via", "visualizing", "with",
}

PREREQUISITES = (
    ("matrix-multiplication", "self-attention"),
    ("softmax", "self-attention"),
    ("self-attention", "multi-head-attention"),
    ("causal-masking", "scaled-dot-product-attention"),
    ("token-embedding", "self-attention"),
    ("relu", "residual-connection"),
)


def _plain(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _plain(value).split() if token and token not in STOPWORDS}


def canonicalize_concept(title: str, explanation: str = "", widget: str = "") -> tuple[str, str]:
    text = _plain(f"{title} {explanation}")
    for name, label, patterns in CONCEPT_ALIASES:
        if any(re.search(pattern, text) for pattern in patterns):
            return name, label

    tokens = [token for token in text.split() if token not in STOPWORDS]
    if not tokens:
        fallback = _plain(widget).replace(" ", "-") or "interactive-concept"
        return fallback, fallback.replace("-", " ").title()
    name = "-".join(tokens[:5])
    return name, " ".join(tokens[:5]).title()


def concept_quality(spec: dict) -> float:
    score = 0.35
    score += 0.15 if spec.get("title") else 0
    score += 0.15 if spec.get("explanation") else 0
    params = spec.get("params") or {}
    score += min(0.25, len(json.dumps(params, sort_keys=True)) / 1200)
    score += 0.1 if spec.get("widget") not in (None, "none") else 0
    return round(min(1.0, score), 3)


def observations_from_specs(video_id: str, topic: str, specs: list[dict]) -> list[dict]:
    meta = DEMO_VIDEO_META.get(video_id, {})
    observations = []
    for spec in specs:
        if not isinstance(spec, dict) or spec.get("widget") in (None, "none"):
            continue
        name, label = canonicalize_concept(
            spec.get("title", ""), spec.get("explanation", ""), spec.get("widget", ""))
        observations.append({
            "topic": topic,
            "name": name,
            "label": label,
            "video_id": video_id,
            "video_title": meta.get("title", video_id),
            "channel": meta.get("channel", "Unknown teacher"),
            "t_s": float(spec.get("time", 0)),
            "widget": spec.get("widget", ""),
            "quality": concept_quality(spec),
            "spec": spec,
        })
    return observations


def load_observations(video_id: str, topic: str) -> list[dict]:
    path = DATA / video_id / "concepts.json"
    if not path.exists():
        raise FileNotFoundError(f"no cached concepts for {video_id}")
    return observations_from_specs(video_id, topic, json.loads(path.read_text()))


def ensure_schema() -> None:
    with db.conn() as connection, connection.cursor() as cursor:
        cursor.execute(MIGRATION.read_text())
        connection.commit()


def _next_run_seq(cursor, topic: str) -> int:
    cursor.execute("select coalesce(max(run_seq), 0) + 1 from topic_runs where topic=%s", (topic,))
    return int(cursor.fetchone()[0])


def _cached_concept_id(cursor, video_id: str, t_s: float) -> int | None:
    cursor.execute(
        "select id from concepts where video_id=%s order by abs(coalesce(t_s, 0)-%s) limit 1",
        (video_id, t_s),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def _upsert_observations(cursor, topic: str, observations: Iterable[dict], run_seq: int) -> dict[str, int]:
    node_ids: dict[str, int] = {}
    inserted_links = 0
    for observation in observations:
        cursor.execute(
            "insert into kg_concept(topic,name,label,first_run) values (%s,%s,%s,%s) "
            "on conflict (topic,name) do update set label=excluded.label returning id",
            (topic, observation["name"], observation["label"], run_seq),
        )
        node_id = int(cursor.fetchone()[0])
        node_ids[observation["name"]] = node_id
        concept_id = _cached_concept_id(cursor, observation["video_id"], observation["t_s"])
        cursor.execute(
            "insert into kg_frame_link(kg_concept_id,concept_id,topic,video_id,video_title,t_s,channel,widget,quality,spec) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "on conflict (kg_concept_id,video_id,t_s) do update set "
            "concept_id=excluded.concept_id, video_title=excluded.video_title, channel=excluded.channel, "
            "widget=excluded.widget, quality=excluded.quality, spec=excluded.spec returning (xmax = 0)",
            (
                node_id, concept_id, topic, observation["video_id"], observation["video_title"],
                observation["t_s"], observation["channel"], observation["widget"],
                observation["quality"], json.dumps(observation["spec"]),
            ),
        )
        inserted_links += int(bool(cursor.fetchone()[0]))

    cursor.execute(
        "update kg_concept c set exemplar_count=(select count(*) from kg_frame_link l where l.kg_concept_id=c.id), "
        "best_link_id=(select l.id from kg_frame_link l where l.kg_concept_id=c.id "
        "order by l.quality desc, l.created_at limit 1) where c.topic=%s",
        (topic,),
    )
    return {"nodes_seen": len(node_ids), "links_inserted": inserted_links}


def _rebuild_edges(cursor, topic: str) -> int:
    cursor.execute("delete from kg_edge where topic=%s", (topic,))
    cursor.execute(
        "select l.video_id,l.t_s,c.id,c.name from kg_frame_link l join kg_concept c on c.id=l.kg_concept_id "
        "where l.topic=%s order by l.video_id,l.t_s",
        (topic,),
    )
    by_video: dict[str, list[tuple[float, int, str]]] = {}
    for video_id, t_s, node_id, name in cursor.fetchall():
        by_video.setdefault(video_id, []).append((float(t_s), int(node_id), name))

    weights: Counter[tuple[int, int]] = Counter()
    for items in by_video.values():
        previous = None
        for t_s, node_id, _name in items:
            if previous and previous[1] != node_id and t_s - previous[0] <= 240:
                pair = tuple(sorted((previous[1], node_id)))
                weights[pair] += 1
            previous = (t_s, node_id)

    for (src_id, dst_id), weight in weights.items():
        cursor.execute(
            "insert into kg_edge(topic,src_id,dst_id,kind,weight) values (%s,%s,%s,'related',%s)",
            (topic, src_id, dst_id, weight),
        )

    cursor.execute("select name,id from kg_concept where topic=%s", (topic,))
    ids = {name: int(node_id) for name, node_id in cursor.fetchall()}
    for source, target in PREREQUISITES:
        if source in ids and target in ids and ids[source] != ids[target]:
            cursor.execute(
                "insert into kg_edge(topic,src_id,dst_id,kind,weight) values (%s,%s,%s,'prereq',1) "
                "on conflict (topic,src_id,dst_id,kind) do update set weight=excluded.weight",
                (topic, ids[source], ids[target]),
            )

    cursor.execute("delete from kg_widget_prior where topic=%s", (topic,))
    cursor.execute(
        "insert into kg_widget_prior(topic,concept_name,widget,tried,valid) "
        "select %s,c.name,l.widget,count(*),count(*) filter (where l.quality >= 0.6) "
        "from kg_frame_link l join kg_concept c on c.id=l.kg_concept_id "
        "where l.topic=%s group by c.name,l.widget",
        (topic, topic),
    )
    cursor.execute("select count(*) from kg_edge where topic=%s", (topic,))
    return int(cursor.fetchone()[0])


def _insert_run(cursor, payload: dict) -> int:
    columns = (
        "experiment_id", "topic", "run_seq", "mode", "video_id", "source_videos",
        "frames_total", "frames_analyzed", "vlm_calls", "widgets_new", "widgets_reused",
        "novel_concepts", "known_concepts", "build_ms", "yield", "concept_recall",
        "retrieval_precision", "model", "prompt_version", "metadata",
    )
    cursor.execute(
        f"insert into topic_runs({','.join(columns)}) values ({','.join(['%s'] * len(columns))}) returning id",
        tuple(json.dumps(payload.get(key, {})) if key == "metadata" else payload.get(key) for key in columns),
    )
    return int(cursor.fetchone()[0])


def build_graph(topic: str, video_ids: list[str]) -> dict:
    ensure_schema()
    started = time.perf_counter()
    observations = [item for video_id in video_ids for item in load_observations(video_id, topic)]
    with db.conn() as connection, connection.cursor() as cursor:
        run_seq = _next_run_seq(cursor, topic)
        changes = _upsert_observations(cursor, topic, observations, run_seq)
        edge_count = _rebuild_edges(cursor, topic)
        build_ms = round((time.perf_counter() - started) * 1000)
        _insert_run(cursor, {
            "experiment_id": None,
            "topic": topic,
            "run_seq": run_seq,
            "mode": "learn",
            "video_id": video_ids[-1] if video_ids else None,
            "source_videos": video_ids,
            "frames_total": len(observations),
            "frames_analyzed": len(observations),
            "vlm_calls": 0,
            "widgets_new": changes["links_inserted"],
            "widgets_reused": len(observations) - changes["links_inserted"],
            "novel_concepts": changes["nodes_seen"],
            "known_concepts": len(observations) - changes["nodes_seen"],
            "build_ms": build_ms,
            "yield": 1.0 if observations else 0.0,
            "concept_recall": 1.0 if observations else 0.0,
            "retrieval_precision": 1.0,
            "model": "cached-concept-specs",
            "prompt_version": "kg-v1",
            "metadata": {"measurement": "knowledge imported from real prior model outputs"},
        })
        connection.commit()
    snapshot = graph_snapshot(topic)
    return {"ok": True, "build_ms": build_ms, "edges": edge_count, **changes, **snapshot["summary"]}


def ingest_specs(topic: str, video_id: str, specs: list[dict]) -> dict:
    ensure_schema()
    observations = observations_from_specs(video_id, topic, specs)
    with db.conn() as connection, connection.cursor() as cursor:
        run_seq = _next_run_seq(cursor, topic)
        changes = _upsert_observations(cursor, topic, observations, run_seq)
        edge_count = _rebuild_edges(cursor, topic)
        connection.commit()
    return {**changes, "edge_count": edge_count}


def graph_snapshot(topic: str) -> dict:
    ensure_schema()
    with db.conn() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            "select id,name,label,exemplar_count,best_link_id,first_run from kg_concept "
            "where topic=%s order by exemplar_count desc,name",
            (topic,),
        )
        nodes = [dict(row) for row in cursor.fetchall()]
        cursor.execute(
            "select l.id,l.kg_concept_id,l.video_id,l.video_title,l.t_s,l.channel,l.widget,l.quality,l.spec "
            "from kg_frame_link l where l.topic=%s order by l.kg_concept_id,l.quality desc,l.t_s",
            (topic,),
        )
        links = [dict(row) for row in cursor.fetchall()]
        cursor.execute("select src_id,dst_id,kind,weight from kg_edge where topic=%s", (topic,))
        edges = [dict(row) for row in cursor.fetchall()]

    by_node: dict[int, list[dict]] = {}
    for link in links:
        by_node.setdefault(int(link["kg_concept_id"]), []).append(link)
    teachers = set()
    for node in nodes:
        node_links = by_node.get(int(node["id"]), [])
        node["exemplars"] = node_links
        node["widgets"] = sorted({link["widget"] for link in node_links if link.get("widget")})
        node["teachers"] = sorted({link["channel"] for link in node_links if link.get("channel")})
        teachers.update(node["teachers"])
    reinforced = sum(1 for node in nodes if node["exemplar_count"] > 1)
    return {
        "topic": topic,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "exemplar_count": len(links),
            "reinforced_nodes": reinforced,
            "teacher_count": len(teachers),
        },
    }


def _match_node(name: str, nodes: list[dict], threshold: float = 0.72) -> tuple[dict | None, float]:
    exact = next((node for node in nodes if node["name"] == name), None)
    if exact:
        return exact, 1.0
    wanted = _tokens(name.replace("-", " "))
    best_node = None
    best_score = 0.0
    for node in nodes:
        candidate = _tokens(node["name"].replace("-", " "))
        union = wanted | candidate
        jaccard = len(wanted & candidate) / len(union) if union else 0.0
        sequence = SequenceMatcher(None, name, node["name"]).ratio()
        score = max(jaccard, sequence * 0.9)
        if score > best_score:
            best_node, best_score = node, score
    return (best_node, round(best_score, 3)) if best_score >= threshold else (None, round(best_score, 3))


def _context_match(context: str, nodes: list[dict]) -> tuple[dict | None, float]:
    context_tokens = _tokens(context)
    best_node = None
    best_score = 0.0
    for node in nodes:
        concept_tokens = _tokens(f"{node['name']} {node['label']}")
        if not concept_tokens:
            continue
        score = len(context_tokens & concept_tokens) / len(concept_tokens)
        if node["name"] == "self-attention" and {"query", "key"} <= context_tokens:
            score = max(score, 0.9)
        if node["name"] == "multi-head-attention" and "head" in context_tokens and "attention" in context_tokens:
            score = max(score, 0.95)
        if score > best_score:
            best_node, best_score = node, score
    return (best_node, round(best_score, 3)) if best_score >= 0.6 else (None, round(best_score, 3))


def _transcript_window(cues: list[dict], t_s: float, radius: float = 24.0) -> str:
    return " ".join(cue["text"] for cue in cues if t_s - radius <= cue["start"] <= t_s + radius)[:1800]


def plan_frames(topic: str, cues: list[dict], frames: list[dict], exploration_rate: float = 0.125) -> list[dict]:
    nodes = graph_snapshot(topic)["nodes"]
    if not nodes:
        return [
            {
                "kind": "explore",
                "frame": frame,
                "node": None,
                "score": 0.0,
                "context": _transcript_window(cues, float(frame["time"])),
            }
            for frame in frames
        ]
    candidates: dict[int, list[dict]] = {}
    for frame in frames:
        context = _transcript_window(cues, float(frame["time"]))
        node, score = _context_match(context, nodes)
        if node:
            candidates.setdefault(int(node["id"]), []).append({
                "kind": "reuse", "frame": frame, "node": node, "score": score, "context": context,
            })

    selected: list[dict] = []
    for node_candidates in candidates.values():
        kept: list[dict] = []
        for candidate in sorted(node_candidates, key=lambda item: (-item["score"], item["frame"]["time"])):
            if all(abs(candidate["frame"]["time"] - item["frame"]["time"]) >= 60 for item in kept):
                kept.append(candidate)
            if len(kept) == 3:
                break
        selected.extend(kept)

    selected_files = {item["frame"]["file"] for item in selected}
    remaining = [frame for frame in frames if frame["file"] not in selected_files]
    exploration_count = min(len(remaining), max(1, math.ceil(len(frames) * exploration_rate))) if frames else 0
    if exploration_count:
        step = len(remaining) / exploration_count
        for index in range(exploration_count):
            frame = remaining[min(len(remaining) - 1, int(index * step + step / 2))]
            selected.append({
                "kind": "explore",
                "frame": frame,
                "node": None,
                "score": 0.0,
                "context": _transcript_window(cues, float(frame["time"])),
            })
    return sorted(selected, key=lambda item: item["frame"]["time"])


def reusable_spec(plan: dict) -> dict | None:
    node = plan.get("node")
    if not node or not node.get("exemplars"):
        return None
    best = max(node["exemplars"], key=lambda item: (item.get("quality", 0), -item.get("t_s", 0)))
    spec = copy.deepcopy(best.get("spec") or {})
    spec["recursive_reuse"] = {
        "concept": node["name"],
        "confidence": plan.get("score", 0),
        "source_video": best.get("video_id"),
        "source_time": best.get("t_s"),
    }
    return spec


def log_processing_run(topic: str, payload: dict) -> int:
    ensure_schema()
    with db.conn() as connection, connection.cursor() as cursor:
        payload = {**payload, "topic": topic, "run_seq": _next_run_seq(cursor, topic)}
        run_id = _insert_run(cursor, payload)
        connection.commit()
        return run_id


def replay_benchmark(topic: str, target_video_id: str, add_to_graph: bool = True) -> dict:
    ensure_schema()
    started = time.perf_counter()
    target = load_observations(target_video_id, topic)
    snapshot = graph_snapshot(topic)
    nodes = snapshot["nodes"]
    matched = []
    for observation in target:
        node, score = _match_node(observation["name"], nodes)
        matched.append((observation, node, score))
    known = sum(1 for _observation, node, _score in matched if node)
    correct = sum(1 for observation, node, _score in matched if node and node["name"] == observation["name"])

    frames_path = DATA / target_video_id / "frames.json"
    cues_path = DATA / target_video_id / "transcript.json"
    frames = json.loads(frames_path.read_text()) if frames_path.exists() else []
    cues = json.loads(cues_path.read_text()) if cues_path.exists() else []
    plans = plan_frames(topic, cues, frames) if frames and cues else []
    warm_calls = sum(1 for plan in plans if plan["kind"] == "explore")
    warm_reuses = sum(1 for plan in plans if plan["kind"] == "reuse")
    frames_total = len(frames) or len(target)
    experiment_id = hashlib.sha1(
        f"{topic}:{target_video_id}:{time.time_ns()}".encode(), usedforsecurity=False).hexdigest()[:12]
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    cold = {
        "experiment_id": experiment_id,
        "topic": topic,
        "mode": "benchmark_cold",
        "video_id": target_video_id,
        "source_videos": [],
        "frames_total": frames_total,
        "frames_analyzed": frames_total,
        "vlm_calls": frames_total,
        "widgets_new": len(target),
        "widgets_reused": 0,
        "novel_concepts": len(target),
        "known_concepts": 0,
        "build_ms": 0,
        "yield": round(len(target) / max(1, frames_total), 3),
        "concept_recall": 1.0,
        "retrieval_precision": None,
        "model": "nemotron-3-nano-omni",
        "prompt_version": "full-sweep",
        "metadata": {"measurement": "cold full-sweep baseline over cached ground truth"},
    }
    warm = {
        "experiment_id": experiment_id,
        "topic": topic,
        "mode": "benchmark_warm",
        "video_id": target_video_id,
        "source_videos": sorted({link["video_id"] for node in nodes for link in node["exemplars"]}),
        "frames_total": frames_total,
        "frames_analyzed": len(plans),
        "vlm_calls": warm_calls,
        "widgets_new": len(target) - known,
        "widgets_reused": warm_reuses,
        "novel_concepts": len(target) - known,
        "known_concepts": known,
        "build_ms": elapsed_ms,
        "yield": round(len(target) / max(1, len(plans)), 3),
        "concept_recall": round(known / max(1, len(target)), 3),
        "retrieval_precision": round(correct / max(1, known), 3),
        "model": "nemotron-3-nano-omni + self-RAG",
        "prompt_version": "kg-v1",
        "metadata": {
            "measurement": "held-out replay; warm calls are the concrete exploration-frame plan",
            "target_concepts": len(target),
            "planned_frames": [
                {"time": plan["frame"]["time"], "kind": plan["kind"],
                 "concept": plan["node"]["name"] if plan["node"] else None}
                for plan in plans
            ],
        },
    }

    with db.conn() as connection, connection.cursor() as cursor:
        cold["run_seq"] = _next_run_seq(cursor, topic)
        _insert_run(cursor, cold)
        warm["run_seq"] = cold["run_seq"] + 1
        _insert_run(cursor, warm)
        if add_to_graph:
            _upsert_observations(cursor, topic, target, warm["run_seq"])
            _rebuild_edges(cursor, topic)
        connection.commit()

    reduction = round((1 - warm_calls / max(1, frames_total)) * 100, 1)
    return {
        "ok": True,
        "experiment_id": experiment_id,
        "cold": cold,
        "warm": warm,
        "delta": {
            "vlm_calls_saved": frames_total - warm_calls,
            "call_reduction_pct": reduction,
            "known_concept_recall": warm["concept_recall"],
            "retrieval_precision": warm["retrieval_precision"],
        },
        "graph": graph_snapshot(topic)["summary"],
    }


def recursion_runs(topic: str, limit: int = 30) -> list[dict]:
    ensure_schema()
    with db.conn() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            "select * from topic_runs where topic=%s order by created_at desc,id desc limit %s",
            (topic, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
