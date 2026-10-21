(function () {
  var sidebar = document.getElementById("management-sidebar");
  var overlay = document.getElementById("management-sidebar-overlay");
  var openButton = document.getElementById("management-menu-button");
  var closeButton = document.getElementById("management-sidebar-close");

  function openSidebar() {
    if (!sidebar) { return; }
    sidebar.classList.add("is-open");
    if (overlay) { overlay.hidden = false; }
    if (openButton) { openButton.setAttribute("aria-expanded", "true"); }
  }

  function closeSidebar() {
    if (!sidebar) { return; }
    sidebar.classList.remove("is-open");
    if (overlay) { overlay.hidden = true; }
    if (openButton) { openButton.setAttribute("aria-expanded", "false"); }
  }

  if (openButton) { openButton.addEventListener("click", openSidebar); }
  if (closeButton) { closeButton.addEventListener("click", closeSidebar); }
  if (overlay) { overlay.addEventListener("click", closeSidebar); }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeSidebar(); }
  });

  // Follow a real navigation link -> dismiss the mobile drawer so it never
  // covers the page it just opened.
  document.querySelectorAll(".management-sidebar a").forEach(function (link) {
    link.addEventListener("click", function () { closeSidebar(); });
  });

  document.querySelectorAll(".management-nav-link[data-nav-toggle='true']").forEach(function (button) {
    button.addEventListener("click", function (e) {
      var target = document.getElementById(button.getAttribute("aria-controls"));
      var expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      if (target) { target.hidden = expanded; }
      var parentGroup = button.closest(".management-nav-group");
      if (parentGroup) {
        if (!expanded) {
          parentGroup.classList.add("is-expanded");
        } else {
          parentGroup.classList.remove("is-expanded");
        }
      }
    });
  });
})();
