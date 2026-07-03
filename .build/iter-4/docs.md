# Iteration 4 — Documentation Updates

Updated documentation to reflect the Cognitus UI restyle, static-asset routing fix, and FAQ marker signal addition. No speculative content; only what actually shipped.

---

## Files touched

| File | Summary |
|------|---------|
| **README.md** | Updated "Status" section from "Phase 0–3 complete" to "Phase 0–4 complete"; added Phase 4 bullet point describing Cognitus design system, all interaction states, and the three new static-asset routes. Corrected "Phases 4–5 follow" to "Phase 5 follows" (Phase 4 is done). |
| **CHANGELOG.md** | Added new top-level section "Phase 4, Iteration 1 — Cognitus UI/UX restyle" with subsections covering: UI/UX redesign (landmarks, Cognitus tokens, interaction states, responsive layout, accessibility fixes), static assets and routing (three new CSS/JS files, three new `api.py` routes), backend addition (FAQ `source_tier` field, scoped to fast-path only), testing (16 new tests, 139 total passing), and definition of done (AC coverage with honest note on screenshot tooling limitation). Deferred section records "What changed" timeline omission with stated reason (no version-ledger data). |

---

## Content verified against

- `.build/iter-4/spec.md` (frozen spec, all AC 1–12, all decisions D1–D6)
- `.build/iter-4/changes.md` (orchestrator's routing fix, all verification claims)
- `.build/iter-4/test-results.md` (139 tests passing, no regressions)
- `.build/iter-4/frontend-review.md` (ARIA fixes applied, contrast recomputed, responsive confirmed)
- Actual source files: `src/app/static/index.html`, `cognitus.css`, `cognitus.js`, `app.js`, `src/app/api.py`

---

## Honesty notes

- **Screenshots:** README's "Screenshots" section (unchanged from prior iteration) documents that three required images could not be captured due to tooling timeout. No placeholder images created. Manual capture steps provided. Documented in README since Phase 4 was expected to ship them; this is the honest state.
- **"What changed" timeline:** Explicitly deferred (D3, no version-ledger data). CHANGELOG records the deferral with reason, matching the spec's conditional acceptance.
- **Intent chip:** Always hidden (D2); no `intent` field sent by backend. CHANGELOG does not claim it's implemented; the spec itself says it's "data-driven, degrades to absent" — which it does, correctly.
