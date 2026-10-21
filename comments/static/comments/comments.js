document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector(".comments-form");
  const body = form?.querySelector("[data-comment-body]");
  const counter = document.getElementById("comments-character-count");
  const announcement = document.getElementById("comments-character-announcement");
  const submitButton = form?.querySelector("[data-comment-submit]");
  const submitLabel = form?.querySelector("[data-comment-submit-label]");

  if (!form || !body || !counter || !announcement || !submitButton || !submitLabel) {
    return;
  }

  const characterLimit = Number(body.getAttribute("maxlength"));
  let previousRemaining = characterLimit - body.value.length;
  const updateRemainingCharacters = () => {
    const remaining = Math.max(0, characterLimit - body.value.length);
    counter.textContent = `${remaining.toLocaleString()} character${remaining === 1 ? "" : "s"} remaining`;
    if (
      remaining === 0 ||
      (remaining !== characterLimit && remaining % 100 === 0) ||
      (remaining <= 10 && previousRemaining > 10)
    ) {
      announcement.textContent = counter.textContent;
    }
    previousRemaining = remaining;
  };

  body.addEventListener("input", updateRemainingCharacters);
  updateRemainingCharacters();

  form.addEventListener("submit", () => {
    if (!form.reportValidity()) {
      return;
    }

    submitButton.disabled = true;
    submitButton.setAttribute("aria-busy", "true");
    submitLabel.textContent = "Posting...";
  });
});
