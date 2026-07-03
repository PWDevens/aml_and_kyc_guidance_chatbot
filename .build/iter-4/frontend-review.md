# Iteration 4 — UI/UX SME Review

Reviewed against `.build/iter-4/spec.md` (AC-1..AC-12, D1-D6), `.build/iter-4/changes.md`,
`.build/iter-4/test-results.md`, and the actual served files: `src/app/static/index.html`,
`cognitus.css`, `cognitus.js`, `app.js`, plus `src/app/api.py` for the static-route context
(read-only; no backend logic touched).

Verified live in a real browser (Flask dev server on port 8123, real corpus): landing page,
a full ask → stream → citations round trip, and the synthetic decline hook
(`window.CognitusRender.verification(...)`). `changes.md`'s "orchestrator fix" claim (three
real `send_from_directory` routes replacing an inlining workaround) checked against the actual
current files, not just the prose — confirmed accurate: `GET /cognitus.css`, `GET /cognitus.js`,
`GET /app.js` all exist in `api.py` and `index.html` links them via real `<link>`/`<script src>`
tags, no inlined duplication remains.

## What I reviewed

- **Accessibility**: semantics, labeling, keyboard operability/focus, contrast math
  (independently recomputed, not trusted from changes.md), ARIA correctness — in particular the
  `aria-live="polite"` politeness question the role brief flagged.
- **Usability**: affordances, loading/empty/error/decline states, forgiving inputs.
- **Consistency**: Cognitus tokens, one-accent-per-view, hairline-only decoration.
- **Responsiveness**: the 900px / 640px breakpoint behavior against AC-11.

## Fixes applied (minimal, in scope)

1. **`src/app/static/index.html`, `src/app/static/app.js` — fixed a real ARIA anti-pattern.**
   `#answer` had `aria-live="polite"` while being mutated on *every* SSE `token` event
   (potentially hundreds of times per answer via `appendToken()`). With no `aria-atomic`/
   `aria-relevant` narrowing, most screen readers announce on every mutation to a polite live
   region — this reads as a torrent of tiny, disorienting announcements during token-by-token
   streaming, exactly the anti-pattern the role brief asked me to form a judgment on. Verdict:
   genuinely wrong, not defensible as "polite enough." Fix: removed `aria-live` from `#answer`
   itself; added a new visually-hidden `<span id="answer-status" role="status"
   aria-live="polite">` that's updated **once** — either "Answer ready." at `done`, or the
   decline message at verification-declined — so screen reader users still get exactly one
   completion announcement instead of a stream of fragment announcements. Verified live: after
   a real ask → stream → done round trip, `#answer` has no `aria-live` attribute and
   `#answer-status` contains "Answer ready." exactly once; the synthetic decline hook confirmed
   the decline path announces its specific message instead (guarded so `done` doesn't overwrite
   it with the generic message). Token-append logic (`appendToken`, caret handling) was not
   touched — pure a11y-node change.
2. **`src/app/static/cognitus.css` — added the missing `.visually-hidden` utility class.**
   `index.html`'s ask-box `<label for="q" class="visually-hidden">` referenced a class that was
   never defined anywhere in the CSS, so the label was rendering fully visible and unstyled
   above the textarea (redundant with the placeholder text) instead of the evidently intended
   accessible-but-visually-hidden pattern. Added the standard clip-based `.visually-hidden`
   rule. Verified live: `getComputedStyle(label).position === "absolute"` and the label is
   correctly present in the accessibility tree (`preview_snapshot` shows the textbox's
   accessible name as "Your question") while no longer occupying visual layout.
3. **`src/app/static/index.html` — associated the ask-hint with the input.** Added
   `aria-describedby="ask-hint"` on `<textarea id="q">`. The hint (`role="status"`) was already
   announced reactively via its own live region, but wasn't reachable as the field's accessible
   description for a screen-reader user reviewing the field on demand (e.g. tabbing back to it).
   One attribute, zero risk, standard pattern — bundled with fix #2 since both are label-adjacent
   input wiring.

All three fixes together: 2 files' worth of small diffs, no new dependency, no layout/visual
change to sighted users (confirmed via live DOM/computed-style inspection, not just reading the
CSS), full iter-4 test suite re-run green (`pytest tests/test_iter4_static_and_source_tier.py -q`
→ 16 passed).

## Contrast — verified independently, not trusted from changes.md

Recomputed WCAG relative-luminance contrast myself (not just re-stated the claimed numbers):

| Pair | Ratio | AA (normal text, ≥4.5:1) |
|---|---|---|
| Jefferson Blue `#232D4B` on white | 13.56:1 | Pass, by a wide margin |
| Bronze `#7B6D45` on white | 5.10:1 | Pass |
| Bronze `#7B6D45` on `--bg-alt` `#f7f8fa` (decline-region background) | 4.80:1 | Pass |
| ink-muted `#5b6472` on white (subheads, meta text) | 5.98:1 | Pass |
| Cyan `#34CAFF` on white | 1.90:1 | Fails AA outright — confirms cyan is correctly **never** used for text |

Matches `changes.md`'s claimed 13.56:1 / 5.10:1 exactly. Grepped `cognitus.css` for every
`var(--cyan)` usage: exactly 3 call sites (focus-ring outline, streaming caret background,
loading-sweep background) — all non-text decorative accents, never body copy, never the sole
signal of a status (decline uses text + shape + a left border, not color alone; FAQ marker uses
the literal word "from FAQ", not a color chip). `box-shadow`/`gradient` grep: zero property
usages (one mention inside a code comment only). One-accent-per-view holds: cyan's three uses
are mutually exclusive in time/place (focus ring only on the focused element; caret only while
streaming, removed at `done`; loading sweep only before the first token, then replaced by the
caret) — never two cyan accents visible simultaneously in one view.

## Responsive — read the actual media queries, not just the visual description

`cognitus.css` has one layout-driving breakpoint: `@media (min-width: 900px)` switches
`.answer-wrap` from `grid-template-columns: 1fr` (stacked) to a
`minmax(0,2fr) minmax(0,1fr)` two-column right rail. Below 900px — which covers the spec's
"≤640px" case as a subset — the citation panel is already stacked below the answer, satisfying
AC-11 ("collapses to below the answer... at ≤640px", a superset relationship, not a second
breakpoint that needed its own rule). The `@media (max-width: 640px)` block only adjusts padding
(hero/strip/main/header/footer), which is consistent with the spec's intent. `html, body { max
-width: 100%; overflow-x: hidden; }` plus `overflow-wrap`/`word-break` on answer text and
citation links prevents horizontal scroll for long URLs/citations. Verified live at 375px in a
prior session per changes.md (`scrollWidth === innerWidth`); re-confirmed the grid rule reads
correctly in this pass by reading the CSS directly rather than re-trusting the claim.

## Other things checked, no defect found

- Semantic landmarks: exactly one `<header>`, `<main>`, `<footer>`, one `<h1>`, `<aside>` for
  citations — confirmed via live `preview_snapshot` (`banner`/`main`/`complementary`/
  `contentinfo` roles present, one heading per section) as well as by reading the markup.
- No ARIA bolted onto `<div>`s: grepped for `onclick=`, `role="button"` on a `div`, stray
  `tabindex` — none found. All interactive elements are real `<button>`/`<textarea>`/`<a>`.
  Matches this role's "native platform features over libraries" preference.
- Keyboard: `<textarea>`, submit `<button>`, citation `<a>` are unmodified native elements
  (default tab order, default focusability) — no keyboard trap possible from custom tabindex
  wrangling, because there isn't any.
- Focus rings: `:focus-visible` rule applies a cyan outline (2px, offset) to every focusable
  element category (`a`, `button`, `textarea`, `[tabindex]`) — a real outline shape, not a
  color-only signal, and cyan-as-focus-ring doesn't conflict with "cyan never for body text"
  since a focus ring isn't text.
- Empty/error states: corpus-status 503/`indexed==0` → calm "corpus not built / status
  unavailable" (no stack trace); empty-citations → neutral note + "as of: n/a" (never "null");
  all-empty-string citation fields → omits blank lines, no dead `<a href="">`, no "undefined";
  empty-question 400 → quiet inline hint, not parsed as SSE. All four states exist in `app.js`
  exactly as the spec's edge cases require — confirmed by reading the render functions, not just
  the claim.
- Decline wording matches AC-9 verbatim: *"I can't ground an answer for that — try rephrasing or
  narrowing to a specific rule."* — confirmed by direct string comparison against `app.js`.
- Intent chip (D2): `display:none` by default, only shown if a future event carries `data.intent`
  — confirmed present but correctly inert; does not affect layout when absent.
- FAQ marker (AC-10): quiet bordered text badge ("from FAQ"), not a colored banner — text-based
  signal, not color-only.
- `source_tier` scoping (D4): re-confirmed by direct read of `api.py` line 198 — only the FAQ
  fast-path branch carries the new key; the other two citation-emitting branches are untouched.

## Blocking defects — none found requiring FOR SENIOR-PM escalation

No blocking accessibility or UX defect remains after the three fixes above. Everything found
was fixable minimally and was fixed in place.

## Deferred as deliberate tech-debt (ceiling noted, no informal labels used)

1. **`title` attribute on `#health-dot` is not reliably accessible** (not exposed by all screen
   readers, not reachable without a pointer). Low priority: the element is `aria-hidden="true"`
   and explicitly optional/supplementary per spec ("quiet health indicator... never block the
   UI"), carries no information not available elsewhere, and the spec doesn't require it be
   AT-exposed at all. Ceiling: revisit only if a future iteration promotes system health to a
   user-facing, non-decorative status (at which point it should become a real labeled element,
   not a tooltip).
2. **No visible on-page description linking the "eyebrow" section labels' styling intent to a
   documented pattern** — purely a maintainability note, not a user-facing defect: the eyebrow
   kicker style (`.eyebrow`) is applied both to real section `<h2>` elements and to a decorative
   `<span class="eyebrow">` inside the hero and decline region. This is fine today (correct
   semantics either way — the hero's eyebrow is decorative text, not a heading, and the decline
   region's "Not grounded" label is a `<span>`, appropriately not a heading since it's not
   introducing a document section). Ceiling: if a future iteration adds more non-heading eyebrow
   uses, consider a `.eyebrow` vs `.eyebrow-heading` naming split so heading-ness stays
   grep-able at a glance; not worth doing for the current two-instance count.

Both items are cosmetic/maintainability, not accessibility or usability defects, and neither
blocks sign-off.
