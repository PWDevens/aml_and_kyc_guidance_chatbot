# UI / UX — Cognitus Design System

**Deviation 4 of 4.** · **Status:** Draft v1 · **Last updated:** 2026-06-25

> **Goal:** present the chatbot through the **Cognitus** design system — a
> minimalist, consulting-grade identity (the house style of Cognitus Heuristics
> Advisory) — so the product reads as a credible professional tool, not a demo toy.

`fedacq-rag-chatbot` ships a lightweight HTML/JS/CSS UI from `src/app/static/`.
This project keeps that lean, dependency-free, SSE-streaming front end and
**restyles it with Cognitus**: graft `cognitus.css` onto the existing markup and
adopt the system's components.

---

## 1. Design tokens (Cognitus)

| Token | Value | Use |
|-------|-------|-----|
| **Jefferson Blue** | `#232D4B` | Structural color — thin headings, dark bands, the header |
| **Bronze** | `#7B6D45` | Eyebrow kickers, section numbers, source badges |
| **Cyan (tech-pop)** | `#34CAFF` | Sparing accent — active states, the streaming caret, data rules |
| **White / light-gray** | dominant | Space carries the page |
| **Headings** | Abadi ExtraLight, sentence case | Never bold — the *thinness is the brand* |
| **Body** | Arial | Readable, neutral |
| **Eyebrow kickers** | Bold UPPERCASE, wide letter-spacing | Section labels |
| **Rules/decoration** | Hairlines + whitespace only | No shadows, no gradients, no accent stripes |

> **One accent per view, maximum.** When in doubt, remove an accent rather than add
> one. Restraint is the brand.

Implementation: ship `assets/cognitus.css` (and `cognitus.js` for scroll-reveal /
counters) from the Cognitus skill into `src/app/static/`, and apply its component
classes to the chat markup.

---

## 2. Screens & layout

### 2.1 Landing / hero
- Cognitus **hero split**: thin Abadi ExtraLight headline (e.g., *"Defensible
  answers on U.S. AML/KYC regulation"*), a bronze eyebrow kicker (`AML / KYC ·
  RAG`), one-line subhead, and a single primary action (the ask box).
- A quiet **corpus-status strip** (hairline-separated): `Corpus as of {as_of} ·
  Sources: 31 CFR X · FinCEN · FFIEC` — currency made visible from the first screen.

### 2.2 Chat / answer view
- **Ask box** anchored, generous whitespace around it.
- **Streaming answer** in Arial body; the streaming caret uses the cyan tech-pop as
  the *single* accent. Tokens render via SSE exactly as fedacq does.
- **Citation panel** (right rail on desktop, collapsible below on mobile): each
  citation a hairline-ruled card with a **bronze source badge** (`31 CFR` /
  `FinCEN` / `FFIEC`), the section identifier, the `as_of` date, and a click-through
  link. Maps directly to fedacq's citation event payload.
- **`as_of` stamp** on every answer (cached or fresh).
- **Intent chip** (optional, subtle): a small label showing the routed intent
  (definitional / numeric / procedural / change …) for transparency.

### 2.3 "What changed" view (change intent)
- A hairline **timeline** of FinCEN actions on the topic (from the version ledger):
  publication date · effective date · doc number · link. Dark Jefferson-Blue band
  header; bronze section numbering.

### 2.4 Persistent disclaimer footer
- Always-visible, quiet footer: *"Research aid grounded in public regulatory text —
  not legal or compliance advice."* Small, Jefferson Blue, hairline-separated.
  Mirrors the disclaimer carried in the API payload (PRD §7).

---

## 3. Cognitus component mapping

| UI element | Cognitus component |
|------------|--------------------|
| Header / nav | `cognitus` header + wordmark |
| Page intro | Hero split + eyebrow kicker |
| Source badges | Bronze eyebrow/pill labels |
| Citation cards | Hairline-ruled cards |
| Corpus-status / metrics | Stat callouts (with animated counters, used sparingly) |
| "What changed" header | Dark band |
| Section labels | Bold UPPERCASE eyebrow kickers |
| Footer | `cognitus` footer (wordmark + disclaimer) |

See the Cognitus skill's `references/components.md` for exact class names and
markup, and `references/design-spec.md` for the full type scale and do/don'ts.

---

## 4. Interaction & states

- **Loading:** quiet — a thin cyan rule or a single understated spinner; no busy
  animation. (fedacq shows a 15–30 s cold start on first token; warm-start config
  is inherited, so this is rare.)
- **Cache/FAQ hit:** answer appears effectively instantly; the `as_of` stamp and a
  subtle "from FAQ" marker keep it transparent.
- **Verifier decline:** when `answer_verifier` finds nothing grounded, show a calm,
  branded "I can't ground an answer for that — try rephrasing or narrowing to a
  specific rule" rather than a hard error.
- **Empty/error:** Cognitus-styled, plain-language, no stack traces.

---

## 5. Accessibility & craft

- **Contrast:** Jefferson Blue on white and white on Jefferson Blue both pass
  WCAG AA; cyan is used for accent, **not** for body text or sole status signaling.
- **Keyboard:** full keyboard operability for ask box, citation links, panels.
- **Semantics:** real headings/landmarks; citation links are real `<a>` elements.
- **Responsive:** citation rail collapses under the answer on narrow screens.
- **No heavy framework:** plain static files (matching fedacq) keep it fast and
  dependency-light; `cognitus.js` enhancements are progressive.

---

## 6. Build steps (Phase 4)

1. Copy `cognitus.css` + `cognitus.js` into `src/app/static/`.
2. Rebuild `index.html` from the Cognitus `index.html`/`report.html` starters,
   wiring the ask box to the existing `/chat_stream` SSE client (`app.js`).
3. Implement the citation panel against the existing citation event payload.
4. Add the corpus-status strip (reads `GET /corpus_status`).
5. Verify contrast/keyboard/responsive; capture screenshots for the README
   (landing, answer + citations, "what changed").

---

## 7. Open items

- Confirm Abadi ExtraLight availability in the demo environment; the Cognitus CSS
  already falls back to a light-weight system sans if absent.
- Decide whether to show the intent chip by default or behind a "details" toggle.
