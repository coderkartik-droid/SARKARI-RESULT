(function () {
  "use strict";

  var SUPPORTED_MIME = ["image/jpeg", "image/png"];
  var SUPPORTED_EXT = ["jpg", "jpeg", "png"];
  var MIN_DIMENSION = 20;
  var MAX_DIMENSION = 6000;
  var MAX_PIXELS = 40000000; // ~40 MP safety guard

  var PRESETS = {
    square: { width: null, height: null, ratio: 1 },
    portrait: { ratio: 4 / 3 },
    passport: { width: 413, height: 531 },
    stamp: { width: 236, height: 295 }
  };

  function byId(id) { return document.getElementById(id); }

  var fileInput = byId("rcv-file");
  var errorBox = byId("rcv-error");
  var emptyState = byId("rcv-empty");
  var workspace = byId("rcv-workspace");
  var sourceImg = byId("rcv-source");
  var origDims = byId("rcv-orig-dims");
  var origSize = byId("rcv-orig-size");
  var presetSel = byId("rcv-preset");
  var widthInput = byId("rcv-width");
  var heightInput = byId("rcv-height");
  var fitSel = byId("rcv-fit");
  var backgroundSel = byId("rcv-background");
  var formatSel = byId("rcv-format");
  var expected = byId("rcv-expected");
  var generateBtn = byId("rcv-generate");
  var resetBtn = byId("rcv-reset");
  var removeBtn = byId("rcv-remove");
  var status = byId("rcv-status");
  var outputBox = byId("rcv-output");
  var previewImg = byId("rcv-preview");
  var outDims = byId("rcv-out-dims");
  var outSize = byId("rcv-out-size");
  var downloadLink = byId("rcv-download");
  if (!fileInput) { return; }

  var canvas = document.createElement("canvas");
  var ctx = canvas.getContext("2d");
  var sourceFile = null;
  var sourceUrl = null;
  var outputUrl = null;
  var naturalW = 0;
  var naturalH = 0;

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

  function readDimensions() {
    return { w: parseInt(widthInput.value, 10), h: parseInt(heightInput.value, 10) };
  }

  function validateDimensions(w, h) {
    if (!isFinite(w) || !isFinite(h)) { return "Enter both width and height in pixels."; }
    if (w < MIN_DIMENSION || h < MIN_DIMENSION) {
      return "Width and height must be at least " + MIN_DIMENSION + " pixels.";
    }
    if (w > MAX_DIMENSION || h > MAX_DIMENSION) {
      return "Width and height must be " + MAX_DIMENSION + " pixels or less.";
    }
    if (w * h > MAX_PIXELS) {
      return "The requested image is too large. Please use smaller dimensions.";
    }
    return "";
  }

  function updateExpected() {
    var d = readDimensions();
    var error = validateDimensions(d.w, d.h);
    expected.textContent = error ? "—" : d.w + " × " + d.h + " px";
  }

  function applyPreset() {
    var preset = PRESETS[presetSel.value];
    if (!preset) { updateExpected(); return; }
    if (preset.width && preset.height) {
      widthInput.value = preset.width;
      heightInput.value = preset.height;
    } else if (preset.ratio) {
      var w = parseInt(widthInput.value, 10);
      if (!isFinite(w) || w < MIN_DIMENSION) { w = naturalW || 600; }
      widthInput.value = w;
      heightInput.value = Math.round(w / preset.ratio);
    }
    updateExpected();
  }

  function loadFile(file) {
    clearError();
    resetOutput();
    if (!file) { return; }
    if (!isSupported(file)) {
      showError("Unsupported file. Please choose a JPG, JPEG or PNG image.");
      return;
    }
    if (sourceUrl) { URL.revokeObjectURL(sourceUrl); sourceUrl = null; }
    sourceUrl = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      sourceFile = file;
      naturalW = img.naturalWidth;
      naturalH = img.naturalHeight;
      sourceImg.src = sourceUrl;
      origDims.textContent = naturalW + " × " + naturalH + " px";
      origSize.textContent = humanSize(file.size);
      widthInput.value = naturalW;
      heightInput.value = naturalH;
      presetSel.value = "custom";
      workspace.hidden = false;
      emptyState.hidden = true;
      updateExpected();
      setStatus("");
    };
    img.onerror = function () {
      showError("This image could not be read. Please try a different file.");
    };
    img.src = sourceUrl;
  }

  function drawContained(img, w, h) {
    var scale = Math.min(w / img.naturalWidth, h / img.naturalHeight);
    var dw = Math.max(1, img.naturalWidth * scale);
    var dh = Math.max(1, img.naturalHeight * scale);
    ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
  }

  function drawCover(img, w, h) {
    var srcAspect = img.naturalWidth / img.naturalHeight;
    var targetAspect = w / h;
    var sx, sy, sw, sh;
    if (srcAspect > targetAspect) {
      sh = img.naturalHeight;
      sw = sh * targetAspect;
      sx = (img.naturalWidth - sw) / 2;
      sy = 0;
    } else {
      sw = img.naturalWidth;
      sh = sw / targetAspect;
      sx = 0;
      sy = (img.naturalHeight - sh) / 2;
    }
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, w, h);
  }

  function render() {
    clearError();
    if (!sourceFile) {
      showError("Please choose a photograph first.");
      return;
    }
    var d = readDimensions();
    var error = validateDimensions(d.w, d.h);
    if (error) { showError(error); return; }

    setStatus("Generating preview…");
    canvas.width = d.w;
    canvas.height = d.h;
    ctx.fillStyle = backgroundSel.value || "#ffffff";
    ctx.fillRect(0, 0, d.w, d.h);

    if (fitSel.value === "cover") {
      drawCover(sourceImg, d.w, d.h);
    } else {
      drawContained(sourceImg, d.w, d.h);
    }

    var mime = formatSel.value;
    var quality = mime === "image/jpeg" ? 0.92 : undefined;
    canvas.toBlob(function (blob) {
      if (!blob) {
        setStatus("");
        showError("Sorry, the image could not be processed. Try a different format or size.");
        return;
      }
      if (outputUrl) { URL.revokeObjectURL(outputUrl); }
      outputUrl = URL.createObjectURL(blob);
      previewImg.src = outputUrl;
      outDims.textContent = d.w + " × " + d.h + " px";
      outSize.textContent = humanSize(blob.size);
      var baseName = (sourceFile.name || "photo").replace(/\.[^.]+$/, "");
      downloadLink.href = outputUrl;
      downloadLink.setAttribute("download", baseName + "-cv-photo." + (mime === "image/png" ? "png" : "jpg"));
      outputBox.hidden = false;
      setStatus("Preview ready. Download it or adjust the settings and regenerate.");
    }, mime, quality);
  }

  fileInput.addEventListener("change", function () {
    loadFile(fileInput.files && fileInput.files[0]);
  });

  presetSel.addEventListener("change", function () {
    resetOutput();
    setStatus("");
    applyPreset();
  });
  [widthInput, heightInput].forEach(function (el) {
    el.addEventListener("input", function () {
      presetSel.value = "custom";
      resetOutput();
      setStatus("");
      updateExpected();
    });
  });
  [fitSel, backgroundSel, formatSel].forEach(function (el) {
    el.addEventListener("change", function () { resetOutput(); setStatus(""); });
  });

  generateBtn.addEventListener("click", render);

  resetBtn.addEventListener("click", function () {
    if (!naturalW) { return; }
    presetSel.value = "custom";
    widthInput.value = naturalW;
    heightInput.value = naturalH;
    fitSel.value = "contain";
    backgroundSel.value = "#ffffff";
    formatSel.value = "image/png";
    resetOutput();
    setStatus("");
    clearError();
    updateExpected();
  });

  removeBtn.addEventListener("click", function () {
    fileInput.value = "";
    if (sourceUrl) { URL.revokeObjectURL(sourceUrl); sourceUrl = null; }
    sourceFile = null;
    naturalW = 0;
    naturalH = 0;
    sourceImg.removeAttribute("src");
    widthInput.value = "";
    heightInput.value = "";
    presetSel.value = "custom";
    resetOutput();
    workspace.hidden = true;
    emptyState.hidden = false;
    expected.textContent = "—";
    setStatus("");
    clearError();
  });
})();
