# Iteration 4 — Phase 4: Cognitus UI/UX — FROZEN SPEC

Source: `.build/backlog.md` §"Iteration 4", `docs/UIUX_COGNITUS.md` (primary),
`docs/ARCHITECTURE.md` §8. Senior-dev: assume you read ONLY this file.

This is a **frontend-only** iteration. Restyle the existing lean, dependency-free,
SSE-streaming UI (`src/app/static/index.html`) into the **Cognitus** design system.
Do **not** replace the SSE client architecture — keep plain static HTML/CSS/JS, no
framework, no build step, no external assets/CDN.

---

## Goal

Turn the placeholder `index.html` into a credible, branded, **accessible** Cognitus
product surface: hero + corpus-status strip, chat/answer view with a citation panel,
persistent disclaimer footer, and the verifier-decline / FAQ-hit interaction states —
wired to the **existing, unchanged** backend SSE contract. Exactly one backend edit is
permitted (a minimal FAQ-hit SSE signal); everything else is static files.

---

## Backend contract you are building against (verified, do not change)

These are the **exact current shapes** from `src/app/api.py`, `src/rag/retrieval/factory.py`,
and `src/etl/state.py`. Build the UI to these; do not assume fields the backend does not send.

### `POST /chat_stream` — SSE events (`text/event-stream`)
Each event is `event: <name>\ndata: <json>\n\n`. Events, in the order they can arrive:

- `token` → `{ "t": "<string chunk>" }` — 0..N of these; concatenate in order.
- `verification` → `{ "grounded": bool, "declined": bool, "unsupported_claims": [str], "missing_elements": [str], "note": str }`
  — **0 or 1**. Emitted **only** on the orchestrated path AND when `VERIFY_ANSWERS=true`.
  Arrives **after** all `token`s, **before** `citations`. May be absent on the default
  (non-orchestrated) path. UI MUST treat it as optional.
- `citations` → `{ "citations": [ {citation, heading, url, source, as_of} ], "as_of": "<date|null>" }`
  — exactly 1 near the end. `citations` may be `[]`.
- `done` → `{}` — exactly 1, always last. Stream terminates.

Each citation object shape (from `factory._format`, authoritative):
`{ "citation": "31 CFR 1010.311", "heading": "...", "url": "https://...", "source": "ecfr", "as_of": "2026-06-15" }`
Any field may be an empty string. `source` values seen: `ecfr`, `fedreg`, `fincen_advisory`,
`ffiec` (map to badges; unknown → show raw value).

**No `intent` field is ever sent over SSE.** (Confirmed: the orchestrated path emits
`verification` but never an intent event/field.) See Decision D2.

### `GET /corpus_status` → JSON
Success (200):
`{ "indexed": <int>, "as_of": "<date|null>", "rag_mode": "<str>", "last_etl_run": "<iso8601|null>", "counts_by_source": { "ecfr": <int>, "fedreg": <int>, ... } }`
Error (503): `{ "indexed": 0, "error": "<str>" }`. UI MUST handle both `indexed==0`
(corpus not built) and the 503/error body without throwing.

### `GET /healthz` → JSON
`{ "ok": true, "rag_mode": "<str>", "generate": <bool> }`. Optional to consume;
if used, only for a quiet health indicator — never block the UI on it.

---

## Decisions made (resolved by PM — do NOT treat as open)

- **D1 — No Cognitus asset pack exists in this repo.** `Glob **/cognitus*` → no files
  anywhere. There is no importable `cognitus.css`/`cognitus.js`/`components.md`/
  `design-spec.md`. The senior-dev **authors `cognitus.css` and `cognitus.js` from
  scratch** using only the token table, component mapping, and interaction states in
  `docs/UIUX_COGNITUS.md` §1–§5 (transcribed into "Design tokens" below so you need not
  re-open the doc). The doc's references to a "Cognitus skill's `references/…`" are not
  actionable — ignore them; the token/component/do-don't detail in the doc is sufficient
  to build directly. This is **not a blocker.**

- **D2 — Intent chip is built but hidden by default (data-driven, degrades to absent).**
  The backend sends no intent over SSE, and `ORCHESTRATION` ships `false` by default
  (iter-3 D6), so no intent data exists for most requests. Therefore: **do NOT invent an
  intent source and do NOT add a backend intent event this iteration.** Implement the
  intent chip as a DOM element that stays hidden unless an `intent` field is present on a
  received event (it will not be, today). This satisfies UIUX §2.2 "optional, subtle" and
  §7 ("behind a details toggle") while being honest about current data. Acceptance is:
  chip is absent/hidden for every current backend response, and its absence does not break
  layout. (Resolves UIUX §7 open item #2.)

- **D3 — "What changed" timeline view: SKIPPED this iteration, with reason.** UIUX §2.3
  requires "a hairline timeline of FinCEN actions … from the version ledger." **No such
  ledger exists:** `change_resolver` was deferred in iter-3 (D5), and iter-2's provenance
  ledger records ingest *actions*, not a before/after version timeline (confirmed in
  `src/etl/state.py` — `provenance` has no valid_from/valid_to). The backlog explicitly
  allows this: "'What changed' timeline view if change_resolver shipped; otherwise note as
  deferred with reason." **Decision: do not build it — not even a placeholder screen.**
  Building a placeholder would imply a capability the product does not have and risks
  showing an empty/fake timeline in the mandated README screenshots. Record the deferral in
  `changes.md`. (This closes the backlog's only conditional AC.)

- **D4 — FAQ "from cache/FAQ" marker: add ONE minimal backend SSE field.** Verified in
  `src/app/api.py`: the Tier-1 FAQ fast-path (`chat_stream.gen`) emits `token` + `citations`
  + `done` that are **byte-identical** to a generated/cached answer — there is no existing
  signal the UI could use to distinguish an FAQ hit, and "it felt instant" is not a reliable
  client-side signal. UIUX §4 explicitly wants a "subtle 'from FAQ' marker." The minimal,
  additive change: **on the FAQ fast-path only**, add a single field to the existing
  `citations` event data: `"source_tier": "faq"`. Do **not** add a new event type, do not
  touch the other two branches' payloads. This preserves the AC-2/D9 byte-identical
  guarantee for the non-FAQ paths (they simply never set `source_tier`). UI shows the marker
  when `citations.source_tier === "faq"`, hides it otherwise. See "Files to modify" for the
  exact one-line-scope edit. Rationale for choosing this over "no signal": without it, the
  "Cache/FAQ hit" state in UIUX §4 is unimplementable and untestable.

- **D5 — Fonts.** Abadi ExtraLight is a commercial font whose license cannot be verified in
  this environment and no font file is bundled. Per UIUX §7 ("cognitus.css already falls
  back to a light-weight system sans if absent"), **do not embed or fetch any font.** Use a
  system-font fallback stack for headings that favors a light/thin weight; body stays a
  neutral system sans. No `@font-face`, no Google Fonts, no CDN (CSP/offline-safe, matches
  the dependency-light rule). Exact stacks in "Design tokens." (Resolves UIUX §7 open item #1.)

- **D6 — `ORCHESTRATION` default flip is OUT OF SCOPE here.** The live decision noted in
  `progress.md` (revisit flipping `ORCHESTRATION` to `true` with a latency-inclusive
  measurement) is a retrieval/latency question, not a UI one. This frontend iteration does
  not flip it and does not depend on it. The UI must work correctly with the shipped default
  (`false`), which means: `verification` events are usually absent, and that is fine (see D2,
  and the verifier-decline state below which triggers only when the event IS present).

---

## Acceptance criteria (testable — a screenshot / DOM inspection / curl can verify each)

Numbered AC-1..AC-12. Each is verifiable by the downstream UI/UX review stage without
guessing. "DOM check" = query the rendered DOM; "visual" = screenshot; "contrast" =
computed color pair vs WCAG.

**Structure & branding**
- **AC-1 — Semantic landmarks present.** Rendered page contains exactly one `<header>`,
  one `<main>`, one `<footer>`, and the citation panel is an `<aside>` (or `role`-equivalent)
  associated with the answer. A single `<h1>` exists; section labels use real heading
  elements, not styled `<div>`s. (DOM check.)
- **AC-2 — Cognitus tokens applied via `cognitus.css`.** `src/app/static/cognitus.css`
  exists and is the source of the palette; the page uses Jefferson Blue `#232D4B` for
  structural/header color, Bronze `#7B6D45` for eyebrow kickers / source badges / section
  numbers, and Cyan `#34CAFF` as the **single** accent (streaming caret / active state / a
  data rule). No shadows, no gradients, no accent stripes anywhere (hairline rules +
  whitespace only). (DOM check on `cognitus.css` presence + computed styles + visual.)
- **AC-3 — "One accent per view" honored.** In any single rendered view, cyan appears as an
  accent in at most one role at a time (caret OR active control OR one data rule — not a
  cyan-splattered UI). Cyan is never used for body text or as the *sole* signal of a status.
  (Visual + contrast reasoning.)

**Hero + corpus-status strip (fully backed by `/corpus_status`)**
- **AC-4 — Hero split renders.** A hero with: a Bronze **eyebrow kicker** (bold, UPPERCASE,
  wide letter-spacing, e.g. `AML / KYC · RAG`), a thin Abadi-fallback headline (sentence
  case, never bold), a one-line subhead, and the ask box as the single primary action.
  (Visual + DOM.)
- **AC-5 — Corpus-status strip shows live data.** A hairline-separated strip renders
  `Corpus as of {as_of}`, the indexed count, and the sources present, read from a real
  `GET /corpus_status` call. It uses `counts_by_source` keys for the source list and `as_of`
  for currency. When `indexed==0` or the endpoint returns the 503/error body, the strip shows
  a calm "corpus not built / status unavailable" message (no crash, no stack trace). (Visual +
  DOM, with the endpoint both healthy and forced-error.)

**Chat / answer view + citations (existing SSE contract)**
- **AC-6 — Streaming still works, restyled.** Submitting a question streams `token` chunks
  into the answer region in order; a **cyan** streaming caret is the single accent during
  streaming and is removed on `done`. Answer text is body (neutral sans), not a heading font.
  (Visual during stream + DOM at `done`.)
- **AC-7 — Citation panel.** On `citations`, each citation renders as a **hairline-ruled
  card** containing: a **Bronze source badge** derived from `source` (`ecfr`→`31 CFR`,
  `fedreg`→`FinCEN`, `fincen_advisory`→`FinCEN`, `ffiec`→`FFIEC`; unknown→raw `source`), the
  `citation` identifier, the card's `as_of`, and a **real `<a href>`** click-through to `url`
  (opens in new tab, `rel="noopener"`). Empty-string fields are tolerated (omit that line, no
  "undefined"). The panel is a **right rail on desktop** and **collapses below the answer on
  narrow screens** (see AC-11). (DOM + visual at two widths.)
- **AC-8 — `as_of` stamp on every answer.** Every answered response shows an `as_of` stamp
  (from the `citations` event `as_of`, falling back to the first citation's `as_of`), for both
  fresh and FAQ/cached answers. If `as_of` is null/empty, show a neutral "as of: n/a" rather
  than blank or "null". (DOM.)

**Interaction states**
- **AC-9 — Verifier-decline state.** When a `verification` event arrives with
  `declined===true` (or `grounded===false`), the UI shows a **calm, branded** message —
  wording per UIUX §4: *"I can't ground an answer for that — try rephrasing or narrowing to a
  specific rule."* — instead of presenting the ungrounded text as authoritative. When
  `verification` arrives with `grounded===true, declined===false`, the answer renders normally
  (optionally a subtle "grounded" affordance; not required). When **no** `verification` event
  arrives (the default non-orchestrated path), the answer renders normally with no decline UI.
  `unsupported_claims` / `missing_elements`, if non-empty, may be surfaced subtly (e.g. a small
  note) but must not be shown as a stack trace or error. (Verifiable by feeding a synthetic SSE
  stream containing a `declined:true` verification event; see "Testing hooks.")
- **AC-10 — FAQ-hit marker.** When the `citations` event carries `source_tier==="faq"` (D4),
  a **subtle** "from FAQ" marker renders near the answer/as_of stamp. When absent, no marker.
  Must be visually quiet (small, not a colored banner). (DOM + visual, verifiable via a
  synthetic stream and via a real seeded-FAQ question.)

**Accessibility & responsive (non-negotiable per project standards)**
- **AC-11 — Responsive breakpoint.** At a desktop width (≥ ~900px) the citation panel is a
  right rail alongside the answer; at a narrow width (≤ ~640px) it collapses to below the
  answer (stacked, full-width), and the page body never scrolls horizontally. The ask box and
  hero remain usable at 375px. (Visual at 375 / 768 / 1280.)
- **AC-12 — WCAG AA contrast + full keyboard operability + no color-only signaling.**
  - Contrast: Jefferson Blue `#232D4B` on white and white on Jefferson Blue both meet WCAG AA
    for their text sizes; Bronze `#7B6D45` used for text meets AA on its background; **cyan is
    never used for body text or as the sole status signal.** (Computed-contrast check on each
    text/background pair — each ≥ 4.5:1 for normal text, ≥ 3:1 for large/bold ≥24px or ≥18.66px
    bold.)
  - Keyboard: the ask box, the submit control, every citation `<a>`, and any panel
    toggle/collapse control are reachable and operable by keyboard alone in a sensible tab
    order; visible focus indicator on each (focus ring may use cyan — that's an accent, not
    body text). Submitting the question works via keyboard (Enter in the ask box or focusing
    and activating the button). (Keyboard tab-through + DOM focus check.)
  - Signaling: every state that uses color (decline, FAQ marker, streaming) is **also**
    conveyed by text/shape, not color alone. (DOM/visual.)

---

## Files to create

- **`src/app/static/cognitus.css`** — the Cognitus design system, authored from the tokens
  below. Palette as CSS custom properties on `:root`; hero, corpus strip, answer, citation
  card, source badge, eyebrow kicker, disclaimer footer, decline state, FAQ marker, focus
  rings, and the ≥900 / ≤640 responsive rules. No shadows/gradients; hairline rules only.
- **`src/app/static/cognitus.js`** — progressive-enhancement only: optional scroll-reveal and
  the corpus-status **animated counter** (UIUX §3 "used sparingly"). Must be **non-essential**
  — the page is fully functional and readable with JS disabled or if this file fails to load.
  Do **not** put the SSE client here unless you also keep it working; prefer leaving the SSE
  client inline or in a small `app.js` (see below). No external dependencies.
- **(optional) `src/app/static/app.js`** — if you extract the SSE client out of `index.html`
  for clarity, it lives here. Optional; inline is acceptable. If created, `index.html` must
  reference it with a plain `<script src>` (same-origin, no module CDN).

## Files to modify

- **`src/app/static/index.html`** — rebuilt markup: `<header>` (wordmark + optional health
  dot), hero split, corpus-status strip, `<main>` with ask box + answer region + `<aside>`
  citation panel, persistent `<footer>` disclaimer, hidden intent-chip element (D2), decline
  region, FAQ marker element. Links `cognitus.css` (and `cognitus.js` / `app.js`) via plain
  same-origin tags. The existing SSE parsing loop (the `\n\n` block reader in the current
  file) is the reference client — **preserve its event handling** and extend it to: render the
  new `verification` event (AC-9), read `source_tier` off `citations` (AC-10), and drive the
  cyan caret (AC-6). Keep the `/corpus_status` fetch, upgraded to the richer strip (AC-5).
- **`src/app/api.py`** — the **only** backend edit, and it is minimal (D4): in
  `chat_stream.gen()`'s **FAQ fast-path branch only** (the `if hit is not None:` block that
  currently yields `token` → `citations` → `done`), add `"source_tier": "faq"` to the
  `citations` event's data dict. That block becomes:
  `yield _sse("citations", {"citations": hit["citations"], "as_of": hit["as_of"], "source_tier": "faq"})`
  Do **not** modify `_gen_iter2_path` or `_gen_orchestrated_path` citation payloads — they must
  stay `source_tier`-free to preserve the AC-2/D9 byte-identical collapse guarantee. No other
  backend file changes.

## Files explicitly NOT to touch
- No retrieval / orchestration / FAQ / ETL logic (`src/rag/**`, `src/etl/**`) beyond the one
  `api.py` line above.
- No new Python dependency; no `requirements.txt` change.
- No new backend route, no new SSE event type.
- No `.github/workflows`, no Dockerfile, no test-infra changes (that's Iteration 5).

---

## Interfaces / signatures (frontend contracts)

The SSE client must handle the event set exactly as specified in "Backend contract" above.
Concretely, the parse loop dispatches on `event:` name:

- `token`   → append `data.t` to the answer node (order-preserving); show cyan caret.
- `verification` → if `data.declined || !data.grounded` render the decline state (AC-9);
  else optionally mark grounded. Store `data.unsupported_claims` / `data.missing_elements`
  for a subtle note if non-empty.
- `citations` → render citation cards from `data.citations[]` (fields: `citation, heading,
  url, source, as_of`); set the `as_of` stamp from `data.as_of` (fallback first card's
  `as_of`); if `data.source_tier === "faq"` show the FAQ marker (AC-10).
- `done`     → remove caret, finalize (no further events).

`/corpus_status` consumer: read `indexed`, `as_of`, `counts_by_source` (object; iterate keys
for the source list), `last_etl_run` (optional, may be null). Handle the 503 `{indexed:0,error}`
shape and the healthy-but-`indexed==0` shape identically → "corpus not built / status
unavailable."

Source → badge label mapping (single source of truth, put it in JS):
`{ ecfr: "31 CFR", fedreg: "FinCEN", fincen_advisory: "FinCEN", ffiec: "FFIEC" }`,
default → the raw `source` string (never render empty/"undefined").

---

## Design tokens (transcribed from UIUX_COGNITUS.md §1 — authoritative for this iteration)

| Token | Value | Use |
|-------|-------|-----|
| Jefferson Blue | `#232D4B` | Structural: thin headings, dark bands, header, disclaimer text |
| Bronze | `#7B6D45` | Eyebrow kickers, section numbers, source badges |
| Cyan (tech-pop) | `#34CAFF` | **Single** accent per view: active states, streaming caret, one data rule |
| White / light-gray | dominant | Background; whitespace carries the page |

- **Headings:** thin weight, **sentence case, never bold** (thinness is the brand). Abadi
  ExtraLight is unavailable (D5) → fallback stack, e.g.
  `font-family: "Abadi Extra Light","Abadi MT","Segoe UI Light","Helvetica Neue",Arial,sans-serif; font-weight: 200;`
  (accept that some systems render ~300; never bold).
- **Body:** neutral sans, e.g. `Arial, "Helvetica Neue", system-ui, sans-serif;` normal weight.
- **Eyebrow kickers:** bold, UPPERCASE, wide letter-spacing (`letter-spacing: .12em`), Bronze.
- **Rules/decoration:** hairlines (`1px` light-gray) + whitespace only. **No shadows, no
  gradients, no accent stripes.**
- **One accent per view maximum** (AC-3). When in doubt, remove an accent.

Interaction states (UIUX §4):
- **Loading:** quiet — a thin cyan rule or one understated spinner; no busy animation.
- **Cache/FAQ hit:** answer appears effectively instantly; show `as_of` + the subtle "from
  FAQ" marker (AC-10, D4).
- **Verifier decline:** calm branded message (AC-9), not a hard error.
- **Empty/error:** Cognitus-styled, plain-language, **no stack traces** (applies to
  `/corpus_status` errors, empty citations, and the empty-question 400).

---

## Edge cases (handle all)

1. **No `verification` event** (default `ORCHESTRATION=false`): render the answer normally,
   no decline UI. This is the common case — do not gate answer rendering on `verification`.
2. **`verification` with `grounded:false`/`declined:true`:** show decline state; do not present
   the streamed tokens as an authoritative answer (per AC-9 you may keep them visible but
   clearly demoted, or replace with the decline message — either is acceptable as long as the
   decline is unmistakable and calm).
3. **`citations: []`** (no matching text; api.py yields the "No matching regulatory text…"
   token then empty citations): show the answer token, no citation cards, and a neutral "no
   citations" note; `as_of` stamp → "n/a".
4. **Citation fields empty strings** (`url`/`heading`/`as_of`/`source` == ""): omit the missing
   line; if `url==""` render the citation as plain text (no dead `<a href="">`); never print
   "undefined"/"null".
5. **`/corpus_status` 503 or `indexed==0`:** calm "corpus not built / status unavailable" in the
   strip; the ask box still works (retrieval may still return the "no matching text" path).
6. **Empty question submit:** the backend returns `400 {error:"empty question"}` (not SSE) —
   the client must not try to parse it as an event stream; show a quiet inline "enter a
   question" hint and don't blow up on the non-stream response.
7. **Long answers / wide content:** answer and citation cards wrap; any wide element (long URL,
   citation) stays inside its container — no horizontal page scroll (AC-11).
8. **`source_tier` absent** on `citations` (every non-FAQ path): no FAQ marker (AC-10).
9. **Cold-start latency** (first token can be 15–30s per UIUX §4): the quiet loading state
   persists until the first `token`; don't show a spurious error before tokens arrive.
10. **JS-disabled / `cognitus.js` load failure:** page is still readable and the disclaimer +
    hero + static content still render (progressive enhancement; the counter/scroll-reveal are
    the only things that may silently no-op).

---

## Patterns to follow

- **Mirror the existing SSE client** in `src/app/static/index.html` (the `fetch('/chat_stream')`
  + `reader.read()` + `\n\n`-split + `event:`/`data:` regex loop). Keep that exact streaming
  approach; extend it, don't rewrite it into a framework.
- **Dependency-light, offline-safe:** plain `<style>`/`<link rel=stylesheet>`/`<script src>`,
  all same-origin under `src/app/static/`. No CDN, no `@font-face` remote, no npm/build. This
  matches the current file and ARCHITECTURE §8 / UIUX §5 ("plain static files … no heavy
  framework").
- **Additive backend change only** (D4): follow the iter-3 D9 discipline — the non-FAQ paths'
  SSE bytes are a frozen contract; only the FAQ branch gains a field.
- **`_sse()` helper** in `api.py` already JSON-encodes the data dict — just add the key to the
  dict passed in; do not hand-format SSE.
- **Ponytail: full, but silent.** No `ponytail:` comments and no literal word "ponytail"
  anywhere in the new/edited files (HTML/CSS/JS/py). Record any simplification in
  `.build/iter-4/changes.md`, not in code comments. (The existing `api.py` already contains
  pre-existing `ponytail:` comment lines in untouched branches — do **not** add new ones and do
  not remove the pre-existing ones as part of this iteration; leave the byte-identical branches
  alone except for the one FAQ-line edit.)

## Testing hooks (so the UI/UX review stage can verify states that the default backend rarely produces)

The reviewer needs to see the decline and FAQ states, which the default config (`ORCHESTRATION=false`)
rarely emits live. Make these states **inspectable without backend changes**:
- The decline (AC-9) and FAQ-marker (AC-10) rendering must be driven purely by the shape of
  received events, so the reviewer can exercise them by POSTing to `/chat_stream` with
  `ORCHESTRATION=true`+`VERIFY_ANSWERS=true` (for a real `verification` event) and by asking a
  seeded FAQ question (for a real `source_tier:"faq"` citations event), OR by replaying a
  captured/synthetic SSE fixture against the client. Do **not** add a magic query param or debug
  route — keep the client a pure function of the event stream. (If you extract the render
  functions so they can be called on a hand-built event object, that's encouraged but not
  required.)
- README screenshots to capture (build step §6.5 of UIUX, minus the deferred one): **landing
  (hero + corpus strip)**, **answer + citation panel** (desktop rail + mobile collapsed), and
  **verifier-decline state**. The "what changed" screenshot is **omitted** (D3).

---

## Out of scope

- The "What changed" / change-timeline view (D3 — no version-ledger data exists; deferred with
  reason, per the backlog's own allowance).
- Any backend/retrieval/orchestration/FAQ/ETL logic change beyond the single `api.py`
  `source_tier:"faq"` line (D4).
- Flipping the `ORCHESTRATION` default (D6 — separate latency-driven decision, not a UI task).
- A real intent event/source (D2 — chip is data-driven and stays hidden; no backend intent
  plumbing this iteration).
- New Python dependencies, new routes, new SSE event types, font embedding/licensing, CDN
  assets, or any build tooling.
- Test suite / Dockerfile / CI / `requirements.lock` (that is Iteration 5).

---

## Definition of done for this iteration

All of AC-1..AC-12 demonstrably true; `cognitus.css` + `cognitus.js` authored from the tokens;
`index.html` rebuilt and wired to the unchanged SSE contract (plus the one additive FAQ field);
the three required README screenshots captured (landing, answer+citations desktop/mobile,
decline); no new dependency; no `ponytail:` text; D3's deferral and every divergence recorded in
`.build/iter-4/changes.md`.
