/* Cachet landing v2 — motion. Vanilla, zero dependencies.
 * Examination sequence, scroll reveals, count-up, sticky nav, pointer tilt.
 * Degrades: no JS keeps all content visible; reduced-motion shows final states. */
(function () {
  "use strict";

  /* reloads land at the top, never a restored position */
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";
  if (!location.hash) {
    var toTop = function () {
      var de = document.documentElement, prev = de.style.scrollBehavior;
      de.style.scrollBehavior = "auto"; window.scrollTo(0, 0); de.style.scrollBehavior = prev;
    };
    toTop(); window.addEventListener("load", toTop);
  }

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hasIO = "IntersectionObserver" in window;

  /* ---- count-up ---- */
  function countUp(el) {
    var target = parseInt(el.getAttribute("data-countup"), 10) || 0;
    if (reduce) { el.textContent = String(target); return; }
    var dur = 1200, start = null, ease = function (t) { return 1 - Math.pow(1 - t, 3); };
    (function tick(now) {
      if (start === null) start = now;
      var t = Math.min(1, (now - start) / dur);
      el.textContent = String(Math.round(ease(t) * target));
      if (t < 1) requestAnimationFrame(tick);
    })(performance.now());
  }

  /* ---- reveals (data-rise + data-ledger) ---- */
  var rises = document.querySelectorAll("[data-rise], [data-ledger]");
  if (reduce || !hasIO) {
    rises.forEach(function (el) { el.classList.add("is-visible"); });
    document.querySelectorAll("[data-ledger] [data-countup]").forEach(countUp);
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("is-visible");
        var c = e.target.matches("[data-ledger]") ? e.target.querySelector("[data-countup]") : null;
        if (c) countUp(c);
        io.unobserve(e.target);
      });
    }, { threshold: 0.18, rootMargin: "0px 0px -8% 0px" });
    rises.forEach(function (el) { io.observe(el); });
  }

  /* ---- sticky nav ---- */
  var nav = document.querySelector(".nav");
  if (nav) {
    var onScroll = function () { nav.classList.toggle("scrolled", window.scrollY > 8); };
    onScroll(); window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---- the examination ---- */
  var exhibit = document.querySelector("[data-exam]");
  if (exhibit) {
    var sheet = exhibit.querySelector(".exhibit-sheet");
    var cites = exhibit.querySelectorAll("[data-cite]");
    var heroTally = exhibit.querySelector("[data-countup]");

    var finalState = function () {
      exhibit.classList.add("is-done");
      cites.forEach(function (c) {
        if (c.hasAttribute("data-fabricated")) c.classList.add("is-flagged");
        else c.classList.add("checked");
      });
      if (heroTally) heroTally.textContent = heroTally.getAttribute("data-countup");
    };

    if (reduce || !hasIO) {
      finalState();
    } else {
      if (sheet) exhibit.style.setProperty("--scan-end", (sheet.offsetHeight - 36) + "px");
      var play = function () {
        exhibit.classList.add("is-examining");
        // verified cites tick as the scan passes them
        var verified = [].filter.call(cites, function (c) { return !c.hasAttribute("data-fabricated"); });
        verified.forEach(function (c, i) {
          setTimeout(function () { c.classList.add("checked"); }, 700 + i * 520);
        });
        // the fabricated one is caught at the end of the sweep
        var fab = exhibit.querySelector("[data-fabricated]");
        setTimeout(function () { if (fab) fab.classList.add("is-flagged"); }, 1750);
        // verdict + tally resolve
        setTimeout(function () {
          exhibit.classList.add("is-done");
          if (heroTally) countUp(heroTally);
        }, 2050);
      };
      // start once the hero rise has settled; only once
      var started = false;
      var kick = function () { if (started) return; started = true; setTimeout(play, 650); };
      var inView = function () {
        var r = exhibit.getBoundingClientRect();
        return r.top < window.innerHeight * 0.65 && r.bottom > 0;
      };
      // above the fold: play on load. otherwise wait for it to scroll into view.
      if (inView()) {
        kick();
      } else if (hasIO) {
        var exIO = new IntersectionObserver(function (entries) {
          entries.forEach(function (e) { if (e.isIntersecting) { kick(); exIO.disconnect(); } });
        }, { threshold: 0.35 });
        exIO.observe(exhibit);
      } else { kick(); }
    }
  }

  /* ---- pointer tilt on the exhibit (fine pointer, motion allowed) ---- */
  var tilt = document.querySelector("[data-tilt]");
  if (tilt && !reduce && window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    var raf = null;
    var onMove = function (ev) {
      if (raf) return;
      raf = requestAnimationFrame(function () {
        raf = null;
        var r = tilt.getBoundingClientRect();
        var px = (ev.clientX - r.left) / r.width - 0.5;   // -0.5..0.5
        var py = (ev.clientY - r.top) / r.height - 0.5;
        tilt.style.setProperty("--rx", (px * 6).toFixed(2));
        tilt.style.setProperty("--ry", (py * 6).toFixed(2));
      });
    };
    var reset = function () { tilt.style.setProperty("--rx", "0"); tilt.style.setProperty("--ry", "0"); };
    tilt.addEventListener("mousemove", onMove);
    tilt.addEventListener("mouseleave", reset);
  }
})();
