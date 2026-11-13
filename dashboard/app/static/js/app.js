// Small page behaviours. No framework: Bootstrap's JS handles modals and toasts.
(function () {
  'use strict';

  var root = document.documentElement;

  // ----- light / dark toggle (dark is the default) -----
  function setTheme(theme) {
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-bs-theme', theme);
    try { localStorage.setItem('theme', theme); } catch (e) { /* storage blocked: theme lasts for this page only */ }
    document.dispatchEvent(new Event('themechange')); // charts.js redraws on this
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });
  });

  // ----- sidebar on mobile -----
  var sidebar = document.getElementById('sidebar');
  var backdrop = document.getElementById('sidebar-backdrop');
  function toggleSidebar(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('open', open);
    backdrop.classList.toggle('open', open);
  }
  document.querySelectorAll('[data-menu]').forEach(function (button) {
    button.addEventListener('click', function () { toggleSidebar(true); });
  });
  if (backdrop) backdrop.addEventListener('click', function () { toggleSidebar(false); });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') toggleSidebar(false);
  });

  // ----- flash messages as toasts -----
  document.querySelectorAll('.toast').forEach(function (el) {
    new bootstrap.Toast(el, { delay: 4500 }).show();
  });

  // ----- copy to clipboard -----
  document.addEventListener('click', function (event) {
    var button = event.target.closest('.copy-btn');
    if (!button || !navigator.clipboard) return;
    event.preventDefault();
    navigator.clipboard.writeText(button.dataset.copy).then(function () {
      var icon = button.querySelector('i');
      button.classList.add('copied');
      icon.className = 'bi bi-check2';
      setTimeout(function () {
        button.classList.remove('copied');
        icon.className = 'bi bi-copy';
      }, 1200);
    });
  });

  // ----- delete confirmation modal (shared by services and incidents) -----
  var confirmModal = document.getElementById('confirmModal');
  if (confirmModal) {
    confirmModal.addEventListener('show.bs.modal', function (event) {
      var trigger = event.relatedTarget;
      confirmModal.querySelector('form').action = trigger.dataset.action;
      confirmModal.querySelector('[data-confirm-title]').textContent = trigger.dataset.title;
      confirmModal.querySelector('[data-confirm-text]').textContent = trigger.dataset.text;
    });
  }

  // ----- service add / edit modal -----
  var serviceModal = document.getElementById('serviceModal');
  if (serviceModal) {
    serviceModal.addEventListener('show.bs.modal', function (event) {
      var trigger = event.relatedTarget;
      if (!trigger) return; // reopened by the server after a validation error
      var form = serviceModal.querySelector('form');
      form.action = trigger.dataset.action;
      serviceModal.querySelector('.modal-title').textContent = trigger.dataset.title;
      ['name', 'description', 'repo_url', 'health_url'].forEach(function (field) {
        var input = form.querySelector('[name="' + field + '"]');
        input.value = trigger.dataset[field] || '';
        input.classList.remove('is-invalid');
      });
      form.querySelectorAll('.invalid-feedback').forEach(function (el) { el.remove(); });
    });
    serviceModal.addEventListener('shown.bs.modal', function () {
      serviceModal.querySelector('[name="name"]').focus();
    });
    if (serviceModal.dataset.showOnLoad === 'true') {
      new bootstrap.Modal(serviceModal).show();
    }
  }
})();
