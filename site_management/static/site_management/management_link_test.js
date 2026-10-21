(function () {
  function isSafeTestDestination(value) {
    var destination = value.trim();
    if (/^\/(?!\/)\S*$/.test(destination) || /^#\S*$/.test(destination)) {
      return true;
    }
    try {
      var parsed = new URL(destination);
      return (
        (parsed.protocol === "http:" || parsed.protocol === "https:") &&
        Boolean(parsed.hostname) &&
        !parsed.username &&
        !parsed.password
      );
    } catch (error) {
      return false;
    }
  }

  function addTestLink(input) {
    var link = document.createElement("a");
    link.className = "management-test-link";
    link.textContent = "Test link ↗";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.style.marginLeft = "0.6rem";
    link.hidden = true;
    input.insertAdjacentElement("afterend", link);

    function updateLink() {
      var value = input.value || "";
      if (isSafeTestDestination(value)) {
        link.href = value.trim();
        link.hidden = false;
      } else {
        link.removeAttribute("href");
        link.hidden = true;
      }
    }

    input.addEventListener("input", updateLink);
    input.addEventListener("change", updateLink);
    updateLink();
  }

  document
    .querySelectorAll('[data-test-link], input[name="url"], input[name$="_url"]')
    .forEach(addTestLink);
})();
