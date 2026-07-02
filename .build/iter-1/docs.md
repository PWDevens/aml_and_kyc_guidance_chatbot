# Iteration 1 — Documentation summary

Spec: [`.build/iter-1/spec.md`](spec.md) | Implementation: [`.build/iter-1/changes.md`](changes.md)

---

## Docs touched

### 1. **`README.md`** — Status section

**Change:** Updated stale status line from "Planning / pre-build. No application
code is committed yet" to reflect reality ("Phase 1 in progress. Phases 0–1 are
implemented...").

**Why:** The status was misleading — the repo now contains working Phase 0 + Phase 1
Iteration 1 code (loader, indexer, retrieval, generation, cache, tests, 403-chunk
built index). The README's "Specification" emphasis is still correct (the docs/
planning files describe the *target* system); the status now correctly notes which
phases are built vs. still-planned.

**Summary:** Corrected status to reflect Phases 0–1 complete, Phases 2–5 pending.
Linked to the new CHANGELOG.

---

### 2. **`CHANGELOG.md`** — Created

**Content:** 
- Phase 1, Iteration 1 full entry (spec date, results reference, new features,
  configuration changes, measured results, API/internal changes, tests, simplifications).
- Phase 0 reference to `.pipeline/STATUS.md` and `.pipeline/HANDOFF.md`.

**Why:** The project lacked a user-facing changelog. This iteration's decisions
and numbers (naive vs. hybrid measured outcome, reranker added because it fixes
a measured regression, corpus expanded to 403 chunks, etc.) are load-bearing —
users and future maintainers need a place to find them that's not buried in
spec/changes.md files.

**Summary:** Documented all shipping features, configuration, measured results,
API changes, and deferred simplifications in one place. Follows semantic
versioning by phase/iteration concept (no version tags yet, but formatted for
future tagging).

---

## Docs NOT modified

### `docs/ARCHITECTURE.md`
**Reason:** Architecture doc describes the target *system design*, not what's
currently built. Phases 0–1 Iter 1 implement the "Retrieval factory" part of that
design (naive + hybrid modes, now with hybrid_rerank + reranker available). The
doc's high-level architecture (orchestrator, retrieval, generation, FAQ cache,
Cognitus UI) is still the target; Phases 2–5 will fill in the blanks. Updating
it to say "Phase 1 is done" would risk making the *planned* Phases 2–5 sound like
they're built already — exactly the mistake the README *had*. **Left as-is to keep
the plan / reality boundary clear.**

### `docs/ROADMAP.md`, `docs/PRD.md`, etc.
**Reason:** These describe the target product, not what shipped. No changes to
them are warranted by one iteration. If Iteration 1 discovered a *change* to the
plan (e.g., "we can't do X" or "the path to X is different"), ROADMAP gets an
update — but Iteration 1's success confirms the plan, not changes it.

### `docs/ETL_AND_TRIGGERS.md`, `docs/AGENT_ORCHESTRATION.md`, `docs/FAQ_CACHE.md`, `docs/UIUX_COGNITUS.md`
**Reason:** These are Phase 2–5 scopes (not built). Iter 1 does not touch them.

---

## Environment note

The `.pipeline/HANDOFF.md` machine-migration note and `requirements.txt` version
comment on `onnxruntime-genai` were **already handled** by the orchestrator before
this iteration. See `.build/progress.md` "Manual follow-ups / onnxruntime-genai
version drift — FIXED..." The version fix unblocked live generation, which this
iteration's cache wiring now exercises in the real test (`test_real_generation_end_to_end_grounded_answer_is_cached`).

---

## Summary

- **2 files touched:** README.md status section (corrected), CHANGELOG.md (created).
- **Docs not modified:** planning docs (PRD/ARCHITECTURE/ROADMAP/ETL/AGENT/FAQ/UI)
  remain the target/vision; Iter 1 success confirms the plan, not changes it.
- **Result:** Users and maintainers can now see Phase 1's shipped features, measured
  decisions (naive vs. hybrid outcome, reranker justification), and what's deferred
  in one canonical place (CHANGELOG), while the planning docs remain the forward
  roadmap and not conflated with a "pre-build status" that no longer applies.
