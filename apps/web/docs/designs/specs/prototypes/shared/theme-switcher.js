/* ─────────────────────────────────────────────
 * Ditto Theme Switcher — Shared Behavior
 * Handles density + theme toggle for all prototype pages.
 * Requirements:
 *   - <html data-theme="dark" data-density="default">
 *   - Include this script after the page loads
 * ───────────────────────────────────────────── */

;(function () {
  'use strict';

  var html = document.documentElement;

  var DENSITIES = ['default', 'comfortable', 'compact'];
  var DENSITY_LABELS = { compact: '紧凑', default: '标准', comfortable: '宽松' };
  var THEMES = ['dark', 'light'];
  var THEME_LABELS = { dark: '深色', light: '浅色' };
  var DENSITY_ICONS = {
    compact: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 5h14"/><path d="M3 8h14"/><path d="M3 11h14"/><path d="M3 14h14"/></svg>',
    default: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 4h14"/><path d="M3 10h14"/><path d="M3 16h14"/></svg>',
    comfortable: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 3h14"/><path d="M3 10h14"/><path d="M3 17h14"/></svg>'
  };

  var THEME_ICONS = {
    dark: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 1 0 0 12 4.5 4.5 0 0 1 0-12z"/></svg>',
    light: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="10" cy="10" r="3"/><path d="M10 2v2m0 12v2M4.2 4.2l1.4 1.4m8.8 8.8 1.4 1.4M2 10h2m12 0h2M4.2 15.8l1.4-1.4m8.8-8.8 1.4-1.4"/></svg>'
  };

  function resolveThemePreference(preference) {
    return preference === 'light' ? 'light' : 'dark';
  }

  function getThemePreference() {
    return html.getAttribute('data-theme-preference') || html.getAttribute('data-theme') || 'dark';
  }

  function normalizeDensity(density) {
    return density === 'dense' ? 'compact' : density;
  }

  function updatePreferenceSummary() {
    var density = normalizeDensity(html.getAttribute('data-density') || 'default');
    var preference = getThemePreference();
    var resolvedTheme = html.getAttribute('data-theme') || resolveThemePreference(preference);
    var themeLabel = THEME_LABELS[preference] || THEME_LABELS[resolvedTheme] || resolvedTheme;
    var densityLabel = DENSITY_LABELS[density] || density;
    var summary = themeLabel + ' · ' + densityLabel + '密度';

    document.querySelectorAll('[data-preference-summary]').forEach(function (element) {
      element.textContent = '当前：' + summary;
    });

    document.querySelectorAll('[data-current-preference-summary]').forEach(function (trigger) {
      trigger.setAttribute('aria-label', summary);
      trigger.setAttribute('title', summary);
    });
  }

  function setDensity(density) {
    var nextDensity = DENSITIES.indexOf(normalizeDensity(density)) !== -1 ? normalizeDensity(density) : 'default';
    html.setAttribute('data-density', nextDensity);
    localStorage.setItem('ditto-density', nextDensity);
    updateDensityIcon();
  }

  function setTheme(themePreference) {
    var preference = THEMES.indexOf(themePreference) !== -1 ? themePreference : 'dark';
    html.setAttribute('data-theme-preference', preference);
    html.setAttribute('data-theme', resolveThemePreference(preference));
    localStorage.setItem('ditto-theme', preference);
    updateThemeIcon();
  }

  function updateDensityIcon() {
    var density = normalizeDensity(html.getAttribute('data-density') || 'default');
    var btn = document.getElementById('density-toggle');
    if (btn) {
      btn.innerHTML = DENSITY_ICONS[density] || DENSITY_ICONS.default;
      btn.setAttribute('data-preference-active', density === 'default' ? 'false' : 'true');
      btn.setAttribute('data-preference-state', density);
      btn.setAttribute('title', '密度切换 — 当前: ' + (DENSITY_LABELS[density] || density));
      btn.setAttribute('aria-label', '密度切换 — 当前: ' + (DENSITY_LABELS[density] || density));
    }
    document.querySelectorAll('[data-set-density]').forEach(function (option) {
      var selected = option.getAttribute('data-set-density') === density;
      option.setAttribute('aria-checked', selected ? 'true' : 'false');
      option.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    updatePreferenceSummary();
  }

  function updateThemeIcon() {
    var preference = getThemePreference();
    var resolvedTheme = html.getAttribute('data-theme') || resolveThemePreference(preference);
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.innerHTML = THEME_ICONS[preference] || THEME_ICONS[resolvedTheme] || THEME_ICONS.dark;
      btn.setAttribute('data-preference-active', resolvedTheme === 'light' ? 'true' : 'false');
      btn.setAttribute('data-preference-state', resolvedTheme);
      btn.setAttribute('title', '主题切换 — 当前: ' + (THEME_LABELS[preference] || THEME_LABELS[resolvedTheme]));
      btn.setAttribute('aria-label', '主题切换 — 当前: ' + (THEME_LABELS[preference] || THEME_LABELS[resolvedTheme]));
    }
    document.querySelectorAll('[data-set-theme]').forEach(function (option) {
      var selected = option.getAttribute('data-set-theme') === preference;
      option.setAttribute('aria-checked', selected ? 'true' : 'false');
      option.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    updatePreferenceSummary();
  }

  // Restore saved preferences
  var savedDensity = localStorage.getItem('ditto-density');
  var savedTheme = localStorage.getItem('ditto-theme');
  if (savedDensity) setDensity(savedDensity);
  setTheme(savedTheme && THEMES.indexOf(savedTheme) !== -1 ? savedTheme : getThemePreference());

  // Event delegation — density toggle cycles through 3 modes
  document.addEventListener('click', function (e) {
    var densityBtn = e.target.closest('#density-toggle');
    if (densityBtn) {
      var current = normalizeDensity(html.getAttribute('data-density') || 'default');
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
