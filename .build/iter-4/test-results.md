# Iteration 4 — Test & Debug Report

RESULT: **PASS**

Suite: `py -3.12 -m pytest tests/ -q` → **139 passed, 0 failed** (123 pre-existing + 16 new in
`tests/test_iter4_static_and_source_tier.py`), run time ~164s. Re-run twice for confirmation,
same result both times. No self-heal needed — 0 of 2 fix-attempt budget used, because no test
failed.

---

## What was verified before writing tests

Read `.build/iter-4/spec.md` and `.build/iter-4/changes.md` in full, then independently
verified (not just trusted) the state changes.md's "Post-fix" section describes:

- **`src/app/api.py`**: confirmed three new routes exist — `GET /cognitus.css`,
  `GET /cognitus.js`, `GET /app.js` — each a one-line `send_from_directory(STATIC, ...)`
  mirroring the existing `GET /` route. Confirmed the FAQ fast-path in `chat_stream.gen()`
  yields `citations` with `"source_tier": "faq"` added, and that `_gen_iter2_path` /
  `_gen_orchestrated_path` are otherwise unchanged (both still yield the two-key
  `{citations, as_of}` dict with no `source_tier`).
- **`src/app/static/index.html`**: confirmed it links `cognitus.css`/`cognitus.js`/`app.js` via
  real `<link rel="stylesheet">` / `<script src>` tags (no inlined `<style>`/duplicated script
  blocks remain) — matches changes.md's claim that the orchestrator's fix replaced the
  senior-dev's inlining workaround.
- **`cognitus.css`, `cognitus.js`, `app.js`**: spot-read; content lines up with changes.md's
  description (design tokens as CSS custom properties, `source_tier`/verification handling in
  `app.js`, animated-counter/scroll-reveal-only in `cognitus.js`).
- Ran a live `Flask.test_client()` probe (not assumed) to check actual `Content-Type` headers
  Werkzeug sends and actual path-traversal behavior before writing assertions — see below.

No discrepancies found between changes.md's description and the code as it actually stands.

---

## New test coverage added

File: `tests/test_iter4_static_and_source_tier.py` (16 tests, all passing).

### 1. New static routes (`/cognitus.css`, `/cognitus.js`, `/app.js`)
- 200 + non-empty body + content-type check for each route. Verified actual Werkzeug-inferred
  content-types via a live probe rather than assuming: `text/css; charset=utf-8` for
  `cognitus.css`, `application/javascript; charset=utf-8` for both JS files. Tests assert
  loosely (`"css" in content-type`, `"javascript"/"ecmascript" in content-type`) so the test
  doesn't break on an immaterial charset/formatting change.
- Byte-for-byte comparison of each route's response body against the corresponding file on
  disk, confirming the routes serve the real, current static files (not some stale/duplicated
  copy).
- Path-traversal rejection for each of the three new routes, using both a raw `/../` segment
  and a URL-encoded `%2F` variant. Verified live first: all attempts against the real app
  returned 404 (Werkzeug's routing normalizes `/cognitus.css/../requirements.txt`-style
  attempts before `send_from_directory` even runs, and `send_from_directory` itself also
  guards). Tests assert `status_code in (400, 404)` to tolerate either valid rejection code
  rather than over-fitting to one.

### 2. `source_tier` field (D4)
- Did **not** duplicate `tests/test_chat_stream_orchestration.py::test_faq_tier1_hit_skips_retrieval_and_generation_entirely`,
  which already asserts the FAQ path's `citations` event equals
  `{"citations": ..., "as_of": ..., "source_tier": "faq"}` exactly (verified by reading that
  file — it was updated for this iteration per changes.md).
- Added the missing negative coverage: four tests asserting `"source_tier" not in cites` (key
  genuinely absent, not `None`) —
  - `_gen_iter2_path`, fresh-generation branch
  - `_gen_iter2_path`, Tier-2 cache-hit-replay branch
  - `_gen_orchestrated_path`, generated-answer branch
  - `_gen_orchestrated_path`, no-citations early-return branch
  This closes the gap the spec explicitly called out ("neither `_gen_iter2_path` nor
  `_gen_orchestrated_path`'s `citations` event includes a `source_tier` key at all").

### 3. HTML structure (AC-1)
- Regex/count-based check (no new parser dependency, per the task's own guidance that this is
  acceptable) confirming `index.html` contains exactly one `<h1>`, `<header>`, `<main>`,
  `<footer>`, and `<aside>`. Also asserts the `<aside>` is specifically the citation panel
  (its opening tag or immediate content mentions "citation"), and that `cognitus.css`/
  `cognitus.js`/`app.js` are referenced via real `<link>`/`<script src>` tags with no leftover
  `<style>` block — a regression guard against the exact duplication problem changes.md
  documents was found and fixed.

---

## AC-by-AC mapping

| AC | Description | Verification in this pass |
|----|--------------|---------------------------|
| AC-1 | Semantic landmarks, single `<h1>` | **Automated** (new tests: exactly-one counts for h1/header/main/footer/aside, aside is the citation panel). |
| AC-2 | Cognitus tokens via `cognitus.css` | Not re-verified pixel-by-pixel here (out of scope for backend/behavior tests); `cognitus.css` presence and being the real served file is automated (new static-route tests). Palette/computed-style correctness was **manually verified** by the senior-dev/orchestrator per changes.md (contrast ratios, `:root` custom properties). Acceptable for this iteration — visual token application isn't practically unit-testable without a headless-browser/visual-regression harness, which is out of scope per spec ("no build step," no new dependency). |
| AC-3 | One accent per view | **Manual only** (changes.md). Not automatable without visual regression tooling; reasonable gap for this iteration. |
| AC-4 | Hero split renders | **Manual only** (changes.md, live browser). Static-file/markup presence indirectly covered by the HTML-structure tests (hero section exists in the file the routes serve), but the visual rendering itself is not automated. |
| AC-5 | Corpus-status strip, live `/corpus_status` data | Backend contract (`GET /corpus_status` shape, 503/`indexed==0` handling) is unchanged this iteration and already covered by `tests/test_corpus_status_endpoint.py` (pre-existing, still passing). Strip *rendering* from that data is front-end-only and was **manually verified** live (changes.md). Acceptable — no backend change here to add coverage for. |
| AC-6 | Streaming still works, cyan caret restyled | SSE event order/content is unchanged and covered by many pre-existing tests (`test_chat_stream_cache.py`, `test_chat_stream_orchestration.py`) plus this pass's new `source_tier`-absence tests, which incidentally re-confirm token/citations/done ordering. The caret itself is pure CSS/JS and was **manually verified** (changes.md). |
| AC-7 | Citation panel cards, badges, real `<a href>` | Backend citation payload shape is unchanged and covered by existing tests; the `<aside>` citation-panel presence is now automated (new HTML-structure test). Card rendering/badge-mapping/link attributes are front-end DOM behavior, **manually verified** (changes.md, `preview_eval`/`preview_network`). |
| AC-8 | `as_of` stamp on every answer | Backend `as_of` values are unchanged/covered by existing retrieval and cache tests. Stamp *rendering* (including the "n/a" fallback) is front-end, **manually verified** (changes.md edge-case 3 check). |
| AC-9 | Verifier-decline state | Backend `verification` event shape/ordering is **automated** (pre-existing `test_orchestrated_path_emits_verification_event_before_citations`, `test_orchestrated_path_declined_answer_not_cached`, `test_orchestrated_path_off_skips_verification_event`). The decline UI rendering itself (exact wording, calm styling) is front-end and was **manually verified** via a synthetic `CognitusRender.verification()` call in a live browser (changes.md) — this matches the spec's own "Testing hooks" section, which explicitly sanctions synthetic-event verification since `ORCHESTRATION=false` by default rarely produces this live. |
| AC-10 | FAQ-hit marker (`source_tier`) | **Automated**, both directions, in this pass: FAQ path carries `source_tier:"faq"` (pre-existing test, confirmed still correct), both non-FAQ paths' four branches genuinely omit the key (four new tests). This is the strongest AC in this report — full positive + negative backend coverage. Marker *rendering* in the DOM was manually verified (changes.md, live seeded-FAQ question + synthetic event). |
| AC-11 | Responsive breakpoint, no horizontal scroll | Pure CSS/viewport behavior, **manual only** (changes.md: computed `grid-template-columns` + `scrollWidth` checks at 375/1280px). Not automatable without a headless-browser harness; reasonable gap. |
| AC-12 | WCAG AA contrast, keyboard operability, no color-only signaling | **Manual only** (changes.md: computed contrast ratios 13.56:1 and 5.10:1, DOM focus-order checks). Reasonable gap for the same reason as AC-3/AC-11. |

### Is manual-only verification acceptable for the visual/interaction ACs (AC-2, 3, 4, 5 render, 6 caret, 7 render, 8 render, 9 render, 11, 12)?

**Yes, acceptable for this iteration**, with one caveat flagged below. Reasoning:
- The spec's own "Definition of done" and "Testing hooks" sections anticipate this split: they
  ask for **README screenshots** and a **live-browser walkthrough**, not a visual-regression
  test suite, and explicitly say new backend dependencies (a headless-browser/pixel-diff
  tool) are out of scope for this dependency-light, no-build-step project.
  Adding one now would be scope creep beyond this task's brief (add durable *backend* coverage
  a future refactor could rely on).
- The backend contract underlying every one of these ACs (SSE event shapes, `/corpus_status`
  shape, static-file serving) **is** now automated, which is exactly the part a future backend
  refactor is likely to accidentally break. The part that's manual-only (CSS/DOM rendering) is
  also the part least likely to regress silently from a *backend* change, since it's plain
  static files with no build step.
- **Caveat / gap worth flagging to the senior-PM gate**: the three required README screenshots
  (landing, answer+citations desktop/mobile, verifier-decline) are still **not present as image
  files** per changes.md's own admission ("preview_screenshot... timed out," "this is the one
  Definition-of-Done item not fully met"). That's a real, acknowledged DoD gap — not a test
  failure, but the senior-PM gate should decide whether to accept the tooling-limitation
  explanation or require the screenshots be captured before sign-off, since the spec lists them
  under "Definition of done."

---

## Fixes made

None. No test failed on first run; the 2-attempt self-heal budget was not needed.

---

## Anything the senior-PM gate should scrutinize

1. **Screenshots gap (see above)** — real DoD item, honestly disclosed, not silently dropped.
   Worth a explicit accept/reject decision rather than passive carry-forward.
2. **Path-traversal test strictness**: the new traversal tests accept either 400 or 404 as a
   pass condition (both are valid "rejected" outcomes; Werkzeug's routing/`send_from_directory`
   returns 404 in this Flask/Werkzeug version for all attempts tried). If a future Werkzeug
   upgrade changes this to a 400, the tests still pass — this is intentional (testing the
   *outcome* — "not served" — not the specific status code), but worth knowing it isn't pinned
   to exactly 404.
3. **`test_real_generation_end_to_end_grounded_answer_is_cached`** (pre-existing, in
   `test_chat_stream_cache.py`) exercises the real ONNX generation stack against the real
   corpus and is the dominant contributor to the ~164s suite runtime. Unrelated to this
   iteration's changes but noted since it's the long pole in every future `pytest tests/ -q`
   run.
4. **No regression in byte-identical-collapse guarantee**: this pass's negative `source_tier`
   tests, combined with the pre-existing AC-2/D9 collapse tests
   (`test_collapse_generated_answer_matches_iter2_behavior` etc., all still green), together
   give strong confidence the FAQ-only additive change did not leak into the other two paths.
5. **Scope discipline confirmed**: no source files outside `tests/` were modified in this pass.
   `src/app/api.py`, `index.html`, `cognitus.css`, `cognitus.js`, `app.js` are exactly as
   changes.md's "Post-fix" section describes — verified by direct read, not assumed.
