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

  /* ---- Sunburst: a fan of fine oxblood rays from a focal point at the base of
   * the dark band. Built procedurally so it stays crisp and weighs nothing. The
   * rays fade in (staggered) when the band scrolls into view; CSS shows them
   * immediately under reduced-motion. ---- */
  var svg = document.querySelector(".sunburst");
  if (svg) {
    var NS = "http://www.w3.org/2000/svg";
    var cx = 450, cy = 320, N = 82, i, a, prox, len, x2, y2, line, dot;
    var center = 1.5 * Math.PI; // straight up
    for (i = 0; i < N; i++) {
      a = Math.PI + (Math.PI * (i + 0.5)) / N;          // PI..2PI = upper hemisphere
      prox = 1 - Math.min(1, Math.abs(a - center) / (Math.PI / 2)); // 1 center, 0 edges
      len = 64 + prox * 232 + (Math.random() * 36 - 18);
      x2 = cx + Math.cos(a) * len;
      y2 = cy + Math.sin(a) * len;
      line = document.createElementNS(NS, "line");
      line.setAttribute("x1", cx); line.setAttribute("y1", cy);
      line.setAttribute("x2", x2.toFixed(1)); line.setAttribute("y2", y2.toFixed(1));
      line.setAttribute("stroke", "#b5616b");
      line.setAttribute("stroke-width", (0.55 + prox * 0.5).toFixed(2));
      line.setAttribute("stroke-linecap", "round");
      line.style.transitionDelay = (0.18 + (i / N) * 0.5).toFixed(2) + "s";
      svg.appendChild(line);
      dot = document.createElementNS(NS, "circle");
      dot.setAttribute("cx", x2.toFixed(1)); dot.setAttribute("cy", y2.toFixed(1));
      dot.setAttribute("r", (1.1 + prox * 1.5 + Math.random() * 0.5).toFixed(2));
      dot.setAttribute("fill", "#cc8a90");
      dot.style.transitionDelay = (0.32 + (i / N) * 0.5).toFixed(2) + "s";
      svg.appendChild(dot);
    }
  }

  /* ---- Dark band reveal: toggles the sunburst draw-in ---- */
  var band = document.querySelector(".band");
  if (band) {
    if (reduce || !hasIO) {
      band.classList.add("is-visible");
    } else {
      var bandIO = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("is-visible"); bandIO.unobserve(e.target); }
        });
      }, { threshold: 0.25 });
      bandIO.observe(band);
    }
  }
})();
