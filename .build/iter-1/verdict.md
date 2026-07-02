VERDICT: SHIP

# Iteration 1 — Senior-PM gate verdict (RE-GATE after F1 fix)

**Iteration:** N=1 · "Finish Phase 1: multi-mode retrieval + corpus breadth"
**Re-reviewed:** 2026-07-02 · **Reviewer role:** senior PM / eng leader (read-only gate)
**Baseline:** HEAD `4e8d44e` (pre-iteration-1). Nothing committed yet; reviewed from the
working tree via `git diff HEAD` + `git status` + direct file reads.
**Prior verdict:** NEEDS WORK, one required fix (F1). This re-gate verifies only that F1
was applied cleanly and nothing regressed. All 7 acceptance criteria, security, scope,
reliability, and the tech-debt ledger already PASSED in the first pass and are unchanged
(no code logic was touched by the fix) — see git history of this file / progress.md for
that full assessment; it is not re-litigated here.

---

## F1 — "ponytail" removed from all new iteration-1 code — VERIFIED FIXED

The user explicitly forbade the literal word "ponytail" anywhere in new code, docstrings,
or commit messages (spec.md 72–79, DoD 431–432). The three new files that carried it in
their module docstrings are now clean, and the fix was confined to docstring wording.

Verified independently, four ways:

1. **Direct scan of the 3 named files** — `grep -i 'ponytail'` over `src/rag/cache.py`,
   `src/rag/indexing/loaders/fedreg.py`, `tests/test_cache.py` returns **nothing**
   (exit 1). Re-read all three docstrings by hand: the `ponytail:` prefix/sentence is
   gone, replaced by intent-preserving text —
   - `cache.py:7` → `One table, created on first use, no ORM."""`
   - `fedreg.py:9` → `Uses requests (already a dep); abstract-only text — full_text_xml_url
     fetch/parsing is deferred, abstracts are sufficient for corpus breadth."""`
   - `test_cache.py:5` → `Uses a tempfile-backed RagConfig, no fixtures/framework."""`
   The original meaning (single-table/no-ORM; abstract-only deferral; no test framework)
   is fully retained. No code, no logic, no signatures, no behavior changed.

2. **Whole-diff added-line check (the one the task mandated)** —
   `git diff HEAD | grep -i '^+.*ponytail'` returns **nothing** (exit 1). No added line
   anywhere in the diff reintroduces the word.

3. **Whole-diff any-occurrence check** — `git diff HEAD | grep -i 'ponytail'` finds 5
   lines: **4 are pre-existing context lines** (leading space — Phase-0 `ponytail:`
   comments in modified files, which the spec says to leave alone, and they are), and
   **1 is a removal** (leading `-`, the pre-existing `# ponytail:` comment in
   `src/rag/llm/models.py` that the earlier out-of-band onnxruntime-genai fix deleted).
   **Zero added (`+`) occurrences.** The word count in the diff went *down* by one, not up.

4. **Whole-working-tree untracked-file scan** — the 3 fixed files are untracked/new
   (`git diff HEAD` does not show new files, which is why the diff-grep alone can't see
   them — hence the direct scan in (1)). Scanning every untracked file for "ponytail"
   yields **zero hits**. The only remaining occurrence in the tree is
   `tests/test_smoke.py:4`, a **tracked, unmodified Phase-0 file** — correctly untouched,
   out of F1's scope.

## Nothing else broke — VERIFIED

- **Full suite re-run by the reviewer:** `py -3.12 -m pytest tests/ -q` → **19 passed in
  43.92s.** Matches the orchestrator's claim and the first-pass count. Still includes the
  real Phi-4-mini ONNX end-to-end cache test (not a mock). Green honestly.
- **Edits were purely cosmetic:** the fix touched only docstring text in three otherwise
  unchanged new files. No behavior, control flow, SQL, API surface, or public signature
  was altered — consistent with the unchanged test count and the read-through above.

---

## Bottom line

The sole required fix (F1) was applied cleanly, verified four independent ways, and the
suite is still 19/19 green with no behavior change. Every acceptance criterion, plus
security, scope, reliability, and the tech-debt ledger, remains satisfied from the first
pass. Nothing new surfaced. **SHIP.** The loop may advance to Iteration 2 (Phase 2:
trigger-based ETL) per `.build/backlog.md`.
