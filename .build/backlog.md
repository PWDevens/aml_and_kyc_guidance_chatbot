# Backlog — full-build loop

Source plan: `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`docs/ETL_AND_TRIGGERS.md`, `docs/AGENT_ORCHESTRATION.md`, `docs/FAQ_CACHE.md`,
`docs/UIUX_COGNITUS.md`. Iterations below are ROADMAP phases 1–5 (Phase 0 is
already built and verified — see `.pipeline/STATUS.md` iterations 1–2 and
`.pipeline/HANDOFF.md`). Phase 6 (stretch) is explicitly out of scope for this run.

Kickoff decisions (user, 2026-07-02): build through Phase 5 (v1.0 hardening);
ponytail intensity **full**, but simplifications are recorded in `changes.md` /
the tech-debt ledger only — **no `ponytail:` comments or the word "ponytail" in
code or commit messages**.

## Iteration 1 — Finish Phase 1: multi-mode retrieval + corpus breadth
**Tag concept:** `v0.2-multimode` (not actually git-tagged — full-build never tags)
**Goal:** hybrid retrieval proven or correctly rejected on a harder eval set, corpus
broadened beyond eCFR 1010/1020, citations still resolve correctly.
**Acceptance criteria (from ROADMAP Phase 1 + PRD §5):**
- Gold eval set expanded to ~20–30 items (clause-number lookups, dollar thresholds,
  "what changed"-shaped questions), per `.pipeline/STATUS.md` §"Next loop".
- FedReg (FinCEN) + advisory static loaders add corpus breadth beyond 31 CFR 1010/1020.
- Section-aware chunking tuned to eCFR XML structure (ARCHITECTURE §7).
- `RAG_MODE` naive vs hybrid re-measured on the bigger set; default mode decided by
  the numbers (not assumed) and documented.
- Cross-encoder reranker added **only if** it demonstrably fixes hybrid's prior
  ranking regression (see `.pipeline/STATUS.md` iteration 2) — not added speculatively.
- Exact-match answer cache (`src/rag/cache.py`, SQLite) — named in ARCHITECTURE §2
  component map as already "(reused)" from fedacq but not yet present in this repo;
  needed before Phase 3 layers the FAQ cache on top of it.
**Out of scope:** trigger-based ETL (Phase 2), orchestration/FAQ cache (Phase 3),
Cognitus UI (Phase 4), graph/LightRAG mode (not required by Phase 1 exit criteria
in `.pipeline/HANDOFF.md` — defer unless PM finds it's cheap; do not block on it).

## Iteration 2 — Phase 2: trigger-based ETL
**Goal:** the corpus updates itself incrementally when FinCEN/eCFR publish changes,
with a provenance ledger, per `docs/ETL_AND_TRIGGERS.md`.
**Acceptance criteria (ROADMAP Phase 2 + ETL doc §7):**
- `src/etl/watchers/` (fedreg.py, ecfr.py) poll from a stored watermark.
- Rules engine `src/etl/rules.py` implements R1–R4 (final rule, proposed rule,
  notice/advisory, eCFR structural diff) per ETL doc §2.
- Upsert-by-citation load (delete+add, no stale duplicates); watermark advances
  only on success (R8 semantics — atomic, retriable).
- `data/etl_state.db`: watermarks + provenance ledger (`ETL_AND_TRIGGERS.md` §4).
- `GET /corpus_status` reports `as_of`, last ETL run, counts by source.
- A simulated (recorded-fixture) FinCEN change is detected and ingested
  incrementally; re-running the same batch is idempotent.
**Out of scope:** R5/R6 (FAQ/graph sync — Phase 3), R7 (FFIEC — Phase 3), the
scheduled-CI auto-PR pattern (needs a real remote; document as a manual follow-up
instead of building CI automation for a repo with no remote yet).

## Iteration 3 — Phase 3: orchestration + FAQ cache
**Goal:** heterogeneous question shapes get routed appropriately, answers are
verified against retrieved text, and common questions get a sub-second semantic
cache hit — `docs/AGENT_ORCHESTRATION.md` + `docs/FAQ_CACHE.md`.
**Acceptance criteria:**
- Planner + skills: `query_framer`, `intent_classifier`, `retrieval_router`,
  `answer_verifier`, `citation_formatter`; `change_resolver` if `change` intent is
  in scope for this iteration (else deferred with a stated reason).
- Routing matrix (AGENT_ORCHESTRATION §4) wired to the existing retrieval factory;
  `ORCHESTRATION=false` still collapses to the single-path baseline.
- `answer_verifier` declines/labels ungrounded claims rather than hallucinating.
- Semantic FAQ cache (Tier 1, `data/faq.db`) with `FAQ_SIM_THRESHOLD` matching +
  topic-key cross-check; staleness tied to ETL rule R5 (suppress-then-reverify).
- `scripts/seed_faq.py` + a committed `data/faq_seed.yaml` (~30–50 entries per
  FAQ_CACHE §8, or fewer with the gap stated honestly if curation time doesn't
  allow the full target — do not pad with low-quality entries to hit a number).
- Orchestration-on vs orchestration-off compared on the eval set (AGENT_ORCHESTRATION §7).
**Out of scope:** FFIEC ingest (R7) and graph re-sync (R6) — pull in only if
Iteration 1 already built the graph loader/mode; otherwise note as deferred.

## Iteration 4 — Phase 4: Cognitus UI/UX
**Goal:** the front end reads as a credible, branded, accessible product —
`docs/UIUX_COGNITUS.md`.
**Acceptance criteria:**
- `cognitus.css`/`cognitus.js` tokens applied to `src/app/static/`; hero, chat/ask
  view, citation panel (right rail desktop / collapsible mobile), corpus-status
  strip, persistent disclaimer footer, verifier-decline state.
- WCAG AA contrast, full keyboard operability, semantic landmarks (UIUX §5).
- "What changed" timeline view if `change_resolver` (Iteration 3) shipped;
  otherwise note as deferred with reason.
**Out of scope:** backend/retrieval changes; new orchestration skills.

## Iteration 5 — Phase 5: hardening & release
**Goal:** the project is CI-tested, documented, and reproducible end to end —
ROADMAP Phase 5 + Definition of done (§6).
**Acceptance criteria:**
- Test suite covers loaders/parsers, retrieval factory dispatch, RRF, ETL rules,
  each orchestration skill, FAQ matcher (ROADMAP §4).
- `requirements.lock` (or pinned `requirements.txt`) for reproducibility.
- Dockerfile + docs for a one-command run.
- README updated with eval results and a demo walkthrough.
- Clean-machine reproducibility check (documented steps; actually re-run if
  feasible in this environment).
**Out of scope:** any actual `git push`/deploy/publish/CI-provider account setup —
those are irreversible or require credentials outside this loop's authority;
document them as manual follow-ups in `progress.md` instead of performing them.
GitHub Actions **workflow files** may be authored (they're just repo content) but
never triggered, pushed, or connected to a real account by this loop.
