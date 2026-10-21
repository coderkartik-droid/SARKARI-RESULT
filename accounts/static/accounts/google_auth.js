/**
 * "Continue with Google" — Google Identity Services (GIS) integration.
 *
 * Flow:
 *  1. Load https://accounts.google.com/gsi/client (done in index.html, only
 *     when a real client id is configured).
 *  2. Render the official GIS button inside #google-btn-container.
 *  3. On successful sign-in Google returns a JWT `credential`.
 *  4. We decode it locally just to preview name/email/picture (NOT for auth),
 *     then POST it to /accounts/google/verify/ where Django verifies the
 *     token server-side and creates a session.
 *
 * The client id is injected server-side into window.GOOGLE_CLIENT_ID
 * (from the .env GOOGLE_CLIENT_ID via index.html).
 */
(function () {
  "use strict";

  var CLIENT_ID = window.GOOGLE_CLIENT_ID || "";
  var VERIFY_URL = window.GOOGLE_VERIFY_URL || "/accounts/google/verify/";
  var PLACEHOLDER = "YOUR_GOOGLE_CLIENT_ID_HERE";

  var statusEl = document.getElementById("google-auth-status");
  var gisButtonReady = false;
  var gisInitializationStarted = false;

  function setClassicFallbackVisible(visible) {
    var legacyForm = document.getElementById("google-login-form");
    var divider = document.getElementById("google-login-divider");
    if (legacyForm) legacyForm.hidden = !visible;
    if (divider) divider.hidden = !visible;
  }

  function clearButtonContainer(container) {
    while (container && container.firstChild) {
      container.removeChild(container.firstChild);
    }
  }

  function setStatus(message, state) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.setAttribute("data-state", state || "");
  }

  function showClassicFallback() {
    var container = document.getElementById("google-btn-container");
    gisButtonReady = false;
    if (container) {
      container.hidden = true;
      container.removeAttribute("data-loading");
      clearButtonContainer(container);
    }
    setClassicFallbackVisible(true);
  }

  /**
   * Safely decode a JWT payload (base64url, no signature check).
   * Used ONLY to show a welcome preview in the UI before the server confirms.
   */
  function decodeJwtPayload(token) {
    try {
      var part = token.split(".")[1];
      part += "=".repeat((4 - (part.length % 4)) % 4);
      return JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/")));
    } catch (err) {
      return {};
    }
  }

  /**
   * Credential callback: fires when Google completes sign-in.
   * SECURITY: the JWT is verified on the backend; anything decoded here is
   * cosmetic (welcome text, avatar) until the server responds ok.
   */
  function handleCredentialResponse(response) {
    var credential = response && response.credential;
    if (!credential) {
      setStatus("Google sign-in did not return a credential.", "error");
      return;
    }

    // Local (unverified) decode for the welcome preview only.
    var claims = decodeJwtPayload(credential);
    var user = {
      name: claims.name || "",
      email: claims.email || "",
      picture: claims.picture || "",
    };
    // Store locally so the UI can greet returning visitors (cosmetic only).
    try {
      localStorage.setItem("google_user_profile", JSON.stringify(user));
    } catch (err) {
      /* storage may be unavailable — non-fatal */
    }
    showWelcomePreview(user);
    setStatus("Signing you in with Google…", "busy");

    var body = new URLSearchParams();
    body.append("credential", credential);
    // Include the hidden "next" value the plain login form also uses.
    var nextInput = document.querySelector('#google-login-form input[name="next"]');
    if (nextInput && nextInput.value) body.append("next", nextInput.value);

    var csrfInput = document.querySelector('#google-login-form input[name="csrfmiddlewaretoken"]');
    if (!csrfInput) {
      setStatus("Security token missing. Please reload the page.", "error");
      return;
    }

    fetch(VERIFY_URL, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfInput.value,
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: body,
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (result.ok && result.data.ok) {
          var verified = result.data.user || user;
          try {
            localStorage.setItem("google_user_profile", JSON.stringify(verified));
          } catch (err) {
            /* non-fatal */
          }
          showWelcomePreview(verified, true);
          setStatus("Signed in! Redirecting…", "success");
          window.location.assign(result.data.redirect || "/");
          return;
        }
        setStatus(result.data.error || "Google sign-in failed.", "error");
      })
      .catch(function () {
        setStatus("Network error during Google sign-in. Please try again.", "error");
      });
  }

  /** Update the UI with the signed-in user info (welcome state). */
  function showWelcomePreview(user, verified) {
    var container = document.getElementById("google-btn-container");
    var welcome = document.getElementById("google-welcome");
    if (!welcome) return;

    var nameEl = welcome.querySelector("[data-google-name]");
    var emailEl = welcome.querySelector("[data-google-email]");
    var picEl = welcome.querySelector("[data-google-picture]");
    if (nameEl) nameEl.textContent = user.name || "Google user";
    if (emailEl) emailEl.textContent = user.email || "";
    if (picEl && user.picture) {
      picEl.src = user.picture;
      picEl.hidden = false;
      picEl.alt = user.name ? user.name + " profile photo" : "Profile photo";
    }
    if (verified) welcome.setAttribute("data-verified", "true");

    if (container) container.hidden = true;
    welcome.hidden = false;
  }

  /** Restore a previous preview (cosmetic) while anonymous. */
  function restoreCachedPreview() {
    try {
      var cached = JSON.parse(localStorage.getItem("google_user_profile") || "null");
      if (cached && cached.name && !document.body.classList.contains("authenticated")) {
        // Only show the card as a reminder; the server session decides auth.
        showWelcomePreview(cached, false);
        var container = document.getElementById("google-btn-container");
        var welcome = document.getElementById("google-welcome");
        if (welcome && container) {
          container.hidden = !gisButtonReady;
          welcome.hidden = false;
          welcome.removeAttribute("data-verified");
        }
      }
    } catch (err) {
      /* ignore */
    }
  }

  function initGoogleButton() {
    if (!window.google || !window.google.accounts || !window.google.accounts.id) {
      setStatus("Google sign-in script failed to load.", "error");
      showClassicFallback();
      return;
    }
    var container = document.getElementById("google-btn-container");
    if (!container) return;
    if (gisButtonReady || gisInitializationStarted) return;

    container.removeAttribute("data-loading");
    clearButtonContainer(container);
    container.hidden = false;
    try {
      gisInitializationStarted = true;
      window.google.accounts.id.initialize({
        client_id: CLIENT_ID,
        callback: handleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
        use_fedcm_for_prompt: true,
        ux_mode: "popup",
        error_callback: function (error) {
          var type = (error && (error.type || error.message)) || "unknown";
          console.warn("[Google Auth] GIS prompt unavailable (%s).", type);
          if (type === "popup_closed" || type === "popup_blocked") {
            setStatus("Google sign-in popup was closed or blocked. Use the redirect sign-in button below.", "error");
            showClassicFallback();
          } else if (type === "missing_client_id" || type === "unregistered_origin") {
            setStatus("Google sign-in is misconfigured for this origin. Use the redirect sign-in button below.", "error");
            showClassicFallback();
          }
        },
      });
      window.google.accounts.id.renderButton(container, {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "pill",
        logo_alignment: "left",
        width: container.clientWidth > 0 ? container.clientWidth : 320,
      });
      gisButtonReady = true;
      container.hidden = false;
      setClassicFallbackVisible(false);
      setStatus("", "");
      window.google.accounts.id.prompt();
    } catch {
      gisInitializationStarted = false;
      console.warn("[Google Auth] GIS initialization failed; using redirect sign-in.");
      setStatus("Google's sign-in button could not be initialized. Use the redirect sign-in button below.", "error");
      showClassicFallback();
    }
  }

  function boot() {
    if (window.__googleAuthBooted) return;
    window.__googleAuthBooted = true;
    var container = document.getElementById("google-btn-container");

    if (!CLIENT_ID || CLIENT_ID === PLACEHOLDER) {
      // Fallback handling: client id still a placeholder / not injected.
      console.warn(
        "[Google Auth] Client ID is not configured. Set GOOGLE_CLIENT_ID in .env " +
        "(obtain it from Google Cloud Console > APIs & Services > Credentials). " +
        "Falling back to the classic OAuth redirect button."
      );
      return; // leave the classic redirect form visible instead
    }

    if (window.google && window.google.accounts && window.google.accounts.id) {
      initGoogleButton();
    } else if (container) {
      container.setAttribute("data-loading", "true");
      setStatus("Loading Google sign-in…", "busy");
      window.addEventListener("load", initGoogleButton);
      // The load event and timeout may race; initGoogleButton is idempotent.
      setTimeout(function () {
        initGoogleButton();
      }, 800);
    }
    restoreCachedPreview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
