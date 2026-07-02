"""Phi-4-mini ONNX (int4, CPU) via onnxruntime-genai, streaming.

ponytail: lazy module-level singleton, loaded on first use. If the model isn't
present or GENERATE=false, callers fall back to extractive answers — the
retrieval pipeline stays runnable without 2 GB of weights."""
from __future__ import annotations

import glob
import os
from functools import lru_cache

import numpy as np

_VARIANT = "cpu_and_mobile/cpu-int4-rtn-block-32-acc-level-4"
# ponytail: hard cap on injected context. Regulatory sections run long; an
# uncapped 5-section prompt OOMs the int4 CPU model's attention. ~8k chars
# (~2k tokens) holds the top sections and keeps generation fast. Raise if a
# bigger machine / smarter chunking lands (Phase 1 section-aware splitting).
_CONTEXT_CHARS = int(os.getenv("CONTEXT_CHAR_BUDGET", "8000"))

_SYS = (
    "You are an AML/KYC compliance research assistant. Answer ONLY from the "
    "provided regulatory CONTEXT. Cite the controlling section (e.g. 31 CFR "
    "1010.311) inline. If the context does not contain the answer, say so — do "
    "not guess. This is research, not legal advice."
)


def _model_dir() -> str | None:
    env = os.getenv("PHI4_MODEL_DIR")
    if env and os.path.isdir(env):
        return env
    try:
        from huggingface_hub import snapshot_download
        root = snapshot_download("microsoft/Phi-4-mini-instruct-onnx",
                                 allow_patterns=[f"{_VARIANT}/*"])
    except Exception:
        return None
    hits = glob.glob(os.path.join(root, _VARIANT))
    return hits[0] if hits and os.path.isfile(os.path.join(hits[0], "genai_config.json")) else None


@lru_cache(maxsize=1)
def _load():
    import onnxruntime_genai as og
    d = _model_dir()
    if not d:
        raise RuntimeError("Phi-4 ONNX weights not found")
    model = og.Model(d)
    return og, model, og.Tokenizer(model)


def available() -> bool:
    try:
        _load()
        return True
    except Exception:
        return False


def stream(question: str, context: str, max_new_tokens: int = 400):
    """Yield answer text chunks grounded in `context`."""
    og, model, tok = _load()
    context = context[:_CONTEXT_CHARS]
    prompt = (f"<|system|>{_SYS}<|end|>"
              f"<|user|>CONTEXT:\n{context}\n\nQUESTION: {question}<|end|>"
              f"<|assistant|>")
    input_tokens = tok.encode(prompt)
    params = og.GeneratorParams(model)
    params.set_search_options(max_length=len(input_tokens) + max_new_tokens, do_sample=False)
    # ponytail: og's pybind binding rejects a plain list here; numpy array binds.
    params.input_ids = np.asarray([input_tokens], dtype=np.int32)
    gen = og.Generator(model, params)
    stream_tok = tok.create_stream()
    while not gen.is_done():
        gen.compute_logits()
        gen.generate_next_token()
        yield stream_tok.decode(gen.get_next_tokens()[0])
