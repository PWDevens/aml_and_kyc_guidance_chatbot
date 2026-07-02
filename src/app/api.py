"""Flask + SSE serving. One path: retrieve -> (generate | extractive) -> stream.
ponytail: Flask dev server is fine for a local CPU demo; Hypercorn/ASGI is a
Phase-5 packaging concern, not a Phase-0 need."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

from ..etl import state as etl_state
from ..rag import cache
from ..rag.config import CONFIG
from ..rag.indexing.builder import get_collection
from ..rag.llm import models
from ..rag.retrieval.factory import retrieve

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=None)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True, "rag_mode": CONFIG.rag_mode, "generate": models.available() if CONFIG.generate else False}


@app.get("/corpus_status")
def corpus_status():
    try:
        col = get_collection(CONFIG)
        n = col.count()
        got = col.get(include=["metadatas"])
        metas = got["metadatas"]
        as_of = (metas[0].get("as_of") if metas else None)
    except Exception as e:
        return {"indexed": 0, "error": str(e)}, 503

    try:
        last_etl_run = etl_state.last_successful_run(CONFIG)
    except Exception:
        last_etl_run = None  # ETL state db is optional infra

    return {
        "indexed": n,
        "as_of": as_of,
        "rag_mode": CONFIG.rag_mode,
        "last_etl_run": last_etl_run,
        "counts_by_source": etl_state.counts_by_source(metas),
    }


@app.post("/chat_stream")
def chat_stream():
    question = (request.get_json(force=True) or {}).get("question", "").strip()
    if not question:
        return {"error": "empty question"}, 400

    def gen():
        if CONFIG.answer_cache:
            hit = cache.get(CONFIG, question)
            if hit is not None:
                yield _sse("token", {"t": hit["answer"]})
                yield _sse("citations", {"citations": hit["citations"], "as_of": hit["as_of"]})
                yield _sse("done", {})
                return

        context, citations = retrieve(CONFIG, question)
        as_of = citations[0].get("as_of") if citations else None
        if not citations:
            yield _sse("token", {"t": "No matching regulatory text was found in the indexed corpus."})
        elif CONFIG.generate and models.available():
            # Only the generated (verified/authoritative) path is cache-eligible —
            # the extractive fallback and "no matching text" message below are not.
            answer_parts = []
            for chunk in models.stream(question, context, CONFIG.max_new_tokens):
                answer_parts.append(chunk)
                yield _sse("token", {"t": chunk})
            if CONFIG.answer_cache:
                cache.put(CONFIG, question, "".join(answer_parts), citations, as_of)
        else:
            # ponytail: extractive fallback so the demo answers without the LLM.
            yield _sse("token", {"t": "Most relevant provision:\n\n" + context.split("\n\n")[0]})
        yield _sse("citations", {"citations": citations, "as_of": as_of})
        yield _sse("done", {})

    return Response(gen(), mimetype="text/event-stream")
