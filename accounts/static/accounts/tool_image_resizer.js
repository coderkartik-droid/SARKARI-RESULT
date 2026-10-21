(function () {
  "use strict";

  var MAX_DIMENSION = 10000;
  var MAX_PIXELS = 40000000; // ~40 MP safety guard
  var SUPPORTED_MIME = ["image/jpeg", "image/png", "image/webp"];
  var SUPPORTED_EXT = ["jpg", "jpeg", "png", "webp"];

  function byId(id) { return document.getElementById(id); }

  var fileInput = byId("resizer-file");
  var errorBox = byId("resizer-error");
  var emptyState = byId("resizer-empty");
  var workspace = byId("resizer-workspace");
  var sourceImg = byId("resizer-source");
  var origDims = byId("resizer-orig-dims");
  var origSize = byId("resizer-orig-size");
  var widthInput = byId("resizer-width");
  var heightInput = byId("resizer-height");
  var lockInput = byId("resizer-lock");
  var formatInput = byId("resizer-format");
  var expected = byId("resizer-expected");
  var runBtn = byId("resizer-run");
  var resetBtn = byId("resizer-reset");
  var removeBtn = byId("resizer-remove");
  var status = byId("resizer-status");
  var outputBox = byId("resizer-output");
  var previewImg = byId("resizer-preview");
  var outDims = byId("resizer-out-dims");
  var outSize = byId("resizer-out-size");
  var downloadLink = byId("resizer-download");
  if (!fileInput) { return; }

  var sourceFile = null;
  var objectUrl = null;
  var outputUrl = null;
  var naturalW = 0;
  var naturalH = 0;
  var aspect = 1;

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }
  function clearError() {
    errorBox.textContent = "";
    errorBox.hidden = true;
  }
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
  function extLabel(mime) {
    if (mime === "image/png") { return "png"; }
    if (mime === "image/webp") { return "webp"; }
    return "jpg";
  }
  function isSupported(file) {
    if (SUPPORTED_MIME.indexOf(file.type) !== -1) { return true; }
    var name = (file.name || "").toLowerCase();
    var ext = name.indexOf(".") !== -1 ? name.split(".").pop() : "";
    return SUPPORTED_EXT.indexOf(ext) !== -1;
  }

  function readDimensions() {
    var w = parseInt(widthInput.value, 10);
    var h = parseInt(heightInput.value, 10);
    return { w: w, h: h };
  }

  function validateDimensions(w, h) {
    if (!isFinite(w) || !isFinite(h)) { return "Enter both width and height in pixels."; }
    if (w < 1 || h < 1) { return "Width and height must be at least 1 pixel."; }
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

  function revealWorkspace() {
    workspace.hidden = false;
    emptyState.hidden = true;
  }

  function resetOutput() {
    outputBox.hidden = true;
    if (outputUrl) { URL.revokeObjectURL(outputUrl); outputUrl = null; }
    previewImg.removeAttribute("src");
    downloadLink.removeAttribute("href");
  }

  function resetToOriginal() {
    widthInput.value = naturalW;
    heightInput.value = naturalH;
    updateExpected();
    resetOutput();
    setStatus("");
    clearError();
  }

  function loadFile(file) {
    clearError();
    resetOutput();
    if (!file) { return; }
    if (!isSupported(file)) {
      showError("Unsupported file. Please choose a JPG, JPEG, PNG or WebP image.");
      return;
    }
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    objectUrl = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      sourceFile = file;
      naturalW = img.naturalWidth;
      naturalH = img.naturalHeight;
      aspect = naturalW / naturalH;
      sourceImg.src = objectUrl;
      origDims.textContent = naturalW + " × " + naturalH + " px";
      origSize.textContent = humanSize(file.size);
      widthInput.value = naturalW;
      heightInput.value = naturalH;
      revealWorkspace();
      updateExpected();
      setStatus("");
    };
    img.onerror = function () {
      showError("This image could not be read. Please try a different file.");
    };
    img.src = objectUrl;
  }

  fileInput.addEventListener("change", function () {
    resetToOriginal();
    loadFile(fileInput.files && fileInput.files[0]);
  });

  widthInput.addEventListener("input", function () {
    if (lockInput.checked) {
      var w = parseInt(widthInput.value, 10);
      if (isFinite(w) && w > 0) { heightInput.value = Math.max(1, Math.round(w / aspect)); }
    }
    updateExpected();
  });

  heightInput.addEventListener("input", function () {
    if (lockInput.checked) {
      var h = parseInt(heightInput.value, 10);
      if (isFinite(h) && h > 0) { widthInput.value = Math.max(1, Math.round(h * aspect)); }
    }
    updateExpected();
  });

  lockInput.addEventListener("change", function () {
    if (lockInput.checked) {
      var w = parseInt(widthInput.value, 10);
      if (isFinite(w) && w > 0) { heightInput.value = Math.max(1, Math.round(w / aspect)); }
      updateExpected();
    }
  });

  formatInput.addEventListener("change", function () { resetOutput(); setStatus(""); });

  runBtn.addEventListener("click", function () {
    clearError();
    if (!sourceFile || !naturalW) {
      showError("Please choose an image first.");
      return;
    }
    var d = readDimensions();
    var error = validateDimensions(d.w, d.h);
    if (error) { showError(error); return; }

    setStatus("Resizing…");
    var mime = formatInput.value;
    var canvas = document.createElement("canvas");
    canvas.width = d.w;
    canvas.height = d.h;
    var ctx = canvas.getContext("2d");
    if (mime === "image/jpeg") {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, d.w, d.h);
    }
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(sourceImg, 0, 0, d.w, d.h);

    var quality = mime === "image/png" ? undefined : 0.92;
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
      var baseName = (sourceFile.name || "image").replace(/\.[^.]+$/, "");
      downloadLink.href = outputUrl;
      downloadLink.setAttribute("download", baseName + "-resized." + extLabel(mime));
      outputBox.hidden = false;
      setStatus("Done. Your resized image is ready to download.");
    }, mime, quality);
  });

  resetBtn.addEventListener("click", function () {
    if (!naturalW) { return; }
    resetToOriginal();
  });

  removeBtn.addEventListener("click", function () {
    fileInput.value = "";
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    sourceFile = null;
    naturalW = 0;
    naturalH = 0;
    sourceImg.removeAttribute("src");
    widthInput.value = "";
    heightInput.value = "";
    resetOutput();
    workspace.hidden = true;
    emptyState.hidden = false;
    expected.textContent = "—";
    setStatus("");
    clearError();
  });
})();
