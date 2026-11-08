/* Reading aids and the language toggle.

   The toggle swaps the page content in place rather than reloading: on a mobile
   connection a reload means a blank screen and a lost scroll position. Any
   failure falls back to following the link normally. */
(function (core) {
  "use strict";

  var SWAP_FADE_MS = 160;

  function buildTableOfContents() {
    var nav = document.querySelector("[data-toc]");
    var list = document.querySelector("[data-toc-list]");
    var headings = document.querySelectorAll(".c-policy .c-article > h2[id]");
    if (!nav || !list || headings.length === 0) return;

    list.replaceChildren();
    headings.forEach(function (heading) {
      var label = heading.cloneNode(true);
      var number = label.querySelector(".c-article__num");
      if (number) number.remove();

      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = "#" + heading.id;
      link.textContent = label.textContent.trim();
      item.appendChild(link);
      list.appendChild(item);
    });
    nav.hidden = false;
  }

  function trackReadingProgress() {
    var fill = document.querySelector("[data-progress-fill]");
    var meter = document.querySelector("[data-progress]");
    var policy = document.getElementById("policy");
    if (!fill || !meter || !policy) return;

    var scheduled = false;
    var update = function () {
      scheduled = false;
      var span = policy.offsetHeight - window.innerHeight;
      var ratio = span <= 0 ? 1 : (window.scrollY - policy.offsetTop) / span;
      var percent = Math.max(0, Math.min(100, Math.round(ratio * 100)));
      fill.style.width = percent + "%";
      meter.setAttribute("aria-valuenow", String(percent));
    };

    if (!trackReadingProgress.bound) {
      window.addEventListener("scroll", function () {
        if (scheduled) return;
        scheduled = true;
        window.requestAnimationFrame(update);
      }, { passive: true });
      trackReadingProgress.bound = true;
    }
    update();
  }

  function trackJumpButton() {
    var jump = document.querySelector("[data-jump]");
    var decision = document.getElementById("decision");
    if (!jump || !decision || !("IntersectionObserver" in window)) return;

    if (trackJumpButton.observer) trackJumpButton.observer.disconnect();
    trackJumpButton.observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        jump.hidden = entry.isIntersecting || window.scrollY < 240;
      });
    }, { rootMargin: "-20% 0px -20% 0px" });
    trackJumpButton.observer.observe(decision);

    if (!trackJumpButton.bound) {
      window.addEventListener("scroll", function () {
        if (window.scrollY < 240) jump.hidden = true;
      }, { passive: true });
      trackJumpButton.bound = true;
    }
  }

  /* The server never sees the token, so the language links cannot carry it. */
  function keepToken(link) {
    if (!core.token) return;
    var url = new URL(link.getAttribute("href"), window.location.href);
    url.searchParams.set("t", core.token);
    link.setAttribute("href", url.pathname + url.search);
  }

  /* The control itself is never replaced: only its state changes, so the pill
     slides instead of jumping to its new position. */
  function markActive(control, items, language) {
    control.setAttribute("data-lang-active", language);
    items.forEach(function (item) {
      if (item.getAttribute("hreflang") === language) {
        item.setAttribute("aria-current", "true");
      } else {
        item.removeAttribute("aria-current");
      }
    });
  }

  function swapLanguage(link, control, items, language) {
    var url = link.getAttribute("href");
    markActive(control, items, language);
    document.body.classList.add("is-swapping");

    fetch(url, { headers: { Accept: "text/html" } })
      .then(function (response) {
        if (!response.ok) throw new Error("status " + response.status);
        return response.text();
      })
      .then(function (html) {
        var parsed = new DOMParser().parseFromString(html, "text/html");
        var nextMain = parsed.querySelector(".c-main");
        if (!nextMain) throw new Error("unexpected document");

        window.setTimeout(function () {
          document.documentElement.lang = parsed.documentElement.lang;
          document.title = parsed.title;
          document.querySelector(".c-main").replaceWith(document.importNode(nextMain, true));

          // Everything outside <main> that carries words: the brand line reads
          // "par Umbaji" in French and "by Umbaji" in English, and the skip link
          // and footer are translated too. The brand name itself never changes.
          [".c-brand__text", ".c-skip", ".c-footer"].forEach(function (selector) {
            var next = parsed.querySelector(selector);
            var current = document.querySelector(selector);
            if (next && current) current.replaceWith(document.importNode(next, true));
          });

          core.refreshStrings(parsed);
          window.history.replaceState(null, "", url);
          document.body.classList.remove("is-swapping");
          core.remount();
        }, SWAP_FADE_MS);
      })
      .catch(function (error) {
        console.error("consent: language swap failed, navigating instead", error);
        window.location.href = url;
      });
  }

  function bindLanguageToggle() {
    var control = document.querySelector(".c-lang");
    if (!control) return;
    var items = Array.prototype.slice.call(control.querySelectorAll("[data-langswitch]"));

    items.forEach(function (link) {
      keepToken(link);
      link.addEventListener("click", function (event) {
        var language = link.getAttribute("hreflang");
        if (event.metaKey || event.ctrlKey || event.shiftKey) return;
        event.preventDefault();
        if (link.getAttribute("aria-current") === "true" || document.body.dataset.busy === "true") return;
        swapLanguage(link, control, items, language);
      });
    });
  }

  // Bound once: the language control survives a swap, its listeners with it.
  bindLanguageToggle();

  /* The control is revealed only once the script is running: without it the
     buttons could not switch anything, and a dead control is worse than none.
     The footer is replaced on a language swap, so this rebinds on every mount. */
  function bindThemeControl() {
    var theme = window.ConsentTheme;
    var control = document.querySelector("[data-theme-control]");
    if (!theme || !control) return;

    var options = Array.prototype.slice.call(control.querySelectorAll("[data-theme-mode]"));
    var sync = function () {
      options.forEach(function (option) {
        var active = option.getAttribute("data-theme-mode") === theme.current();
        option.setAttribute("aria-checked", String(active));
        option.tabIndex = active ? 0 : -1;
      });
    };

    options.forEach(function (option) {
      option.addEventListener("click", function () {
        theme.set(option.getAttribute("data-theme-mode"));
        sync();
      });
    });

    sync();
    control.hidden = false;
  }

  core.onMount(function () {
    bindThemeControl();
    buildTableOfContents();
    trackReadingProgress();
    trackJumpButton();
  });
})(window.ConsentCore);
