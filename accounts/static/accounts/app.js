const card = document.querySelector("#auth-card");
const loginForm = document.querySelector("#login-form");
const signupForm = document.querySelector("#signup-form");
const loginPanel = document.querySelector(".auth-form--login");
const signupPanel = document.querySelector(".auth-form--signup");
const loginOverlay = document.querySelector(".overlay-content--login");
const signupOverlay = document.querySelector(".overlay-content--signup");

function setMode(mode) {
  const isSignup = mode === "signup";
  card.dataset.mode = isSignup ? "signup" : "login";
  card.setAttribute("aria-label", isSignup ? "Create your Niyukti account" : "Sign in to Niyukti");
  loginPanel.inert = isSignup;
  signupPanel.inert = !isSignup;
  loginPanel.setAttribute("aria-hidden", String(isSignup));
  signupPanel.setAttribute("aria-hidden", String(!isSignup));
  loginOverlay.inert = isSignup;
  signupOverlay.inert = !isSignup;
  loginOverlay.setAttribute("aria-hidden", String(isSignup));
  signupOverlay.setAttribute("aria-hidden", String(!isSignup));
  clearStatus(loginForm);
  clearStatus(signupForm);
  document.querySelector(isSignup ? "#signup-title" : "#login-title").focus({ preventScroll: true });
}

document.querySelectorAll("[data-switch]").forEach((button) => {
  button.addEventListener("click", () => {
    setMode(button.dataset.switch);
  });
});

document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    const isVisible = input.type === "text";
    input.type = isVisible ? "password" : "text";
    button.setAttribute("aria-pressed", String(!isVisible));
    button.setAttribute("aria-label", isVisible ? "Show password" : "Hide password");
    input.focus({ preventScroll: true });
  });
});

function emailIsValid(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function setError(input, message) {
  const error = document.getElementById(`${input.id}-error`);
  error.textContent = message;
  input.setAttribute("aria-invalid", String(Boolean(message)));
}

function clearFormErrors(form) {
  form.querySelectorAll("input").forEach((input) => {
    if (input.type !== "checkbox" && input.type !== "hidden") {
      setError(input, "");
    }
  });
  const termsError = document.querySelector("#signup-terms-error");
  termsError.textContent = "";
  document.querySelector("#accept-terms").removeAttribute("aria-invalid");
}

function setStatus(form, message, state = "info") {
  const status = document.getElementById(`${form.id.replace("-form", "")}-status`);
  status.textContent = message;
  status.dataset.state = state;
}

function clearStatus(form) {
  const status = document.getElementById(`${form.id.replace("-form", "")}-status`);
  status.textContent = "";
  status.removeAttribute("data-state");
}

document.querySelectorAll(".auth-form input").forEach((input) => {
  input.addEventListener("input", () => {
    if (input.type !== "checkbox" && input.getAttribute("aria-invalid") === "true") {
      setError(input, "");
    }
    const statusForm = input.closest("form");
    clearStatus(statusForm);
  });
});

document.querySelector("#accept-terms").addEventListener("change", (event) => {
  if (event.target.checked) {
    document.querySelector("#signup-terms-error").textContent = "";
    event.target.removeAttribute("aria-invalid");
  }
  clearStatus(signupForm);
});

loginForm.addEventListener("submit", (event) => {
  clearFormErrors(loginForm);
  clearStatus(loginForm);

  const identifier = loginForm.elements.username;
  const password = loginForm.elements.password;
  let firstInvalid = null;

  if (!identifier.value.trim()) {
    setError(identifier, "Enter your username or email.");
    firstInvalid = identifier;
  } else if (identifier.value.includes("@") && !emailIsValid(identifier.value.trim())) {
    setError(identifier, "Enter a valid username or email.");
    firstInvalid = identifier;
  }

  if (!password.value) {
    setError(password, "Enter your password.");
    firstInvalid ||= password;
  }

  if (firstInvalid) {
    event.preventDefault();
    setStatus(loginForm, "Please correct the highlighted fields.", "error");
    firstInvalid.focus();
    return;
  }
});

signupForm.addEventListener("submit", (event) => {
  clearFormErrors(signupForm);
  clearStatus(signupForm);

  const username = signupForm.elements.username;
  const email = signupForm.elements.email;
  const password = signupForm.elements.password;
  const confirmation = signupForm.elements.confirmPassword;
  const terms = signupForm.elements.acceptTerms;
  let firstInvalid = null;

  if (!username.value.trim()) {
    setError(username, "Enter a username.");
    firstInvalid = username;
  }

  if (!email.value.trim()) {
    setError(email, "Enter your email address.");
    firstInvalid ||= email;
  } else if (!emailIsValid(email.value.trim())) {
    setError(email, "Enter a valid email address.");
    firstInvalid ||= email;
  }

  if (password.value.length < 8) {
    setError(password, "Password must contain at least 8 characters and one number.");
    firstInvalid ||= password;
  } else if (!/[0-9]/.test(password.value)) {
    setError(password, "Password must contain at least 8 characters and one number.");
    firstInvalid ||= password;
  }

  if (!confirmation.value) {
    setError(confirmation, "Confirm your password.");
    firstInvalid ||= confirmation;
  } else if (password.value !== confirmation.value) {
    setError(confirmation, "These passwords do not match.");
    firstInvalid ||= confirmation;
  }

  if (!terms.checked) {
    document.querySelector("#signup-terms-error").textContent = "Accept the Terms and Privacy Policy to continue.";
    terms.setAttribute("aria-invalid", "true");
    firstInvalid ||= terms;
  }

  if (firstInvalid) {
    event.preventDefault();
    setStatus(signupForm, "Please correct the highlighted fields.", "error");
    firstInvalid.focus();
    return;
  }
});

document.querySelectorAll("[data-policy-link]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    setStatus(signupForm, "Terms and Privacy Policy pages have not been configured yet.");
  });
});
