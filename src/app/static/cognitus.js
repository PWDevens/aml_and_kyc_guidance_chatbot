/* Cognitus progressive enhancement (Iteration 4).
   Non-essential: scroll-reveal + animated corpus-status counter (UIUX §3,
   "used sparingly"). The page is fully functional and readable if this file
   fails to load or JS is disabled -- app.js drives the actual SSE client and
   all required content renders without this file. */
(function () {
  "use strict";

  /* Animated counter: call once with the final integer value and the target
     element; counts up quickly and settles on the real number. No-ops
     gracefully if the element or value is missing. */
  function animateCount(el, value) {
    if (!el || typeof value !== "number" || !isFinite(value)) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = String(value);
      return;
    }
    var start = 0;
    var duration = 600;
    var startTime = null;

    function step(ts) {
      if (startTime === null) startTime = ts;
      var progress = Math.min(1, (ts - startTime) / duration);
      var current = Math.round(start + (value - start) * progress);
      el.textContent = String(current);
      if (progress < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
  }

  /* Scroll-reveal: fade/slide elements marked [data-reveal] into place the
     first time they enter the viewport. Falls back to fully visible content
     (no IntersectionObserver support, or reduced motion). */
  function initScrollReveal() {
    var targets = document.querySelectorAll("[data-reveal]");
    if (!targets.length) return;
    if (!("IntersectionObserver" in window) ||
        (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) {
      return;
    }
    targets.forEach(function (el) { el.classList.add("reveal-pending"); });
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.remove("reveal-pending");
          entry.target.classList.add("reveal-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    targets.forEach(function (el) { observer.observe(el); });
  }

  window.Cognitus = window.Cognitus || {};
  window.Cognitus.animateCount = animateCount;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initScrollReveal);
  } else {
    initScrollReveal();
  }
})();
