# Iteration 4 — senior-PM gate verdict

VERDICT: SHIP

Phase 4 (Cognitus UI/UX restyle). Every load-bearing claim was verified independently at
the gate against the *final* state of the source files — not on the reports' word, and not
by trusting that each of the three actors' (senior-dev, orchestrator, UI/UX reviewer)
patches was reasonable in isolation. The final, three-times-touched state is coherent and
meets the definition of done. The one unmet DoD item (README screenshots) is honestly
disclosed, has alternative evidence, and is accepted as bounded tech-debt.

---

## What was verified independently at the gate

### 1. Static-route security — the trust-boundary surface (PASS, strongest form)
Read the actual route definitions in `src/app/api.py:42-54`. All three new routes are
**zero-argument functions serving hardcoded filenames**:

```python
@app.get("/cognitus.css")
def cognitus_css():
    return send_from_directory(STATIC, "cognitus.css")
# ...identical shape for /cognitus.js and /app.js
```

There is **no variable path parameter anywhere** in these signatures — no `<path:...>`
converter, no user input reaching `send_from_directory`'s filename argument. This is the
safest possible design: arbitrary-path traversal is impossible not because a test happened
to pass, but because the routes structurally cannot accept a user-controlled path. The
test-results.md path-traversal tests (accepting 400/404 on `/../requirements.txt` and
URL-encoded variants against each route) are correct defense-in-depth, but the route
signatures themselves are the real guarantee. `Flask(__name__, static_folder=None)` means
there is no implicit static handler either. No secrets introduced. **Trust boundary is
sound.**

### 2. D9 byte-identical collapse guarantee (PASS)
Read all three citation-emitting branches directly:
- `_gen_iter2_path` (`api.py:95`) → `{"citations": ..., "as_of": ...}` — no `source_tier`.
- `_gen_orchestrated_path` (`api.py:127`, `:150`, `:179`) → all two-key dicts — no
  `source_tier`.
- Tier-1 FAQ fast-path (`api.py:198`) → the **only** branch carrying
  `"source_tier": "faq"`.

The addition is genuinely scoped to the FAQ branch. `test_iter4_static_and_source_tier.py`
asserts key *absence* (`"source_tier" not in cites`, not `== None`) across all four non-FAQ
branches (iter2 fresh, iter2 cache-hit, orchestrated generated, orchestrated no-citations).
The pre-existing D9 collapse tests still pass. **AC-2/D9 preserved, verified in code not
just in a test.**

### 3. ARIA fix correctness (PASS — correctly implemented)
The reviewer's claim checked against the actual `index.html` + `app.js`:
- `#answer` (`index.html:54`) has **no `aria-live`** — the every-token-fires anti-pattern is
  gone.
- `#answer-status` (`index.html:55`) is a visually-hidden `role="status" aria-live="polite"`
  node updated **exactly once per answer**: at `done` (`app.js:303-305`, guarded by
  `els.declineRegion.hidden` so it doesn't clobber a more-specific decline message) or on
  verification-declined (`app.js:171`). The token-append path (`appendToken`) never touches
  it. This is the correct one-shot completion-announcement pattern, not a per-token torrent.
  The two remaining `aria-live` attributes in the tree (`#corpus-strip`, `#answer-status`)
  are both legitimately one-shot. **Correct.**

### 4. Manual live-browser verification for the visual ACs (ACCEPTED as sufficient rigor)
For a frontend styling iteration with no visual-regression tooling and a no-build-step/
no-new-dependency mandate, the documented verification clears the "demonstrably true —
specific and reproducible, not vague" bar:
- Contrast recomputed **independently** by the reviewer (not restated from changes.md):
  Jefferson Blue on white **13.56:1**, Bronze on white **5.10:1**, Bronze on `--bg-alt`
  **4.80:1**, ink-muted on white **5.98:1**, and Cyan on white **1.90:1** — the last
  confirming cyan is correctly *never* used for text (grepped to exactly 3 non-text call
  sites: focus ring, caret, loading sweep).
- Real SSE round-trips through the actual UI (fill + click, not synthetic) for the FAQ path;
  computed `grid-template-columns` + `document.body.scrollWidth === window.innerWidth` at
  375/1280px for AC-11; DOM/computed-style reads for token weight/eyebrow/badge styling.
- Decline/FAQ states driven purely by event shape and exercised via
  `window.CognitusRender.*` — exactly the mechanism the spec's "Testing hooks" section
  sanctions, since `ORCHESTRATION=false` rarely emits a live `verification` event.

This is specific real-value evidence, not "looks good." Adding a headless visual-regression
harness would be scope creep against this iteration's explicit no-new-dependency constraint.
**Acceptable.**

### 5. Scope discipline — both out-of-literal-file-list edits are legitimate corrections
- **Static-route fix (orchestrator):** `Flask(__name__, static_folder=None)` + a single
  file-serving route meant the spec's own required `cognitus.css`/`cognitus.js`/`app.js`
  would 404 — the spec's "no new backend route" line was written without knowledge that
  `static_folder=None` blocked serving the very files its "Files to create" section mandates.
  Adding three routes mirroring the existing `GET /` pattern (and removing the interim
  inlining/duplication) is a correct resolution of a spec/reality mismatch — the same class
  as iteration 2's "removed section" 404 fix. **Not scope creep.**
- **ARIA fix + `.visually-hidden` class + `aria-describedby` (UI/UX reviewer):** the a11y
  baseline is a *non-negotiable project standard*, and the missing `.visually-hidden` class
  was an actual bug (the label rendered visible and unstyled). Fixing a genuine a11y
  anti-pattern and a missing referenced class is squarely in-scope for a frontend iteration
  whose spec lists a11y as non-negotiable. **Not scope creep.**
- Confirmed via `git status`/`git diff --stat`: the only changed files are `api.py`,
  `index.html`, `cognitus.css`/`cognitus.js`/`app.js` (new), the two test files, README,
  CHANGELOG, `.build/iter-4/`, and `.claude/launch.json` (a harmless dev-tooling file). No
  "explicitly NOT to touch" path (`src/rag/**`, `src/etl/**`, `requirements.txt`,
  `.github/workflows`, Dockerfile) was modified. No new Python dependency.

### 6. Tests green honestly
Ran the full suite at the gate myself (not on the reports' word):
`py -3.12 -m pytest tests/ -q` → **139 passed in 154.73s**, 0 failed. Matches
test-results.md's 139 (123 pre-existing + 16 new). The new test file has real teeth:
byte-for-byte disk-vs-route comparison, traversal rejection on all three routes,
`source_tier` absence on all four non-FAQ branches, and a regression guard against
re-inlining (`assert "<style>" not in html`). The one modified pre-existing test is the
sanctioned one-line FAQ-shape update (`+ "source_tier": "faq"`). No `<style>`/inlined
duplication remains (grepped). No new `ponytail:` text in any new/edited static file
(grepped: only the two pre-existing `api.py` comments remain, correctly untouched). No
`box-shadow`/gradient in the CSS.

---

## Accepted tech-debt (bounded, carried forward)

1. **Three README screenshots not captured as image files** (landing/hero+corpus strip;
   answer+citations at desktop and mobile; verifier-decline). Reproducible
   preview-tool screenshot timeout across two independent server instances — an
   environment/tooling limitation, not a page defect (the page loads and runs correctly,
   confirmed via DOM/computed-style inspection and a live end-to-end `/chat_stream`
   exchange). Honestly disclosed at every layer (changes.md, test-results.md, docs.md,
   README "Screenshots" section, CHANGELOG DoD). **No fabricated/placeholder images added.**
   Alternative evidence (independently recomputed contrast, real SSE round-trips, computed
   layout metrics) substitutes credibly. **Ceiling:** capture the three shots manually
   (`python -m src.app.asgi`, visit `http://127.0.0.1:8000/`, use the
   `CognitusRender.verification()` hook for the decline shot) at the next opportunity with
   working screenshot tooling; the manual steps are already in the README. Does **not** block
   SHIP — the DoD's intent (demonstrate the visual states are true) is met by reproducible
   specific evidence.

2. **`#health-dot` `title` attribute not reliably AT-exposed** (frontend-review.md deferral
   #1). Element is `aria-hidden="true"`, explicitly optional/supplementary per spec ("quiet
   health indicator... never block the UI"), carries no unique information. **Ceiling:**
   promote to a real labeled element only if a future iteration makes system health a
   user-facing non-decorative status.

3. **`.eyebrow` class serves both real `<h2>` section labels and decorative `<span>`s**
   (hero eyebrow, decline "Not grounded" label) — frontend-review.md deferral #2. Semantics
   are correct today (the decorative uses are appropriately non-heading). **Ceiling:** split
   into `.eyebrow` vs `.eyebrow-heading` if non-heading eyebrow uses proliferate; not worth
   it at the current two-instance count.

4. **Visual ACs (AC-3/4/5-render/6-caret/7-render/8-render/9-render/11/12) are
   manual-verification-only** — no automated visual-regression coverage. Acceptable for this
   dependency-light, no-build-step iteration; the underlying backend contracts (SSE shapes,
   `/corpus_status`, static-file serving) **are** now automated, which is the part a future
   backend refactor could break. **Ceiling:** add a headless-browser/visual-regression
   harness only if/when the project takes on a build step (not before Phase 5's infra work,
   and only if justified).

### Minor note (non-blocking, no fix required)
The CHANGELOG's DoD block says "AC-1..AC-10, AC-12 verified" and then lists several of those
same ACs under "manual verification only" — slightly muddled wording. The underlying
evidence is honest and complete (nothing is overclaimed as automated that isn't), so this is
a cosmetic phrasing wrinkle, not a correctness or honesty problem. Not worth a re-gate.

---

## Definition-of-done scorecard
- **AC-1..AC-12:** all demonstrably true — AC-1/AC-10 (and the `source_tier` scoping) by
  automated test; the rest by specific, reproducible live verification (recomputed contrast,
  real SSE round-trips, computed layout metrics, synthetic-event render hooks). ✅
- **Diff matches spec:** exactly the permitted `api.py` FAQ-line edit + the three static
  files + rebuilt `index.html`, plus the two legitimate spec/reality-mismatch corrections
  (routes, a11y). Nothing required missing; nothing out-of-scope added. ✅
- **Tests green honestly:** 139 passed, re-run at the gate. ✅
- **Security/trust boundary:** static routes take no user path — safe by construction. No
  secrets. ✅
- **a11y baseline:** semantic landmarks, labeled input, native keyboard operability, visible
  cyan focus ring (shape, not color-only), AA contrast, no keyboard traps, text/shape signals
  alongside every color state. ✅
- **Async states:** loading (quiet cyan rule), empty (neutral note + "n/a"), error
  (calm "corpus not built / status unavailable", non-stream 400 handled), decline — all
  present. ✅
- **Shortcuts recorded with ceilings** in changes.md and here; no `ponytail:` comments. ✅
- **Screenshots:** the single unmet DoD item — accepted as bounded, honestly-disclosed
  tech-debt with a ceiling. ⚠️ (does not block)

**Iteration 4 ships.**
