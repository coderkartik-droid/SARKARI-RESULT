document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.management-icon-picker').forEach(function (picker) {
    var select = picker.querySelector('select');
    var preview = picker.querySelector('.management-icon-picker-value');
    if (!select || !preview) {
      return;
    }

    var updatePreview = function () {
      var selectedText = select.options[select.selectedIndex]?.text || 'none';
      preview.textContent = selectedText;
    };

    updatePreview();
    select.addEventListener('change', updatePreview);
  });
});
