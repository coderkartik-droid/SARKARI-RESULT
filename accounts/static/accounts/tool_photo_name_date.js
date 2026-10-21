(function () {
  "use strict";

  var SUPPORTED_MIME = ["image/jpeg", "image/png"];
  var SUPPORTED_EXT = ["jpg", "jpeg", "png"];
  var MAX_CANVAS = 4096;

  var SIZE_FACTORS = { small: 0.045, medium: 0.06, large: 0.08 };
  var COLORS = {
    white: { fill: "#ffffff", strip: "rgba(0, 0, 0, 0.52)", outline: "rgba(0, 0, 0, 0.6)" },
    black: { fill: "#111111", strip: "rgba(255, 255, 255, 0.78)", outline: "rgba(255, 255, 255, 0.85)" },
    saffron: { fill: "#ff6b35", strip: "rgba(0, 0, 0, 0.52)", outline: "rgba(0, 0, 0, 0.6)" },
    navy: { fill: "#1e3a5f", strip: "rgba(255, 255, 255, 0.78)", outline: "rgba(255, 255, 255, 0.85)" }
  };

  function byId(id) { return document.getElementById(id); }

  var fileInput = byId("nd-file");
  var errorBox = byId("nd-error");
  var emptyState = byId("nd-empty");
  var workspace = byId("nd-workspace");
  var canvas = byId("nd-canvas");
  var nameInput = byId("nd-name");
  var dateInput = byId("nd-date");
  var positionSel = byId("nd-position");
  var sizeSel = byId("nd-size");
  var colorSel = byId("nd-color");
  var formatSel = byId("nd-format");
  var stripInput = byId("nd-strip");
  var downloadLink = byId("nd-download");
  var resetBtn = byId("nd-reset");
  var removeBtn = byId("nd-remove");
  if (!fileInput) { return; }

  var ctx = canvas.getContext("2d");
  var image = null;
  var objectUrl = null;
  var downloadUrl = null;

  function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; }
  function clearError() { errorBox.textContent = ""; errorBox.hidden = true; }
  function isSupported(file) {
    if (SUPPORTED_MIME.indexOf(file.type) !== -1) { return true; }
    var name = (file.name || "").toLowerCase();
    var ext = name.indexOf(".") !== -1 ? name.split(".").pop() : "";
    return SUPPORTED_EXT.indexOf(ext) !== -1;
  }
  function todayString() {
    var d = new Date();
    var day = String(d.getDate()).padStart(2, "0");
    var month = String(d.getMonth() + 1).padStart(2, "0");
    return day + "/" + month + "/" + d.getFullYear();
  }
  function resetDownload() {
    if (downloadUrl) { URL.revokeObjectURL(downloadUrl); downloadUrl = null; }
    downloadLink.removeAttribute("href");
  }

  function draw() {
    if (!image) { return; }
    var naturalW = image.naturalWidth;
    var naturalH = image.naturalHeight;
    var scale = Math.min(1, MAX_CANVAS / Math.max(naturalW, naturalH));
    var w = Math.max(1, Math.round(naturalW * scale));
    var h = Math.max(1, Math.round(naturalH * scale));
    canvas.width = w;
    canvas.height = h;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(image, 0, 0, w, h);

    var name = nameInput.value.trim();
    var date = dateInput.value.trim();
    var lines = [];
    if (name) { lines.push(name); }
    if (date) { lines.push(date); }

    clearError();
    if (!name && !date) {
      showError("Enter a name, a date, or both to add a label to your photo.");
    }

    if (lines.length) {
      var colors = COLORS[colorSel.value] || COLORS.white;
      var factor = SIZE_FACTORS[sizeSel.value] || SIZE_FACTORS.medium;
      var fontSize = Math.max(14, Math.round(w * factor));
      var lineHeight = fontSize * 1.35;
      var padding = fontSize * 0.7;
      var blockHeight = lines.length * lineHeight;
      var stripHeight = Math.min(h, blockHeight + padding * 1.4);
      var stripTop = positionSel.value === "top" ? 0 : h - stripHeight;

      if (stripInput.checked) {
        ctx.fillStyle = colors.strip;
        ctx.fillRect(0, stripTop, w, stripHeight);
      }

      ctx.font = "600 " + fontSize + "px system-ui, -apple-system, Segoe UI, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineWidth = Math.max(1, fontSize * 0.07);
      ctx.strokeStyle = colors.outline;
      ctx.fillStyle = colors.fill;

      var maxWidth = Math.max(20, w - padding * 2);
      var startCenter = stripTop + (stripHeight - blockHeight) / 2 + lineHeight / 2;
      for (var i = 0; i < lines.length; i++) {
        var y = startCenter + i * lineHeight;
        ctx.strokeText(lines[i], w / 2, y, maxWidth);
        ctx.fillText(lines[i], w / 2, y, maxWidth);
      }
    }

    updateDownload();
  }

  function updateDownload() {
    var mime = formatSel.value;
    var quality = mime === "image/jpeg" ? 0.92 : undefined;
    canvas.toBlob(function (blob) {
      if (!blob) { return; }
      if (downloadUrl) { URL.revokeObjectURL(downloadUrl); }
      downloadUrl = URL.createObjectURL(blob);
      downloadLink.href = downloadUrl;
      var ext = mime === "image/png" ? "png" : "jpg";
      downloadLink.setAttribute("download", "photo-name-date." + ext);
    }, mime, quality);
  }

  function loadFile(file) {
    clearError();
    resetDownload();
    if (!file) { return; }
    if (!isSupported(file)) {
      showError("Unsupported file. Please choose a JPG, JPEG or PNG image.");
      return;
    }
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    objectUrl = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      image = img;
      workspace.hidden = false;
      emptyState.hidden = true;
      draw();
    };
    img.onerror = function () {
      showError("This image could not be read. Please try a different file.");
    };
    img.src = objectUrl;
  }

  function applyDefaults() {
    nameInput.value = "";
    dateInput.value = todayString();
    positionSel.value = "bottom";
    sizeSel.value = "medium";
    colorSel.value = "white";
    formatSel.value = "image/png";
    stripInput.checked = true;
  }

  fileInput.addEventListener("change", function () {
    applyDefaults();
    loadFile(fileInput.files && fileInput.files[0]);
  });

  [nameInput, dateInput].forEach(function (el) { el.addEventListener("input", draw); });
  [positionSel, sizeSel, colorSel, stripInput].forEach(function (el) { el.addEventListener("change", draw); });
  formatSel.addEventListener("change", updateDownload);

  resetBtn.addEventListener("click", function () {
    if (!image) { return; }
    applyDefaults();
    draw();
  });

  removeBtn.addEventListener("click", function () {
    fileInput.value = "";
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    image = null;
    canvas.width = 0;
    canvas.height = 0;
    resetDownload();
    workspace.hidden = true;
    emptyState.hidden = false;
    clearError();
    applyDefaults();
  });
})();
