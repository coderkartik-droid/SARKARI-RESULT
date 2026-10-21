(function () {
  "use strict";

  var PAGE_SIZES = {
    a4: [595.28, 841.89],
    letter: [612, 792]
  };
  var SUPPORTED_MIME = ["image/jpeg"];
  var SUPPORTED_EXT = ["jpg", "jpeg"];
  var COVER_MAX_PX = 1600;

  function byId(id) { return document.getElementById(id); }

  var fileInput = byId("pdf-files");
  var errorBox = byId("pdf-error");
  var emptyState = byId("pdf-empty");
  var workspace = byId("pdf-workspace");
  var thumbsList = byId("pdf-thumbs");
  var countEl = byId("pdf-count");
  var pageSizeSel = byId("pdf-page-size");
  var orientationSel = byId("pdf-orientation");
  var fitSel = byId("pdf-fit");
  var convertBtn = byId("pdf-convert");
  var clearBtn = byId("pdf-clear");
  var status = byId("pdf-status");
  var outputBox = byId("pdf-output");
  var downloadLink = byId("pdf-download");
  if (!fileInput) { return; }

  var items = [];
  var counter = 0;
  var pdfUrl = null;

  function showError(msg) { errorBox.textContent = msg; errorBox.hidden = false; }
  function clearError() { errorBox.textContent = ""; errorBox.hidden = true; }
  function setStatus(msg) {
    if (msg) { status.textContent = msg; status.hidden = false; }
    else { status.textContent = ""; status.hidden = true; }
  }
  function isSupported(file) {
    if (SUPPORTED_MIME.indexOf(file.type) !== -1) { return true; }
    var name = (file.name || "").toLowerCase();
    var ext = name.indexOf(".") !== -1 ? name.split(".").pop() : "";
    return SUPPORTED_EXT.indexOf(ext) !== -1;
  }

  function resetPdfOutput() {
    outputBox.hidden = true;
    if (pdfUrl) { URL.revokeObjectURL(pdfUrl); pdfUrl = null; }
    downloadLink.removeAttribute("href");
  }

  function renderThumbs() {
    thumbsList.innerHTML = "";
    items.forEach(function (item, index) {
      var li = document.createElement("li");
      li.className = "tool-thumb";

      var img = document.createElement("img");
      img.src = item.url;
      img.alt = "Selected image " + (index + 1);
      li.appendChild(img);

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tool-thumb-remove";
      btn.setAttribute("aria-label", "Remove image " + (index + 1));
      btn.textContent = "×";
      btn.addEventListener("click", function () { removeItem(item.id); });
      li.appendChild(btn);

      thumbsList.appendChild(li);
    });
    countEl.textContent = String(items.length);
    workspace.hidden = items.length === 0;
    emptyState.hidden = items.length > 0;
  }

  function removeItem(id) {
    var index = -1;
    for (var i = 0; i < items.length; i++) { if (items[i].id === id) { index = i; break; } }
    if (index === -1) { return; }
    URL.revokeObjectURL(items[index].url);
    items.splice(index, 1);
    clearError();
    resetPdfOutput();
    setStatus("");
    renderThumbs();
  }

  function loadItem(file) {
    return new Promise(function (resolve) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        items.push({
          id: ++counter,
          file: file,
          url: url,
          img: img,
          width: img.naturalWidth,
          height: img.naturalHeight
        });
        resolve(true);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        resolve(false);
      };
      img.src = url;
    });
  }

  function addFiles(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) { return; }
    clearError();
    var skipped = 0;
    var chain = Promise.resolve();
    files.forEach(function (file) {
      if (!isSupported(file)) { skipped++; return; }
      chain = chain.then(function () {
        return loadItem(file).then(function (ok) { if (!ok) { skipped++; } });
      });
    });
    chain.then(function () {
      resetPdfOutput();
      setStatus("");
      if (skipped > 0) {
        showError(skipped + " file(s) were skipped. Only JPG and JPEG images are supported.");
      }
      renderThumbs();
      fileInput.value = "";
    });
  }

  function coverDataUrl(item, pageW, pageH) {
    var srcAspect = item.width / item.height;
    var pageAspect = pageW / pageH;
    var sx, sy, sw, sh;
    if (srcAspect > pageAspect) {
      sh = item.height;
      sw = sh * pageAspect;
      sx = (item.width - sw) / 2;
      sy = 0;
    } else {
      sw = item.width;
      sh = sw / pageAspect;
      sx = 0;
      sy = (item.height - sh) / 2;
    }
    var targetW = Math.min(COVER_MAX_PX, Math.round(pageW * 2));
    var targetH = Math.max(1, Math.round(targetW / pageAspect));
    var canvas = document.createElement("canvas");
    canvas.width = targetW;
    canvas.height = targetH;
    var ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, targetW, targetH);
    ctx.drawImage(item.img, sx, sy, sw, sh, 0, 0, targetW, targetH);
    return canvas.toDataURL("image/jpeg", 0.92);
  }

  function convert() {
    clearError();
    resetPdfOutput();
    if (!items.length) {
      showError("Please select at least one JPG image before converting.");
      return;
    }
    var jsPDFClass = window.jspdf && window.jspdf.jsPDF;
    if (!jsPDFClass) {
      showError("The PDF library could not be loaded. Please check your connection and reload the page.");
      return;
    }

    setStatus("Generating PDF…");
    convertBtn.disabled = true;

    setTimeout(function () {
      try {
        var base = PAGE_SIZES[pageSizeSel.value] || PAGE_SIZES.a4;
        var orientation = orientationSel.value === "landscape" ? "landscape" : "portrait";
        var pw = base[0];
        var ph = base[1];
        var doc = new jsPDFClass({ unit: "pt", format: [pw, ph], orientation: orientation });
        var fit = fitSel.value;

        for (var i = 0; i < items.length; i++) {
          if (i > 0) { doc.addPage([pw, ph], orientation); }
          var pageW = doc.internal.pageSize.getWidth();
          var pageH = doc.internal.pageSize.getHeight();
          var item = items[i];

          if (fit === "cover") {
            doc.addImage(coverDataUrl(item, pageW, pageH), "JPEG", 0, 0, pageW, pageH);
          } else {
            var scale = Math.min(pageW / item.width, pageH / item.height);
            var dw = item.width * scale;
            var dh = item.height * scale;
            doc.addImage(item.img, "JPEG", (pageW - dw) / 2, (pageH - dh) / 2, dw, dh);
          }
        }

        var blob = doc.output("blob");
        pdfUrl = URL.createObjectURL(blob);
        downloadLink.href = pdfUrl;
        downloadLink.setAttribute("download", "converted-images.pdf");
        outputBox.hidden = false;
        setStatus("PDF ready. Use the button below to download it.");
      } catch (err) {
        showError("Sorry, the PDF could not be generated. Please try fewer or smaller images.");
        setStatus("");
      } finally {
        convertBtn.disabled = false;
      }
    }, 50);
  }

  fileInput.addEventListener("change", function () { addFiles(fileInput.files); });
  convertBtn.addEventListener("click", convert);
  clearBtn.addEventListener("click", function () {
    items.forEach(function (item) { URL.revokeObjectURL(item.url); });
    items = [];
    fileInput.value = "";
    resetPdfOutput();
    clearError();
    setStatus("");
    renderThumbs();
  });
})();
