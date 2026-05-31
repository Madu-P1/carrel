/* Cachet motion — vanilla, zero dependencies.
 * Scroll-reveal (IntersectionObserver), count-up tally, sticky-nav state.
 * Everything degrades: no JS = all content visible; reduced-motion = no movement. */
(function () {
  "use strict";
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
    var dur = 950, start = null;
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
})();
