(function () {
  "use strict";

  var SUPPORTED_MIME = ["image/jpeg", "image/png"];
  var SUPPORTED_EXT = ["jpg", "jpeg", "png"];
  var MIN_DIMENSION = 20;
  var MAX_DIMENSION = 6000;
  var MAX_PIXELS = 40000000; // ~40 MP safety guard

  function byId(id) { return document.getElementById(id); }

  var photoInput = byId("psj-photo");
  var signatureInput = byId("psj-signature");
  var errorBox = byId("psj-error");
  var emptyState = byId("psj-empty");
  var workspace = byId("psj-workspace");
  var photoPreview = byId("psj-photo-preview");
  var signaturePreview = byId("psj-signature-preview");
  var photoDims = byId("psj-photo-dims");
  var signatureDims = byId("psj-signature-dims");
  var layoutSel = byId("psj-layout");
  var widthInput = byId("psj-width");
  var heightInput = byId("psj-height");
  var gapInput = byId("psj-gap");
  var backgroundSel = byId("psj-background");
  var formatSel = byId("psj-format");
  var generateBtn = byId("psj-generate");
  var resetBtn = byId("psj-reset");
  var removeBtn = byId("psj-remove");
  var status = byId("psj-status");
  var outputBox = byId("psj-output");
  var previewImg = byId("psj-preview");
  var downloadLink = byId("psj-download");
  if (!photoInput) { return; }

  var canvas = document.createElement("canvas");
  var ctx = canvas.getContext("2d");
  var photo = { file: null, url: null, img: null, w: 0, h: 0 };
  var signature = { file: null, url: null, img: null, w: 0, h: 0 };
  var outputUrl = null;

  function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; }
  function clearError() { errorBox.textContent = ""; errorBox.hidden = true; }
  function setStatus(msg) {
    if (msg) { status.textContent = msg; status.hidden = false; }
    else { status.textContent = ""; status.hidden = true; }
  }
  function humanSize(bytes) {
    if (!bytes && bytes !== 0) { return "—"; }
    var units = ["B", "KB", "MB", "GB"];
    var value = bytes;
    var i = 0;
    while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
    return (i === 0 ? value : value.toFixed(1)) + " " + units[i];
  }
  function isSupported(file) {
    if (SUPPORTED_MIME.indexOf(file.type) !== -1) { return true; }
    var name = (file.name || "").toLowerCase();
    var ext = name.indexOf(".") !== -1 ? name.split(".").pop() : "";
    return SUPPORTED_EXT.indexOf(ext) !== -1;
  }
  function resetOutput() {
    outputBox.hidden = true;
    if (outputUrl) { URL.revokeObjectURL(outputUrl); outputUrl = null; }
    previewImg.removeAttribute("src");
    downloadLink.removeAttribute("href");
  }

  function loadImage(file) {
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { resolve({ url: url, img: img, w: img.naturalWidth, h: img.naturalHeight }); };
      img.onerror = function () { URL.revokeObjectURL(url); resolve(null); };
      img.src = url;
    });
  }

  function assignSlot(slot, input, result, previewEl, dimsEl) {
    if (slot.url) { URL.revokeObjectURL(slot.url); }
    slot.url = result.url;
    slot.img = result.img;
    slot.w = result.w;
    slot.h = result.h;
    slot.file = input.files && input.files[0];
    previewEl.src = result.url;
    dimsEl.textContent = result.w + " × " + result.h + " px";
  }

  function handleFile(input, slot, previewEl, dimsEl, label) {
    clearError();
    resetOutput();
    setStatus("");
    var file = input.files && input.files[0];
    if (!file) { return; }
    if (!isSupported(file)) {
      showError("Unsupported " + label + " file. Please choose a JPG, JPEG or PNG image.");
      input.value = "";
      return;
    }
    loadImage(file).then(function (result) {
      if (!result) {
        showError("The " + label + " image could not be read. Please try a different file.");
        input.value = "";
        return;
      }
      assignSlot(slot, input, result, previewEl, dimsEl);
      updateWorkspaceVisibility();
    });
  }

  function updateWorkspaceVisibility() {
    var ready = photo.img && signature.img;
    workspace.hidden = !ready;
    emptyState.hidden = ready;
    if (ready) { updateExpected(); }
  }

  function readLayout() {
    var w = parseInt(widthInput.value, 10);
    var h = parseInt(heightInput.value, 10);
    var gap = parseInt(gapInput.value, 10);
    if (!isFinite(gap) || gap < 0) { gap = 0; }
    return { w: w, h: h, gap: gap, layout: layoutSel.value };
  }

  function validateLayout(d) {
    if (!isFinite(d.w) || !isFinite(d.h)) { return "Enter both output width and height in pixels."; }
    if (d.w < MIN_DIMENSION || d.h < MIN_DIMENSION) {
      return "Output width and height must be at least " + MIN_DIMENSION + " pixels.";
    }
    if (d.w > MAX_DIMENSION || d.h > MAX_DIMENSION) {
      return "Output width and height must be " + MAX_DIMENSION + " pixels or less.";
    }
    if (d.w * d.h > MAX_PIXELS) {
      return "The requested output is too large. Please use smaller dimensions.";
    }
    if (d.gap > 200) { return "The gap must be 200 pixels or less."; }
    if (d.gap >= (d.layout === "beside" ? d.w : d.h)) {
      return "The gap is too large for the chosen output size.";
    }
    return "";
  }

  function updateExpected() {
    var d = readLayout();
    var error = validateLayout(d);
    if (error) { downloadLink.setAttribute("aria-disabled", "true"); }
    else { downloadLink.removeAttribute("aria-disabled"); }
    return error;
  }

  function regionFor(d, index) {
    if (d.layout === "beside") {
      var availW = d.w - d.gap;
      var photoW = Math.round(availW * 0.55);
      if (index === 0) { return { x: 0, y: 0, w: photoW, h: d.h }; }
      return { x: photoW + d.gap, y: 0, w: availW - photoW, h: d.h };
    }
    var availH = d.h - d.gap;
    var photoH = Math.round(availH * 0.68);
    if (index === 0) { return { x: 0, y: 0, w: d.w, h: photoH }; }
    return { x: 0, y: photoH + d.gap, w: d.w, h: availH - photoH };
  }

  function drawContained(img, region) {
    var scale = Math.min(region.w / img.naturalWidth, region.h / img.naturalHeight);
    var dw = Math.max(1, img.naturalWidth * scale);
    var dh = Math.max(1, img.naturalHeight * scale);
    var dx = region.x + (region.w - dw) / 2;
    var dy = region.y + (region.h - dh) / 2;
    ctx.drawImage(img, dx, dy, dw, dh);
  }

  function render() {
    clearError();
    if (!photo.img || !signature.img) {
      showError("Please upload both a photograph and a signature image.");
      return;
    }
    var d = readLayout();
    var error = validateLayout(d);
    if (error) { showError(error); return; }

    setStatus("Generating preview…");
    canvas.width = d.w;
    canvas.height = d.h;
    ctx.fillStyle = backgroundSel.value || "#ffffff";
    ctx.fillRect(0, 0, d.w, d.h);
    drawContained(photo.img, regionFor(d, 0));
    drawContained(signature.img, regionFor(d, 1));

    var mime = formatSel.value;
    var quality = mime === "image/jpeg" ? 0.92 : undefined;
    canvas.toBlob(function (blob) {
      if (!blob) {
        setStatus("");
        showError("Sorry, the combined image could not be generated. Try a different format or size.");
        return;
      }
      if (outputUrl) { URL.revokeObjectURL(outputUrl); }
      outputUrl = URL.createObjectURL(blob);
      previewImg.src = outputUrl;
      var baseName = (photo.file && photo.file.name ? photo.file.name : "photo").replace(/\.[^.]+$/, "");
      downloadLink.href = outputUrl;
      downloadLink.setAttribute("download", baseName + "-with-signature." + (mime === "image/png" ? "png" : "jpg"));
      outputBox.hidden = false;
      setStatus("Preview ready. Download it or adjust the settings and regenerate.");
    }, mime, quality);
  }

  function clearSlot(slot, input, previewEl, dimsEl) {
    if (slot.url) { URL.revokeObjectURL(slot.url); }
    slot.file = null;
    slot.url = null;
    slot.img = null;
    slot.w = 0;
    slot.h = 0;
    input.value = "";
    previewEl.removeAttribute("src");
    dimsEl.textContent = "—";
  }

  photoInput.addEventListener("change", function () {
    handleFile(photoInput, photo, photoPreview, photoDims, "photograph");
  });
  signatureInput.addEventListener("change", function () {
    handleFile(signatureInput, signature, signaturePreview, signatureDims, "signature");
  });
  [layoutSel, backgroundSel, formatSel].forEach(function (el) {
    el.addEventListener("change", function () { resetOutput(); setStatus(""); });
  });
  [widthInput, heightInput, gapInput].forEach(function (el) {
    el.addEventListener("input", function () { resetOutput(); setStatus(""); updateExpected(); });
  });

  generateBtn.addEventListener("click", function () {
    if (!photo.img || !signature.img) { render(); return; }
    render();
  });

  resetBtn.addEventListener("click", function () {
    layoutSel.value = "below";
    widthInput.value = 600;
    heightInput.value = 700;
    gapInput.value = 12;
    backgroundSel.value = "#ffffff";
    formatSel.value = "image/png";
    resetOutput();
    setStatus("");
    clearError();
    if (photo.img && signature.img) { render(); }
  });

  removeBtn.addEventListener("click", function () {
    clearSlot(photo, photoInput, photoPreview, photoDims);
    clearSlot(signature, signatureInput, signaturePreview, signatureDims);
    workspace.hidden = true;
    emptyState.hidden = false;
    resetOutput();
    setStatus("");
    clearError();
  });
})();
