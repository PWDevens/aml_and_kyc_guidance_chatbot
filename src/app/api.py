"""Flask + SSE serving. One path: retrieve -> (generate | extractive) -> stream.
ponytail: Flask dev server is fine for a local CPU demo; Hypercorn/ASGI is a
Phase-5 packaging concern, not a Phase-0 need."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

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
        peek = col.get(limit=1, include=["metadatas"])
        as_of = (peek["metadatas"][0].get("as_of") if peek["metadatas"] else None)
    except Exception as e:
        return {"indexed": 0, "error": str(e)}, 503
    return {"indexed": n, "as_of": as_of, "rag_mode": CONFIG.rag_mode}


@app.post("/chat_stream")
def chat_stream():
    question = (request.get_json(force=True) or {}).get("question", "").strip()
    if not question:
        return {"error": "empty question"}, 400

    def gen():
        context, citations = retrieve(CONFIG, question)
        if not citations:
            yield _sse("token", {"t": "No matching regulatory text was found in the indexed corpus."})
        elif CONFIG.generate and models.available():
            for chunk in models.stream(question, context, CONFIG.max_new_tokens):
                yield _sse("token", {"t": chunk})
        else:
            # ponytail: extractive fallback so the demo answers without the LLM.
            yield _sse("token", {"t": "Most relevant provision:\n\n" + context.split("\n\n")[0]})
        as_of = citations[0].get("as_of") if citations else None
        yield _sse("citations", {"citations": citations, "as_of": as_of})
        yield _sse("done", {})

    return Response(gen(), mimetype="text/event-stream")
