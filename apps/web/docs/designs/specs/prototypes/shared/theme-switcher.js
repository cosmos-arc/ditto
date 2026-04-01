/* ─────────────────────────────────────────────
 * Ditto Theme Switcher — Shared Behavior
 * Handles density + theme toggle for all prototype pages.
 * Requirements:
 *   - <html data-theme="dark" data-density="compact">
 *   - Include this script after the page loads
 * ───────────────────────────────────────────── */

;(function () {
  'use strict';

  var html = document.documentElement;

  function setDensity(density) {
    html.setAttribute('data-density', density);
    localStorage.setItem('ditto-density', density);
    updateDensityButtons();
  }

  function setTheme(theme) {
    html.setAttribute('data-theme', theme);
    localStorage.setItem('ditto-theme', theme);
    updateThemeButtons();
  }

  function updateDensityButtons() {
    var density = html.getAttribute('data-density') || 'compact';
    document.querySelectorAll('[data-set-density]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-set-density') === density ? 'true' : 'false');
    });
  }

  function updateThemeButtons() {
    var theme = html.getAttribute('data-theme') || 'dark';
    document.querySelectorAll('[data-set-theme]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-set-theme') === theme ? 'true' : 'false');
    });
  }

  // Restore saved preferences
  var savedDensity = localStorage.getItem('ditto-density');
  var savedTheme = localStorage.getItem('ditto-theme');
  if (savedDensity) setDensity(savedDensity);
  if (savedTheme) setTheme(savedTheme);

  // Event delegation
  document.addEventListener('click', function (e) {
    var densityBtn = e.target.closest('[data-set-density]');
    if (densityBtn) {
      setDensity(densityBtn.getAttribute('data-set-density'));
      return;
    }
    var themeBtn = e.target.closest('[data-set-theme]');
    if (themeBtn) {
      setTheme(themeBtn.getAttribute('data-set-theme'));
    }
  });

  // Initial state sync
  updateDensityButtons();
  updateThemeButtons();
})();
