"""Flask + SSE serving. One path: retrieve -> (generate | extractive) -> stream.
Deliberately minimal: the Flask dev server is fine for a local CPU demo;
Hypercorn/ASGI is a Phase-5 packaging concern, not a Phase-0 need.

Phase 3 (D9): chat_stream.gen() gains a Tier-1 semantic FAQ fast-path (ahead
of the iter-2 Tier-2 exact-match cache) and, when CONFIG.orchestration is on,
an orchestrated frame->classify->route->retrieve->verify path. Hard
constraint (AC-2): with orchestration=False AND faq_cache=False, gen() must
produce byte-identical SSE output to iter-2. The iter-2 body below is kept as
the literal, untouched `else` branch to guarantee that — see
_gen_iter2_path()."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

from ..etl import state as etl_state
from ..rag import cache
from ..rag.config import CONFIG
from ..rag.faq import matcher as faq_matcher
from ..rag.indexing.builder import get_collection
from ..rag.llm import models
from ..rag.orchestration import planner
from ..rag.orchestration.verify import verify_answer
from ..rag.retrieval.factory import retrieve

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=None)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/cognitus.css")
def cognitus_css():
    return send_from_directory(STATIC, "cognitus.css")


@app.get("/cognitus.js")
def cognitus_js():
    return send_from_directory(STATIC, "cognitus.js")


@app.get("/app.js")
def app_js():
    return send_from_directory(STATIC, "app.js")


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


def _gen_iter2_path(question: str):
    """The exact, untouched iter-2 body (D9 hard constraint / AC-2). Do not
    edit this to add Phase-3 behavior — it is the byte-identical collapse
    target when orchestration=False and faq_cache=False."""
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
        # Deliberately simple extractive fallback so the demo answers without the LLM.
        yield _sse("token", {"t": "Most relevant provision:\n\n" + context.split("\n\n")[0]})
    yield _sse("citations", {"citations": citations, "as_of": as_of})
    yield _sse("done", {})


def _gen_orchestrated_path(question: str):
    """Phase 3 (D9 steps 2-6): Tier-2 cache unchanged, then frame->classify->
    route->retrieve via planner.plan(), buffered generation, buffer-then-
    verify (D10), then the same Tier-2-write + citations tail as iter-2."""
    if CONFIG.answer_cache:
        hit = cache.get(CONFIG, question)
        if hit is not None:
            yield _sse("token", {"t": hit["answer"]})
            yield _sse("citations", {"citations": hit["citations"], "as_of": hit["as_of"]})
            yield _sse("done", {})
            return

    plan = planner.plan(CONFIG, question)
    per_request_cfg, intent, filters = plan["cfg"], plan["intent"], plan["filters"]

    context, citations = None, None
    if filters.get("citation"):
        fetched = planner.citation_fetch(per_request_cfg, filters["citation"])
        if fetched is not None:
            context, citations = fetched
    if context is None:
        # D8a edge case: filtered fetch returned nothing (or no filter) ->
        # fall back to the intent's normal semantic mode.
        context, citations = retrieve(per_request_cfg, question)

    as_of = citations[0].get("as_of") if citations else None
    if not citations:
        # Verifier is not reached on a legitimately-empty context — the
        # "No matching regulatory text" branch handles this first (unchanged
        # edge-case posture from iter-2).
        yield _sse("token", {"t": "No matching regulatory text was found in the indexed corpus."})
        yield _sse("citations", {"citations": citations, "as_of": as_of})
        yield _sse("done", {})
        return

    if CONFIG.generate and models.available():
        answer_parts = []
        for chunk in models.stream(question, context, per_request_cfg.max_new_tokens):
            answer_parts.append(chunk)
            yield _sse("token", {"t": chunk})
        answer = "".join(answer_parts)

        cache_eligible = True
        if CONFIG.verify_answers:
            result = verify_answer(answer, context, intent, topic=intent)
            yield _sse("verification", {
                "grounded": result["grounded"],
                "declined": result["declined"],
                "unsupported_claims": result["unsupported_claims"],
                "missing_elements": result["missing_elements"],
                "note": result["note"],
            })
            # D10: only a grounded, non-declined answer is cache-eligible.
            cache_eligible = result["grounded"] and not result["declined"]

        if CONFIG.answer_cache and cache_eligible:
            cache.put(CONFIG, question, answer, citations, as_of)
    else:
        yield _sse("token", {"t": "Most relevant provision:\n\n" + context.split("\n\n")[0]})

    yield _sse("citations", {"citations": citations, "as_of": as_of})
    yield _sse("done", {})


@app.post("/chat_stream")
def chat_stream():
    question = (request.get_json(force=True) or {}).get("question", "").strip()
    if not question:
        return {"error": "empty question"}, 400

    def gen():
        # Tier-1 FAQ fast-path (D9 step 1): runs before Tier-2, independent
        # of ORCHESTRATION. A hit short-circuits retrieval and generation
        # entirely.
        if CONFIG.faq_cache:
            framed = planner.frame_query_hints(question)
            hit = faq_matcher.match(CONFIG, framed["framed_query"], framed["hints"])
            if hit is not None:
                yield _sse("token", {"t": hit["answer"]})
                yield _sse("citations", {"citations": hit["citations"], "as_of": hit["as_of"], "source_tier": "faq"})
                yield _sse("done", {})
                return

        if CONFIG.orchestration:
            yield from _gen_orchestrated_path(question)
        else:
            yield from _gen_iter2_path(question)

    return Response(gen(), mimetype="text/event-stream")
