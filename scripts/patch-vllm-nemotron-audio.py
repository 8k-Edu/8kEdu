#!/usr/bin/env python3
"""Fix vllm-mlx / mlx_vlm loading of the Nemotron-3-Nano-Omni 4bit checkpoint.

mlx-community's 4bit conversion already stores the audio (sound_encoder) conv
weights in MLX layout — Conv1d (out, kW, in) and Conv2d (out, kH, kW, in). But
mlx_vlm's `sanitize_audio_weights` assumes PyTorch layout and re-transposes every
`sound_encoder.encoder.*.weight`, double-applying the layout swap. The server then
dies at load with e.g.:

    ValueError: Expected shape (256, 3, 3, 1) but received shape (256, 3, 1, 3)
    for parameter sound_encoder.encoder.subsampling.layers.0.weight

8kEdu uses only the vision + text towers, but the loader validates every parameter,
so the broken audio branch blocks the whole model. This patch makes the audio-weight
transpose a no-op for this pre-converted checkpoint (the filters that drop
feature_extractor / num_batches_tracked keys are preserved), which lets the full
model load and serve on Apple-Silicon vllm-mlx.

Idempotent: safe to run repeatedly (e.g. after `uv tool upgrade vllm-mlx`).

  uv run python scripts/patch-vllm-nemotron-audio.py
"""
import importlib.util
import re
import sys
from pathlib import Path

MARKER = "# 8kedu-patch: mlx-community 4bit stores audio convs in MLX layout already"


def find_audio_py() -> Path:
    spec = importlib.util.find_spec("mlx_vlm")
    if spec is None or not spec.submodule_search_locations:
        # fall back to the vllm-mlx uv tool env, whose interpreter isn't the one running us
        for base in Path.home().glob(".local/share/uv/tools/vllm-mlx/lib/python*/site-packages"):
            cand = base / "mlx_vlm" / "models" / "nemotron_h_nano_omni" / "audio.py"
            if cand.exists():
                return cand
        raise SystemExit("could not locate mlx_vlm (is vllm-mlx / mlx-vlm installed?)")
    return Path(spec.submodule_search_locations[0]) / "models" / "nemotron_h_nano_omni" / "audio.py"


def main() -> int:
    path = find_audio_py()
    src = path.read_text()
    if MARKER in src:
        print(f"already patched: {path}")
        return 0

    # Replace the two transpose lines inside sanitize_audio_weights with a pass-through.
    pat = re.compile(
        r'(if key\.startswith\("sound_encoder\.encoder\."\):\n)'
        r'(\s*)if key\.endswith\("\.weight"\) and value\.ndim == 3:\n'
        r'\s*value = value\.transpose\(0, 2, 1\)\n'
        r'\s*elif key\.endswith\("\.weight"\) and value\.ndim == 4:\n'
        r'\s*value = value\.transpose\(0, 2, 3, 1\)\n'
    )
    m = pat.search(src)
    if not m:
        print("ERROR: sanitize_audio_weights transpose block not found — mlx_vlm layout "
              "may have changed. Inspect it manually:", path, file=sys.stderr)
        return 2
    indent = m.group(2)
    replacement = (
        m.group(1)
        + f"{indent}{MARKER}\n"
        + f"{indent}# so the PyTorch->MLX transpose here would double-apply; keep as-is.\n"
        + f"{indent}pass\n"
    )
    path.write_text(src[:m.start()] + replacement + src[m.end():])
    print(f"patched: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
