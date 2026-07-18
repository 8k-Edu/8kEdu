"""The agent's brain — Nemotron Omni via the local LM Studio OpenAI-compatible server.
One model: vision (reads video frames) + reasoning + tool-calling. Local, $0.
"""
import json
import os
import re
from openai import OpenAI

BASE_URL = os.environ.get("NEMOTRON_BASE_URL", "http://localhost:1234/v1")
MODEL = os.environ.get("NEMOTRON_MODEL", "nvidia/nemotron-3-nano-omni")

_client = OpenAI(base_url=BASE_URL, api_key=os.environ.get("NEMOTRON_API_KEY", "lm-studio"))


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def think(system: str, user: str, max_tokens: int = 4000, temperature: float = 0.2) -> str:
    """Plain reasoning call. Returns the answer text (reasoning_content is discarded)."""
    r = _client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens, temperature=temperature,
    )
    return (r.choices[0].message.content or "").strip()


def decide(system: str, user: str, max_tokens: int = 4000) -> dict:
    """Reasoning call that must return a JSON object."""
    raw = think(system + "\n\nReply with ONLY a JSON object.", user, max_tokens, temperature=0.1)
    return _extract_json(raw) or {"_raw": raw[:400], "_parse_error": True}
