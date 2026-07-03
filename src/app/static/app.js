/* Cognitus SSE client (Iteration 4). Extends the original inline client from
   the pre-Cognitus index.html: same fetch('/chat_stream') + reader.read() +
   '\n\n'-split + event:/data: regex loop, now also handling the
   'verification' event (AC-9) and the 'source_tier' field on 'citations'
   (AC-10), and driving the cyan streaming caret (AC-6). */
(function () {
  "use strict";

  var SOURCE_BADGES = {
    ecfr: "31 CFR",
    fedreg: "FinCEN",
    fincen_advisory: "FinCEN",
    ffiec: "FFIEC"
  };

  function badgeFor(source) {
    if (source && SOURCE_BADGES[source]) return SOURCE_BADGES[source];
    return source || "";
  }

  var els = {
    corpusStrip: document.getElementById("corpus-strip"),
    healthDot: document.getElementById("health-dot"),
    form: document.getElementById("ask-form"),
    q: document.getElementById("q"),
    askBtn: document.getElementById("ask-btn"),
    askHint: document.getElementById("ask-hint"),
    loadingRule: document.getElementById("loading-rule"),
    answer: document.getElementById("answer"),
    answerStatus: document.getElementById("answer-status"),
    declineRegion: document.getElementById("decline-region"),
    declineMessage: document.getElementById("decline-message"),
    asOfStamp: document.getElementById("as-of-stamp"),
    asOfText: document.getElementById("as-of-text"),
    faqMarker: document.getElementById("faq-marker"),
    answerNote: document.getElementById("answer-note"),
    citations: document.getElementById("citations"),
    intentChip: document.getElementById("intent-chip")
  };

  var DECLINE_MESSAGE = "I can't ground an answer for that — try rephrasing or narrowing to a specific rule.";

  // ---------- corpus status strip (AC-5) ----------
  function renderCorpusUnavailable() {
    els.corpusStrip.setAttribute("data-state", "unavailable");
    els.corpusStrip.innerHTML = '<span class="stat">Corpus not built / status unavailable.</span>';
  }

  function renderCorpusStatus(d) {
    if (!d || typeof d.indexed !== "number" || d.indexed === 0 || d.error) {
      renderCorpusUnavailable();
      return;
    }
    els.corpusStrip.removeAttribute("data-state");
    var sources = d.counts_by_source && typeof d.counts_by_source === "object"
      ? Object.keys(d.counts_by_source)
      : [];
    var asOf = d.as_of || "n/a";

    var parts = [];
    parts.push('<span class="stat">Corpus as of <strong>' + escapeHtml(asOf) + "</strong></span>");
    parts.push('<span class="stat"><strong id="corpus-count">0</strong> sections indexed</span>');
    if (sources.length) {
      parts.push('<span class="stat">Sources: ' + escapeHtml(sources.join(" · ")) + "</span>");
    }
    els.corpusStrip.innerHTML = parts.join("");

    var countEl = document.getElementById("corpus-count");
    if (window.Cognitus && typeof window.Cognitus.animateCount === "function") {
      window.Cognitus.animateCount(countEl, d.indexed);
    } else if (countEl) {
      countEl.textContent = String(d.indexed);
    }
  }

  fetch("/corpus_status")
    .then(function (r) { return r.json().catch(function () { return { indexed: 0, error: "bad response" }; }); })
    .then(renderCorpusStatus)
    .catch(renderCorpusUnavailable);

  // Quiet health indicator only; never blocks the UI (spec: optional).
  fetch("/healthz")
    .then(function (r) { return r.json(); })
    .then(function (d) { els.healthDot.setAttribute("data-ok", d && d.ok ? "true" : "false"); })
    .catch(function () { /* quiet: health check is optional */ });

  // ---------- escaping helper ----------
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---------- rendering helpers (pure functions of event data; exposed for
  // manual/synthetic-fixture exercise per the spec's "Testing hooks") ----------

  function renderCitations(data) {
    var list = (data && data.citations) || [];
    els.citations.innerHTML = "";
    if (!list.length) {
      var note = document.createElement("p");
      note.className = "citation-empty-note";
      note.textContent = "No citations for this answer.";
      els.citations.appendChild(note);
    } else {
      list.forEach(function (c) {
        var card = document.createElement("div");
        card.className = "citation-card";

        var badgeText = badgeFor(c.source);
        if (badgeText) {
          var badge = document.createElement("div");
          badge.className = "source-badge";
          badge.textContent = badgeText;
          card.appendChild(badge);
        }

        if (c.citation) {
          var idLine = document.createElement("div");
          idLine.className = "citation-id";
          idLine.textContent = c.citation;
          card.appendChild(idLine);
        }

        if (c.heading) {
          var heading = document.createElement("div");
          heading.className = "citation-heading";
          heading.textContent = c.heading;
          card.appendChild(heading);
        }

        if (c.url) {
          var link = document.createElement("a");
          link.href = c.url;
          link.target = "_blank";
          link.rel = "noopener";
          link.textContent = "View source";
          card.appendChild(document.createElement("br"));
          card.appendChild(link);
        }

        if (c.as_of) {
          var asOf = document.createElement("div");
          asOf.className = "citation-as-of";
          asOf.textContent = "as of: " + c.as_of;
          card.appendChild(asOf);
        }

        els.citations.appendChild(card);
      });
    }

    // as_of stamp: from citations event, falling back to first card's as_of.
    var stampValue = data && data.as_of;
    if (!stampValue && list.length) stampValue = list[0].as_of;
    els.asOfText.textContent = "as of: " + (stampValue || "n/a");
    els.asOfStamp.hidden = false;

    // FAQ marker (AC-10, D4): only when citations.source_tier === "faq".
    els.faqMarker.hidden = !(data && data.source_tier === "faq");
  }

  function renderVerification(data) {
    if (!data) return;
    var declined = !!data.declined || data.grounded === false;
    if (declined) {
      els.declineMessage.textContent = DECLINE_MESSAGE;
      els.declineRegion.hidden = false;
      if (els.answerStatus) els.answerStatus.textContent = "Answer not grounded. " + DECLINE_MESSAGE;
    } else {
      els.declineRegion.hidden = true;
    }

    var notes = [];
    if (data.unsupported_claims && data.unsupported_claims.length) {
      notes.push("Unsupported: " + data.unsupported_claims.join("; "));
    }
    if (data.missing_elements && data.missing_elements.length) {
      notes.push("Missing: " + data.missing_elements.join("; "));
    }
    if (notes.length) {
      els.answerNote.textContent = notes.join(" · ");
      els.answerNote.hidden = false;
    } else {
      els.answerNote.hidden = true;
    }

    // D2: intent chip stays hidden unless an `intent` field is present on a
    // received event. No backend intent is sent today; this simply degrades
    // to absent, per spec.
    if (data.intent) {
      els.intentChip.textContent = data.intent;
      els.intentChip.setAttribute("data-visible", "true");
    }
  }

  // Expose pure render functions for synthetic-fixture exercise (spec
  // "Testing hooks"): a reviewer can call these directly with a hand-built
  // event object without touching the network layer.
  window.CognitusRender = {
    citations: renderCitations,
    verification: renderVerification
  };

  // ---------- reset UI for a new question ----------
  function resetAnswerUI() {
    els.answer.textContent = "";
    if (els.answerStatus) els.answerStatus.textContent = "";
    els.citations.innerHTML = "";
    els.declineRegion.hidden = true;
    els.asOfStamp.hidden = true;
    els.faqMarker.hidden = true;
    els.answerNote.hidden = true;
    els.intentChip.setAttribute("data-visible", "false");
    els.intentChip.textContent = "";
  }

  function setCaret(active) {
    var existing = els.answer.querySelector(".caret");
    if (active && !existing) {
      var caret = document.createElement("span");
      caret.className = "caret";
      caret.setAttribute("aria-hidden", "true");
      els.answer.appendChild(caret);
    } else if (!active && existing) {
      existing.remove();
    }
  }

  function appendToken(t) {
    var caret = els.answer.querySelector(".caret");
    var textNode = document.createTextNode(t);
    if (caret) {
      els.answer.insertBefore(textNode, caret);
    } else {
      els.answer.appendChild(textNode);
    }
  }

  // ---------- ask flow ----------
  function ask(question) {
    resetAnswerUI();
    els.askBtn.disabled = true;
    els.loadingRule.setAttribute("data-active", "true");
    setCaret(true);

    fetch("/chat_stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question })
    }).then(function (resp) {
      if (!resp.ok) {
        // Non-stream error response (e.g. 400 empty question) -- do not try
        // to parse it as an SSE stream.
        return resp.json().catch(function () { return {}; }).then(function (body) {
          setCaret(false);
          els.loadingRule.setAttribute("data-active", "false");
          els.askBtn.disabled = false;
          els.askHint.textContent = (body && body.error) ? "Please enter a question." : "Something went wrong. Please try again.";
        });
      }

      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buf = "";

      function pump() {
        return reader.read().then(function (result) {
          if (result.done) {
            setCaret(false);
            els.loadingRule.setAttribute("data-active", "false");
            els.askBtn.disabled = false;
            return;
          }
          buf += decoder.decode(result.value, { stream: true });
          var i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            var block = buf.slice(0, i);
            buf = buf.slice(i + 2);
            var ev = (block.match(/event: (.*)/) || [])[1];
            var dl = (block.match(/data: (.*)/) || [])[1];
            if (!dl) continue;
            var data = JSON.parse(dl);

            if (ev === "token") {
              els.loadingRule.setAttribute("data-active", "false");
              appendToken(data.t);
            } else if (ev === "verification") {
              renderVerification(data);
            } else if (ev === "citations") {
              renderCitations(data);
            } else if (ev === "done") {
              setCaret(false);
              els.loadingRule.setAttribute("data-active", "false");
              els.askBtn.disabled = false;
              // Announce completion once (single AT interruption), rather than
              // making #answer itself a live region that would re-announce on
              // every token during streaming (chatty / disorienting for screen
              // reader users). Skipped when the decline message already
              // announced (that text is more specific than a generic "ready").
              if (els.answerStatus && els.declineRegion.hidden) {
                els.answerStatus.textContent = "Answer ready.";
              }
            }
          }
          return pump();
        });
      }

      return pump();
    }).catch(function () {
      setCaret(false);
      els.loadingRule.setAttribute("data-active", "false");
      els.askBtn.disabled = false;
      els.askHint.textContent = "Something went wrong. Please try again.";
    });
  }

  els.form.addEventListener("submit", function (evt) {
    evt.preventDefault();
    var question = els.q.value.trim();
    els.askHint.textContent = "";
    if (!question) {
      els.askHint.textContent = "Please enter a question.";
      return;
    }
    ask(question);
  });
})();
