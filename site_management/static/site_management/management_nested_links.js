/* Dynamic "Add URL" entries for the shared content editor.
 *
 * One script drives every nested-entry formset: it adds rows from the
 * server-rendered empty form, removes rows (without touching the others),
 * reorders them, and shows only the inputs that match the selected content
 * type (Icon / Link / Text). No inline JavaScript is used, so the management
 * templates stay CSP- and XSS-safe.
 */
(function () {
  "use strict";

  // Which inputs matter for each content type. Everything else is hidden but
  // still submitted, so switching type never destroys a saved value.
  var VISIBLE_FIELDS = {
    icon: ["label", "url", "image", "icon", "open_new_tab"],
    link: ["label", "url", "open_new_tab"],
    text: ["label"]
  };
  var ALWAYS_VISIBLE = ["link_type", "is_active"];

  function applyType(row) {
    var select = row.querySelector('select[name$="-link_type"]');
    if (!select) {
      return;
    }
    var allowed = VISIBLE_FIELDS[select.value] || VISIBLE_FIELDS.link;
    row.querySelectorAll("[data-link-field]").forEach(function (field) {
      var name = field.getAttribute("data-link-field");
      var show =
        ALWAYS_VISIBLE.indexOf(name) !== -1 || allowed.indexOf(name) !== -1;
      field.classList.toggle("management-link-field-hidden", !show);
    });
  }

  function renumber(list) {
    list.querySelectorAll("[data-link-row]").forEach(function (row, index) {
      var order = row.querySelector('input[name$="-display_order"]');
      if (order) {
        order.value = index;
      }
    });
  }

  function initRow(row) {
    var select = row.querySelector('select[name$="-link_type"]');
    if (select && !select.dataset.linkTypeBound) {
      select.dataset.linkTypeBound = "true";
      select.addEventListener("change", function () {
        applyType(row);
      });
    }
    applyType(row);
  }

  function initList(list) {
    list.querySelectorAll("[data-link-row]").forEach(initRow);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-link-list]").forEach(initList);
  });

  document.addEventListener("click", function (event) {
    var target = event.target;

    var removeButton = target.closest("[data-link-remove]");
    if (removeButton) {
      event.preventDefault();
      var row = removeButton.closest("[data-link-row]");
      if (!row) {
        return;
      }
      var idInput = row.querySelector('input[name$="-id"]');
      var deleteBox = row.querySelector('input[name$="-DELETE"]');
      if (idInput && idInput.value && deleteBox) {
        // Saved entry: mark it for deletion instead of dropping the row.
        deleteBox.checked = true;
        row.hidden = true;
      } else {
        var list = row.closest("[data-link-list]");
        row.remove();
        if (list) {
          renumber(list);
        }
      }
      return;
    }

    var moveButton = target.closest("[data-link-move]");
    if (moveButton) {
      event.preventDefault();
      var moveRow = moveButton.closest("[data-link-row]");
      var moveList = moveRow && moveRow.closest("[data-link-list]");
      if (!moveList) {
        return;
      }
      if (moveButton.getAttribute("data-link-move") === "up") {
        var previous = moveRow.previousElementSibling;
        if (previous) {
          moveList.insertBefore(moveRow, previous);
        }
      } else {
        var next = moveRow.nextElementSibling;
        if (next) {
          moveList.insertBefore(next, moveRow);
        }
      }
      renumber(moveList);
      return;
    }

    var addButton = target.closest("[data-link-add]");
    if (addButton) {
      event.preventDefault();
      var details = addButton.closest("details");
      if (!details) {
        return;
      }
      var addList = details.querySelector("[data-link-list]");
      var template = details.querySelector("template[data-link-empty-template]");
      var totalInput = details.querySelector('input[name$="-TOTAL_FORMS"]');
      if (!addList || !template || !totalInput) {
        return;
      }
      var index = parseInt(totalInput.value, 10) || 0;
      var markup = template.innerHTML.replace(/__prefix__/g, index);
      var holder = document.createElement("div");
      holder.innerHTML = markup.trim();
      var newRow = holder.querySelector("[data-link-row]");
      if (!newRow) {
        return;
      }
      addList.appendChild(newRow);
      totalInput.value = index + 1;
      initRow(newRow);
    }
  });
})();
