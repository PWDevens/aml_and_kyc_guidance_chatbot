# Iteration 2 — Documentation updates

**Role:** Documentation SME | **Date:** 2026-07-02

---

## Summary

Updated existing project documentation to reflect Phase 2 completion. Two files modified:

### 1. README.md — Status section
Updated the Phase/Iteration progress line to reflect completion of Phases 0–2 and the trigger-based ETL delivery. Changed from "Phase 1 in progress" to "Phase 1 complete; Phase 2 complete" with a bullet summary of each phase's scope.

**Reason:** README is the first entry point; it must accurately reflect shipped work.

### 2. CHANGELOG.md — New Phase 2 entry
Added a comprehensive Phase 2, Iteration 1 entry at the top of the changelog, covering:
- New features (ETL pipeline, watchers, rules engine R1–R4, upsert-by-citation, provenance ledger, `/corpus_status` extension)
- Carried-forward tech-debt resolved (CFR-reference filtering of FedReg docs, now in R1–R3)
- Configuration changes (4 new env vars: `ETL_STATE_PATH`, `ETL_SCHEDULE`, `ETL_FEDREG_SINCE`, `ETL_ECFR_SINCE`)
- Measured results (live run table: 3 passes, 475 final chunks, 197 provenance rows, rule distribution)
- API & internal changes (new `src/etl/` package, extensions to `builder`, `loaders`, `api`)
- Edge cases and design notes (eCFR removed sections, R1 scheduling marker, watermark idempotency, R8 mid-batch atomicity)
- Tests summary (36 total: 19 pre-existing + 17 new)
- Simplifications/deferred (CI auto-PR, container loop, separate collections, R4b)

**Reason:** CHANGELOG documents "what actually shipped" per iteration; it is the versioned handoff artifact.

---

## Files NOT modified

- **`docs/ETL_AND_TRIGGERS.md`** — Phase 2 spec documents the design; CHANGELOG captures the implementation. Re-documenting the same material in a third place would duplicate what the code and spec already say clearly (per the role definition: "no duplicating what the code already says clearly").
- **`docs/ARCHITECTURE.md`** — Existing system architecture section already mentions ETL as Deviation 1; no signature changes to the architecture diagram or control flow this iteration. The offline ETL → corpus upsert path is implicit in the existing diagram ("Trigger-based ETL ... incremental parse → chunk → embed → upsert ChromaDB"). Adding a sub-section on ETL implementation details would bloat this doc without new structural insight.
- **ADR** — No ADR created. No non-obvious architectural tradeoff unresolved; all D1–D7 decisions are documented in `.build/iter-2/spec.md` (the frozen spec), not as a new ADR. The tradeoffs that arose (D1: `/versions` endpoint vs. structure tree diff, D2: section-scoped re-pull, D3: (title, part) intersection ignoring null chapter, D4: incremental upsert vs. full rebuild, etc.) are recorded in the spec and implementation summary, not as a separate architecture decision record.

---

## Why these two docs

- **README:** Updated "Status" line to match reality (phases shipped) so users/reviewers see the current state immediately.
- **CHANGELOG:** The authoritative versioned record of "what shipped this iteration." Every release updates the CHANGELOG with new feature summaries, measured numbers, and config changes. Phases 0–1 entries already follow this pattern; Phase 2 entry follows the same convention.

Both updates mirror the repo's existing documentation style and conventions (exact numbers from live runs, measured counts from the real corpus, plain English with markdown formatting).

---

## Ponytail compliance

No instances of the word "ponytail" in the new CHANGELOG section or the updated README section. Pre-existing `ponytail:` comments in source files (Phase 0–1) were not touched per the project override.
