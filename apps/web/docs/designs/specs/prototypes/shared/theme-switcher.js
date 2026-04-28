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

  var DENSITIES = ['dense', 'compact', 'comfortable'];
  var DENSITY_LABELS = { dense: '紧凑', compact: '标准', comfortable: '宽松' };
  var DENSITY_ICONS = {
    dense: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 5h14"/><path d="M3 8h14"/><path d="M3 11h14"/><path d="M3 14h14"/></svg>',
    compact: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 4h14"/><path d="M3 10h14"/><path d="M3 16h14"/></svg>',
    comfortable: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 3h14"/><path d="M3 10h14"/><path d="M3 17h14"/></svg>'
  };

  var THEME_ICONS = {
    dark: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 1 0 0 12 4.5 4.5 0 0 1 0-12z"/></svg>',
    light: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="10" cy="10" r="3"/><path d="M10 2v2m0 12v2M4.2 4.2l1.4 1.4m8.8 8.8 1.4 1.4M2 10h2m12 0h2M4.2 15.8l1.4-1.4m8.8-8.8 1.4-1.4"/></svg>'
  };

  function setDensity(density) {
    html.setAttribute('data-density', density);
    localStorage.setItem('ditto-density', density);
    updateDensityIcon();
  }

  function setTheme(theme) {
    html.setAttribute('data-theme', theme);
    localStorage.setItem('ditto-theme', theme);
    updateThemeIcon();
  }

  function updateDensityIcon() {
    var density = html.getAttribute('data-density') || 'compact';
    var btn = document.getElementById('density-toggle');
    if (btn) {
      btn.innerHTML = DENSITY_ICONS[density] || DENSITY_ICONS.compact;
      btn.setAttribute('title', '密度: ' + (DENSITY_LABELS[density] || density));
      btn.setAttribute('aria-label', '密度切换 — 当前: ' + (DENSITY_LABELS[density] || density));
    }
  }

  function updateThemeIcon() {
    var theme = html.getAttribute('data-theme') || 'dark';
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.innerHTML = THEME_ICONS[theme] || THEME_ICONS.dark;
      btn.setAttribute('title', '主题: ' + (theme === 'dark' ? '深色' : '浅色'));
      btn.setAttribute('aria-label', '主题切换 — 当前: ' + (theme === 'dark' ? '深色' : '浅色'));
    }
  }

  // Restore saved preferences
  var savedDensity = localStorage.getItem('ditto-density');
  var savedTheme = localStorage.getItem('ditto-theme');
  if (savedDensity && DENSITIES.indexOf(savedDensity) !== -1) setDensity(savedDensity);
  if (savedTheme) setTheme(savedTheme);

  // Event delegation — density toggle cycles through 3 modes
  document.addEventListener('click', function (e) {
    var prefsBtn = e.target.closest('[data-view-preferences-trigger]');
    if (prefsBtn) {
      var root = prefsBtn.closest('.view-preferences');
      if (root) root.setAttribute('data-open', root.getAttribute('data-open') === 'true' ? 'false' : 'true');
      return;
    }

    var densityBtn = e.target.closest('#density-toggle');
    if (densityBtn) {
      var current = html.getAttribute('data-density') || 'compact';
      var idx = DENSITIES.indexOf(current);
      var next = DENSITIES[(idx + 1) % DENSITIES.length];
      setDensity(next);
      return;
    }

    var themeBtn = e.target.closest('#theme-toggle');
    if (themeBtn) {
      var currentTheme = html.getAttribute('data-theme') || 'dark';
      setTheme(currentTheme === 'dark' ? 'light' : 'dark');
      return;
    }

    // Legacy support: data-set-density / data-set-theme buttons
    var legacyDensity = e.target.closest('[data-set-density]');
    if (legacyDensity) {
      setDensity(legacyDensity.getAttribute('data-set-density'));
      return;
    }
    var legacyTheme = e.target.closest('[data-set-theme]');
    if (legacyTheme) {
      setTheme(legacyTheme.getAttribute('data-set-theme'));
      return;
    }
  });

  // Initial state sync
  updateDensityIcon();
  updateThemeIcon();
})();
