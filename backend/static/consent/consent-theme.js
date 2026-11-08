/* Theme choice, applied before the page paints.

   This file is loaded synchronously in <head>, without `defer`: a deferred
   script would run after first paint and the reader would see the device theme
   flash before their own choice takes over. It stays an external file so the
   page keeps a Content-Security-Policy with no inline script. */
(function () {
  "use strict";

  var STORAGE_KEY = "hllama-consent-theme";
  var MODES = ["auto", "light", "dark"];

  function stored() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      return MODES.indexOf(value) === -1 ? "auto" : value;
    } catch (error) {
      // Private windows and blocked site data throw here; the device theme is
      // a perfectly good answer.
      return "auto";
    }
  }

  function apply(mode) {
    var root = document.documentElement;
    if (mode === "auto") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", mode);
    }
  }

  var current = stored();
  apply(current);

  window.ConsentTheme = {
    modes: MODES,

    current: function () {
      return current;
    },

    set: function (mode) {
      if (MODES.indexOf(mode) === -1) return;
      current = mode;
      apply(mode);
      try {
        window.localStorage.setItem(STORAGE_KEY, mode);
      } catch (error) {
        // The choice still applies to this page; it just will not be remembered.
      }
    }
  };
})();
