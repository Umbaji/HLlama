/* The decision itself: accept, refuse, and every state around them.

   The page reads fine without this file; it only adds the choice. */
(function (core) {
  "use strict";

  var REDIRECT_SECONDS = 5;

  var countdownTimer = null;

  /* The link only reopens the conversation. It used to carry a sentence she had
     to send about herself ("J'ai donne mon consentement"), which the bot matched
     character for character to reply; the backend now pushes that reply as soon
     as the decision is recorded. The bot still recognises the old sentence, for
     links already in circulation. */
  function whatsappUrl() {
    return "https://wa.me/" + core.waNumber;
  }

  function panel(status, kind, title, bodyText) {
    var wrapper = document.createElement("div");
    wrapper.className = "c-panel c-panel--" + kind;

    var heading = document.createElement("p");
    heading.className = "c-panel__title";
    heading.textContent = title;

    var paragraph = document.createElement("p");
    paragraph.className = "c-panel__body";
    paragraph.textContent = bodyText;

    wrapper.appendChild(heading);
    wrapper.appendChild(paragraph);
    status.replaceChildren(wrapper);
    return wrapper;
  }

  function bind() {
    var checkbox = document.querySelector("[data-check]");
    var acceptBtn = document.querySelector("[data-accept]");
    var refuseBtn = document.querySelector("[data-refuse]");
    var acceptHint = document.querySelector("[data-accept-hint]");
    var statusEl = document.querySelector("[data-status]");
    var choiceEl = document.querySelector("[data-choice]");
    if (!checkbox || !acceptBtn || !refuseBtn || !statusEl) return;

    // The server already hid the choice and explained why when the link cannot
    // record a decision; there is nothing to bind in that case.
    if (!core.token || (choiceEl && choiceEl.hidden)) return;

    var syncAcceptState = function () {
      acceptBtn.disabled = !checkbox.checked;
      acceptHint.hidden = checkbox.checked;
    };

    var setBusy = function (isBusy) {
      document.body.dataset.busy = String(isBusy);
      [acceptBtn, refuseBtn].forEach(function (button) {
        button.disabled = isBusy || (button === acceptBtn && !checkbox.checked);
        button.setAttribute("aria-busy", String(isBusy));
      });
    };

    var showSuccess = function (decision) {
      var accepted = decision === "accepted";
      var box = panel(
        statusEl,
        "success",
        core.text(accepted ? "success_accepted_title" : "success_refused_title"),
        core.text(accepted ? "success_accepted_body" : "success_refused_body")
      );
      choiceEl.hidden = true;
      if (!core.waNumber) return;

      var actions = document.createElement("div");
      actions.className = "c-panel__actions";
      var link = document.createElement("a");
      link.className = "c-link";
      link.href = whatsappUrl();
      link.textContent = core.text("redirect_manual");
      var countdown = document.createElement("span");
      countdown.className = "c-panel__countdown";
      actions.appendChild(link);
      actions.appendChild(countdown);
      box.appendChild(actions);

      var hint = document.createElement("p");
      hint.className = "c-panel__countdown";
      hint.textContent = core.text("redirect_blocked");
      box.appendChild(hint);
      link.focus();

      // The automatic redirect is a convenience, never the only way out: in-app
      // browsers regularly block it, which used to leave the page stuck.
      var remaining = REDIRECT_SECONDS;
      var tick = function () {
        countdown.textContent = core.text("redirect_countdown").replace("{seconds}", String(remaining));
      };
      tick();
      countdownTimer = window.setInterval(function () {
        remaining -= 1;
        if (remaining > 0) return tick();
        window.clearInterval(countdownTimer);
        window.location.href = link.href;
      }, 1000);
    };

    var showError = function (messageText, canRetry, retry) {
      var box = panel(statusEl, "error", core.text("error_title"), messageText);
      if (!canRetry) return;

      var actions = document.createElement("div");
      actions.className = "c-panel__actions";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "c-btn c-btn--ghost c-btn--compact";
      button.textContent = core.text("retry_label");
      button.addEventListener("click", retry);
      actions.appendChild(button);
      box.appendChild(actions);
      button.focus();
    };

    var submit = function (decision, button) {
      var original = Array.prototype.map.call(button.childNodes, function (node) {
        return node.cloneNode(true);
      });
      var restore = function () {
        button.replaceChildren.apply(button, original);
        setBusy(false);
        syncAcceptState();
      };

      setBusy(true);
      statusEl.replaceChildren();
      var spinner = document.createElement("span");
      spinner.className = "c-spinner";
      button.replaceChildren(spinner, document.createTextNode(core.text("submitting")));

      if (!navigator.onLine) {
        restore();
        showError(core.text("error_offline"), true, function () { submit(decision, button); });
        return;
      }

      fetch(core.apiPath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: core.token, decision: decision })
      })
        .then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          if (result.ok) return showSuccess(decision);

          var code = result.data && typeof result.data.message === "string" ? result.data.message : "";
          // A dead link and a spent one cannot be retried: a new link is the
          // only way forward, so no retry button is offered.
          var messages = {
            CONSENT_TOKEN_INVALID: core.text("error_invalid_token"),
            CONSENT_TOKEN_ALREADY_USED: core.text("error_already_used")
          };
          var terminal = Object.prototype.hasOwnProperty.call(messages, code);
          restore();
          if (terminal) choiceEl.hidden = true;
          showError(
            terminal ? messages[code] : core.text("error_generic"),
            !terminal,
            function () { submit(decision, button); }
          );
        })
        .catch(function (error) {
          console.error("consent: submission failed", error);
          restore();
          showError(core.text("error_network"), true, function () { submit(decision, button); });
        });
    };

    checkbox.addEventListener("change", syncAcceptState);
    acceptBtn.addEventListener("click", function () { submit("accepted", acceptBtn); });
    refuseBtn.addEventListener("click", function () { submit("refused", refuseBtn); });
    syncAcceptState();
  }

  core.onMount(bind);
})(window.ConsentCore);
