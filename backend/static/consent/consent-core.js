/* Shared state for the consent page.

   The page can replace its own content when the language changes, so anything
   that binds to the DOM registers through `onMount` and is re-run after a swap.
   No bundler here on purpose: three small files, loaded in order, each with one
   responsibility. */
window.ConsentCore = (function () {
  "use strict";

  var body = document.body;
  var mounts = [];
  var strings = readStrings(document);

  function readStrings(root) {
    var node = root.querySelector("[data-strings]");
    if (!node) return {};
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      console.error("consent: unreadable strings block", error);
      return {};
    }
  }

  return {
    token: new URLSearchParams(window.location.search).get("t"),
    apiPath: body.getAttribute("data-api-path") || "/api/consent",
    waNumber: body.getAttribute("data-wa-number") || "",

    text: function (key) {
      return typeof strings[key] === "string" ? strings[key] : "";
    },

    refreshStrings: function (root) {
      strings = readStrings(root);
    },

    /* Register a binder and run it now; it runs again after every swap. */
    onMount: function (binder) {
      mounts.push(binder);
      binder();
    },

    remount: function () {
      mounts.forEach(function (binder) {
        try {
          binder();
        } catch (error) {
          console.error("consent: remount failed", error);
        }
      });
    }
  };
})();
