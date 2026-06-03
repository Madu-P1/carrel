/* Cachet motion — vanilla, zero dependencies.
 * Scroll-reveal (IntersectionObserver), count-up tally, sticky-nav state.
 * Everything degrades: no JS = all content visible; reduced-motion = no movement. */
(function () {
  "use strict";

  /* Reloads land at the hero, never at a restored position or a stale #anchor. */
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  (function () {
    var reloaded =
      (performance.navigation && performance.navigation.type === 1) ||
      (performance.getEntriesByType &&
        (performance.getEntriesByType("navigation")[0] || {}).type === "reload");
    if (reloaded || !location.hash) {
      var toTop = function () {
        var de = document.documentElement, prev = de.style.scrollBehavior;
        de.style.scrollBehavior = "auto";
        window.scrollTo(0, 0);
        de.style.scrollBehavior = prev;
      };
      toTop();
      window.addEventListener("load", toTop);
    }
  })();
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hasIO = "IntersectionObserver" in window;

  /* ---- Reveal on scroll ---- */
  var reveals = document.querySelectorAll("[data-reveal]");
  if (reduce || !hasIO) {
    reveals.forEach(function (el) { el.classList.add("is-visible"); });
  } else {
    var revealIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add("is-visible");
          revealIO.unobserve(e.target);
        }
      });
    }, { threshold: 0.18, rootMargin: "0px 0px -8% 0px" });
    reveals.forEach(function (el) { revealIO.observe(el); });
  }

  /* ---- Count-up (fires when fully in view) ---- */
  function countUp(el) {
    var target = parseInt(el.getAttribute("data-countup"), 10) || 0;
    if (reduce) { el.textContent = String(target); return; }
    var dur = 1300, start = null;
    var ease = function (t) { return 1 - Math.pow(1 - t, 3); };
    function tick(now) {
      if (start === null) start = now;
      var t = Math.min(1, (now - start) / dur);
      el.textContent = String(Math.round(ease(t) * target));
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  var counters = document.querySelectorAll("[data-countup]");
  if (reduce || !hasIO) {
    counters.forEach(countUp);
  } else {
    var countIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { countUp(e.target); countIO.unobserve(e.target); }
      });
    }, { threshold: 1 });
    counters.forEach(function (el) {
      el.textContent = "0"; // start from zero so the reveal counts up, no reset flash
      countIO.observe(el);
    });
  }

  /* ---- Sticky header gains a hairline + blur once scrolled ---- */
  var header = document.querySelector(".site-header");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("scrolled", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---- Scroll-driven moments: the dark band grows to full width, and the
   * "what you get" briefs flip through a 3D spotlight deck. Both run off one
   * rAF-throttled scroll loop. Reduced-motion and narrow screens opt out and
   * keep the static, readable layout. ---- */
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  function easeInOutCubic(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

  var bandInner = document.querySelector(".band-inner");

  var docs = document.querySelector("[data-docs]");
  var deck = docs && docs.querySelector(".docs-deck");
  var cards = deck ? Array.prototype.slice.call(deck.querySelectorAll(".doc-card")) : [];
  var wideMQ = window.matchMedia("(min-width: 900px)");
  var use3d = !reduce && cards.length > 0 && wideMQ.matches;
  if (use3d) docs.classList.add("is-3d");

  function updateBand() {
    if (!bandInner || reduce) return;
    var r = bandInner.getBoundingClientRect();
    var vh = window.innerHeight;
    // 0 while the band sits at the bottom of the viewport, 1 once it has risen in
    var p = clamp((vh - r.top) / (vh * 0.7), 0, 1);
    bandInner.style.setProperty("--grow", easeOutCubic(p).toFixed(3));
  }

  function updateDocs() {
    if (!use3d) return;
    var rect = docs.getBoundingClientRect();
    var total = docs.offsetHeight - window.innerHeight;
    var scrolled = clamp(-rect.top, 0, total);
    var g = total > 0 ? scrolled / total : 0;
    var N = cards.length;
    // Ease the fractional index so each brief dwells in the spotlight, then turns.
    var raw = g * (N - 1);
    var base = Math.floor(raw);
    var t = base + easeInOutCubic(clamp(raw - base, 0, 1));
    for (var i = 0; i < N; i++) {
      var local = t - i, x, ry, z, sc, op, br, zi, p, q;
      if (local >= 0) {
        // active (0) -> passed: peels right and turns to face the new doc
        p = Math.min(local, 1.5);
        x = p * 400; ry = -p * 54; z = -p * 210; sc = 1 - p * 0.08;
        op = p <= 1 ? 1 : clamp(1 - (p - 1) / 0.5, 0, 1);
        br = 1 - Math.min(p, 1) * 0.5;
        zi = 200 - Math.round(p * 12);
      } else {
        // upcoming: queued behind, receding harder and dimming into shadow
        q = Math.min(-local, 4);
        x = -q * 40; ry = q * 8; z = -q * 200; sc = 1 - q * 0.06;
        op = clamp(1 - q * 0.36, 0, 1);
        br = 1 - Math.min(q, 2) * 0.3;
        zi = 200 - Math.round(q * 12);
      }
      var c = cards[i];
      c.style.transform = "translate3d(" + x.toFixed(1) + "px, -50%, " + z.toFixed(1) + "px) rotateY(" + ry.toFixed(1) + "deg) scale(" + sc.toFixed(3) + ")";
      c.style.opacity = op.toFixed(3);
      c.style.filter = "brightness(" + br.toFixed(3) + ")";
      c.style.zIndex = String(zi);
    }
  }

  function clearDocs() {
    cards.forEach(function (c) {
      c.style.transform = ""; c.style.opacity = ""; c.style.filter = ""; c.style.zIndex = "";
    });
  }

  var ticking = false;
  function onScrollFx() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { updateBand(); updateDocs(); ticking = false; });
  }

  updateBand();
  updateDocs();
  window.addEventListener("scroll", onScrollFx, { passive: true });
  window.addEventListener("resize", function () {
    var should = !reduce && cards.length > 0 && wideMQ.matches;
    if (should && !use3d) { use3d = true; docs.classList.add("is-3d"); }
    else if (!should && use3d) { use3d = false; docs.classList.remove("is-3d"); clearDocs(); }
    onScrollFx();
  }, { passive: true });
})();
