/* ─────────────────────────────────────────────
 * Ditto Prototype Interactions — Shared Library
 * Edition v1 Iteration v3→v4 — Vanilla JS 交互增强
 *
 * 声明式 data-* 属性驱动，零外部依赖
 * 渐进增强：JS 未加载时 CSS 基线 ≥9.0
 * 所有动效尊重 prefers-reduced-motion
 * ───────────────────────────────────────────── */
;(function () {
  'use strict';

  /* ── Motion Preference ─────────────────────── */
  var motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  var reducedMotion = motionQuery.matches;
  document.documentElement.toggleAttribute('data-reduced-motion', reducedMotion);
  motionQuery.addEventListener('change', function (event) {
    reducedMotion = event.matches;
    document.documentElement.toggleAttribute('data-reduced-motion', reducedMotion);
  });

  /* ── Utility: Parse JSON from data attribute ── */
  function parseAttr(el, attr) {
    try { return JSON.parse(el.getAttribute(attr)); }
    catch (_) { return null; }
  }

  /* ── Utility: Resolve CSS custom property ── */
  var computedStyleCache = null;
  var cssVarCacheInvalidationReady = false;

  function clearCssVarCache() {
    computedStyleCache = null;
  }

  function cssVar(name, fallback) {
    if (!computedStyleCache) {
      computedStyleCache = getComputedStyle(document.documentElement);
    }
    var v = computedStyleCache.getPropertyValue(name);
    return v ? v.trim() : fallback;
  }

  function watchCssVarCacheInvalidation() {
    if (cssVarCacheInvalidationReady) return;
    cssVarCacheInvalidationReady = true;

    document.addEventListener('themechange', clearCssVarCache);
    document.addEventListener('densitychange', clearCssVarCache);

    if (typeof MutationObserver === 'undefined') return;
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i += 1) {
        if (mutations[i].attributeName === 'data-theme' || mutations[i].attributeName === 'data-density') {
          clearCssVarCache();
          return;
        }
      }
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'data-density'],
    });
  }

  /* ══════════════════════════════════════════════
   * 1. Tabs
   *    Container: data-tabs="group-name"
   *    Buttons:   data-tab-target="panel-id"
   *    Panels:    data-tab-panel="panel-id"
   * ══════════════════════════════════════════════ */
  var tabIdCounter = 1;

  var Tabs = {
    init: function () {
      document.querySelectorAll('[data-tabs]').forEach(function (group) {
        var buttons = Array.from(group.querySelectorAll('[data-tab-target]'));
        var panels  = Tabs._resolvePanels(group, buttons);
        if (!buttons.length || !panels.length) return;

        function rememberPanelDisplay(panel) {
          var currentDisplay = panel.style.display;
          if (currentDisplay && currentDisplay !== 'none') {
            panel.setAttribute('data-tab-display', currentDisplay);
          }
        }

        function activate(btn, shouldDispatch) {
          var target = btn.getAttribute('data-tab-target');
          if (!target) return;

          buttons.forEach(function (button) {
            var selected = button === btn;
            button.classList.toggle('active', selected);
            button.setAttribute('aria-selected', selected ? 'true' : 'false');
            if (button.getAttribute('role') === 'tab') {
              button.setAttribute('tabindex', selected ? '0' : '-1');
            }
          });

          panels.forEach(function (panel) {
            var match = panel.getAttribute('data-tab-panel') === target;
            rememberPanelDisplay(panel);
            panel.style.display = match ? (panel.getAttribute('data-tab-display') || '') : 'none';
            panel.setAttribute('aria-hidden', match ? 'false' : 'true');
          });

          if (shouldDispatch) {
            group.dispatchEvent(new CustomEvent('ditto:tab-change', {
              detail: { target: target },
              bubbles: true,
            }));
          }
        }

        var activeTarget = group.querySelector('[data-tab-target].active, [data-tab-target][aria-selected="true"]') || buttons[0];
        activate(activeTarget, false);

        /* Ensure tablist role */
        if (!group.hasAttribute('role')) {
          group.setAttribute('role', 'tablist');
        }

        /* Ensure buttons have role="tab" and aria-controls */
        var tabButtons = group.querySelectorAll('[data-tab-target]');
        tabButtons.forEach(function (btn) {
          if (!btn.hasAttribute('role')) {
            btn.setAttribute('role', 'tab');
          }
          var target = btn.getAttribute('data-tab-target');
          if (target && !btn.hasAttribute('aria-controls')) {
            btn.setAttribute('aria-controls', target);
          }
        });

        /* Ensure panels have role="tabpanel" and aria-labelledby */
        panels.forEach(function (panel) {
          if (!panel.hasAttribute('role')) {
            panel.setAttribute('role', 'tabpanel');
          }
          var targetPanel = panel.getAttribute('data-tab-panel');
          if (targetPanel && !panel.hasAttribute('aria-labelledby')) {
            var controllingBtn = Array.from(tabButtons).find(function (b) {
              return b.getAttribute('data-tab-target') === targetPanel;
            });
            if (controllingBtn) {
              if (!controllingBtn.id) {
                controllingBtn.id = 'ditto-tab-' + (tabIdCounter++);
              }
              panel.setAttribute('aria-labelledby', controllingBtn.id);
            }
          }
        });

        /* delegated click */
        group.addEventListener('click', function (e) {
          var btn = e.target.closest('[data-tab-target]');
          if (!btn || !group.contains(btn)) return;
          activate(btn, true);
        });

        group.addEventListener('keydown', function (e) {
          var btn = e.target.closest('[data-tab-target]');
          if (!btn || !group.contains(btn)) return;

          var allButtons = Array.from(group.querySelectorAll('[data-tab-target]'));
          var idx = allButtons.indexOf(btn);

          switch (e.key) {
            case 'ArrowRight':
            case 'ArrowDown':
              e.preventDefault();
              var next = allButtons[(idx + 1) % allButtons.length];
              next.focus();
              activate(next, true);
              break;
            case 'ArrowLeft':
            case 'ArrowUp':
              e.preventDefault();
              var prev = allButtons[(idx - 1 + allButtons.length) % allButtons.length];
              prev.focus();
              activate(prev, true);
              break;
            case 'Home':
              e.preventDefault();
              allButtons[0].focus();
              activate(allButtons[0], true);
              break;
            case 'End':
              e.preventDefault();
              allButtons[allButtons.length - 1].focus();
              activate(allButtons[allButtons.length - 1], true);
              break;
            case 'Enter':
            case ' ':
              e.preventDefault();
              activate(btn, true);
              break;
          }
        });
      });
    },

    _resolvePanels: function (group, buttons) {
      var localPanels = Array.from(group.querySelectorAll('[data-tab-panel]'));
      if (localPanels.length) return localPanels;

      var controlledPanels = Tabs._resolveControlledPanels(buttons);
      if (controlledPanels.length) return controlledPanels;

      return [];
    },

    _resolveControlledPanels: function (buttons) {
      var panels = [];
      var seen = new Set();

      for (var i = 0; i < buttons.length; i += 1) {
        var controls = buttons[i].getAttribute('aria-controls');
        if (!controls) return [];

        var panel = document.getElementById(controls);
        if (!panel || !panel.hasAttribute('data-tab-panel')) return [];

        if (!seen.has(panel.id)) {
          seen.add(panel.id);
          panels.push(panel);
        }
      }

      return panels;
    },
  };

  /* ══════════════════════════════════════════════
   * 1a. Radio-backed tab labels
   *     Keeps CSS-radio tab prototypes aligned with ARIA state.
   * ══════════════════════════════════════════════ */
  var RadioTabLabels = {
    init: function () {
      document.querySelectorAll('[role="tablist"]').forEach(function (tablist) {
        RadioTabLabels._syncTablist(tablist);
      });

      document.addEventListener('change', function (event) {
        if (!event.target || event.target.nodeType !== 1) return;
        var input = event.target;
        if (!input.matches('input[type="radio"]')) return;

        document.querySelectorAll('[role="tab"][for="' + (typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(input.id) : input.id) + '"]').forEach(function (tab) {
          var tablist = tab.closest('[role="tablist"]');
          if (tablist) RadioTabLabels._syncTablist(tablist);
        });
      });
    },

    _syncTablist: function (tablist) {
      var tabs = Array.from(tablist.querySelectorAll('[role="tab"][for]'));
      if (!tabs.length) return;

      tabs.forEach(function (tab) {
        var input = document.getElementById(tab.getAttribute('for'));
        if (!input || input.type !== 'radio') return;

        var selected = input.checked;
        tab.setAttribute('aria-selected', selected ? 'true' : 'false');
        tab.setAttribute('tabindex', selected ? '0' : '-1');
        tab.classList.toggle('active', selected);

        var panelId = tab.getAttribute('aria-controls');
        var panel = panelId ? document.getElementById(panelId) : null;
        if (panel) panel.setAttribute('aria-hidden', selected ? 'false' : 'true');
      });
    },
  };

  /* ══════════════════════════════════════════════
   * 1b. Filter Chips
   *     Container: .filter-group
   *     Buttons:   .filter-chip
   * ══════════════════════════════════════════════ */
  var FilterChips = {
    init: function () {
      document.querySelectorAll('.filter-group').forEach(function (group) {
        var chips = Array.from(group.querySelectorAll('.filter-chip'));
        if (!chips.length) return;

        chips.forEach(function (chip) {
          chip.setAttribute('aria-pressed', chip.classList.contains('active') ? 'true' : 'false');
        });

        group.addEventListener('click', function (e) {
          var chip = e.target.closest('.filter-chip');
          if (!chip || !group.contains(chip)) return;
          FilterChips._toggle(chip, group, true);
        });

        group.addEventListener('keydown', function (e) {
          var chip = e.target.closest('.filter-chip');
          if (!chip || !group.contains(chip)) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            FilterChips._toggle(chip, group, true);
          }
        });
      });
    },

    _toggle: function (chip, group, shouldDispatch) {
      var chips = Array.from(group.querySelectorAll('.filter-chip'));
      chips.forEach(function (item) {
        item.classList.remove('active');
        item.setAttribute('aria-pressed', 'false');
      });
      chip.classList.add('active');
      chip.setAttribute('aria-pressed', 'true');

      if (shouldDispatch) {
        group.dispatchEvent(new CustomEvent('ditto:filter-chip-change', {
          detail: { value: chip.textContent.trim() },
          bubbles: true,
        }));
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 1c. Interactive Role Actions
   *     Elements: [role="button"], [role="link"]
   *     Native buttons and links already handle keyboard activation.
   * ══════════════════════════════════════════════ */
  var InteractiveRoleActions = {
    init: function () {
      document.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        if (!event.target || event.target.nodeType !== 1) return;

        var eventTarget = event.target;
        var target = eventTarget.closest('[role="button"], [role="link"]');
        if (!target) return;
        if (target.getAttribute('role') === 'link' && event.key !== 'Enter') return;
        if (InteractiveRoleActions._isNestedInteractiveControl(eventTarget, target)) return;

        event.preventDefault();
        target.click();
      });
    },

    _isNestedInteractiveControl: function (eventTarget, roleAction) {
      if (eventTarget === roleAction) return false;

      var interactive = eventTarget.closest(
        'button, input, select, textarea, a[href], area[href], label, summary, details, iframe, object, embed, audio[controls], video[controls], [contenteditable]:not([contenteditable="false"]), [tabindex]:not([tabindex="-1"]), [role="button"], [role="link"], [role="checkbox"], [role="switch"], [role="radio"], [role="tab"], [role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], [role="combobox"], [role="textbox"], [role="searchbox"], [role="slider"], [role="spinbutton"], [role="listbox"], [role="treeitem"], [data-tab-target]'
      );

      return Boolean(interactive && interactive !== roleAction && roleAction.contains(interactive));
    },
  };

  /* ══════════════════════════════════════════════
   * 1d. Primary Answer Drilldowns
   *     Elements: [data-answer-action][aria-controls], .answer-action[aria-controls]
   * ══════════════════════════════════════════════ */
  var PrimaryAnswerDrilldowns = {
    init: function () {
      document.addEventListener('click', function (event) {
        if (!event.target || event.target.nodeType !== 1) return;

        var action = event.target.closest('[data-answer-action][aria-controls], .answer-action[aria-controls]');
        if (!action) return;

        PrimaryAnswerDrilldowns._activate(action);
      });
    },

    _activate: function (action) {
      var controls = (action.getAttribute('aria-controls') || '').trim().split(/\s+/).filter(Boolean);
      if (!controls.length) return;

      var drilldownTarget = (action.getAttribute('data-drilldown-target') || '').trim();
      var targetIds = drilldownTarget ? [drilldownTarget] : controls;
      var target = targetIds
        .map(function (id) { return document.getElementById(id); })
        .find(function (element) { return element && PrimaryAnswerDrilldowns._isVisible(element); });

      if (!target) return;

      target.setAttribute('data-primary-answer-drilldown', 'active');
      if (!target.hasAttribute('tabindex')) {
        target.setAttribute('tabindex', '-1');
        target.setAttribute('data-primary-answer-temp-tabindex', 'true');
      }
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    },

    _isVisible: function (element) {
      if (element.getAttribute('aria-hidden') === 'true') return false;
      var style = getComputedStyle(element);
      return style.display !== 'none' && style.visibility !== 'hidden';
    },
  };

  /* ══════════════════════════════════════════════
   * 2. Sparkline — data-sparkline='{"data":[...]}'
   * ══════════════════════════════════════════════ */
  var Sparkline = {
    init: function () {
      document.querySelectorAll('[data-sparkline]').forEach(function (svg) {
        var cfg = parseAttr(svg, 'data-sparkline');
        if (!cfg || !cfg.data || cfg.data.length < 2) return;
        Sparkline.render(svg, cfg);
      });
    },

    render: function (svg, cfg) {
      var data = cfg.data;
      var seriesMap = {
        up:      cssVar('--chart-series-up'),
        down:    cssVar('--chart-series-down'),
        neutral: cssVar('--chart-series-neutral'),
        accent:  cssVar('--brand-accent'),
        warning: cssVar('--amber-500'),
      };
      var stroke = seriesMap[cfg.series] || cfg.stroke || cssVar('--chart-series-up', 'oklch(0.670 0.170 20)');
      var sw     = cfg.strokeWidth || parseFloat(cssVar('--sparkline-stroke-width')) || 1.5;
      var w      = cfg.width  || parseFloat(svg.getAttribute('width'))  || parseFloat(cssVar('--sparkline-width'))  || 48;
      var h      = cfg.height || parseFloat(svg.getAttribute('height')) || parseFloat(cssVar('--sparkline-height')) || 20;

      svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      svg.setAttribute('fill', 'none');
      svg.style.width  = w + 'px';
      svg.style.height = h + 'px';

      var min = data.reduce(function (m, v) { return v < m ? v : m; }, Infinity);
      var max = data.reduce(function (m, v) { return v > m ? v : m; }, -Infinity);
      var range = max - min || 1;
      var pad = sw;

      var pts = data.map(function (v, i) {
        return {
          x: pad + (i / (data.length - 1)) * (w - 2 * pad),
          y: pad + (1 - (v - min) / range) * (h - 2 * pad),
        };
      });

      var d = Sparkline.catmullRom(pts);

      /* stroke path */
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      path.setAttribute('stroke', stroke);
      path.setAttribute('stroke-width', String(sw));
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('stroke-linejoin', 'round');
      path.setAttribute('fill', 'none');
      svg.appendChild(path);

      /* optional area fill */
      if (cfg.fill) {
        var fillColor = cfg.fill === true ? stroke.replace(/[^,]+\)$/, ' 0.08)') : cfg.fill;
        var areaD = d + ' L ' + pts[pts.length - 1].x + ',' + h + ' L ' + pts[0].x + ',' + h + ' Z';
        var area = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        area.setAttribute('d', areaD);
        area.setAttribute('fill', fillColor);
        svg.appendChild(area);
      }
    },

    /* Catmull-Rom → Cubic Bezier */
    catmullRom: function (pts) {
      if (pts.length < 2) return '';
      if (pts.length === 2) return 'M ' + pts[0].x + ',' + pts[0].y + ' L ' + pts[1].x + ',' + pts[1].y;
      var d = 'M ' + pts[0].x + ',' + pts[0].y;
      for (var i = 0; i < pts.length - 1; i++) {
        var p0 = pts[Math.max(0, i - 1)];
        var p1 = pts[i];
        var p2 = pts[i + 1];
        var p3 = pts[Math.min(pts.length - 1, i + 2)];
        d += ' C ' +
          (p1.x + (p2.x - p0.x) / 6) + ',' + (p1.y + (p2.y - p0.y) / 6) + ' ' +
          (p2.x - (p3.x - p1.x) / 6) + ',' + (p2.y - (p3.y - p1.y) / 6) + ' ' +
          p2.x + ',' + p2.y;
      }
      return d;
    },
  };

  /* ══════════════════════════════════════════════
   * 3. DonutGauge — data-donut='{"value":0.85}'
   * ══════════════════════════════════════════════ */
  var DonutGauge = {
    init: function () {
      document.querySelectorAll('[data-donut]').forEach(function (svg) {
        var cfg = parseAttr(svg, 'data-donut');
        if (!cfg || cfg.value == null) return;
        DonutGauge.render(svg, cfg);
      });
    },

    render: function (svg, cfg) {
      var value = Math.max(0, Math.min(1, cfg.value));
      var label = cfg.label || Math.round(value * 100) + '%';
      var color = cfg.color || cssVar('--brand-accent', 'oklch(0.700 0.120 235)');
      var track = cfg.trackColor || cssVar('--overlay-6', 'oklch(1 0 0 / 0.06)');
      var size  = cfg.size || 64;
      var sw    = cfg.strokeWidth || Math.max(4, size * 0.1);
      var cx = size / 2;
      var cy = size / 2;
      var r  = (size - sw) / 2;
      var C  = 2 * Math.PI * r;
      var offset = C * (1 - value);

      svg.setAttribute('viewBox', '0 0 ' + size + ' ' + size);
      svg.setAttribute('fill', 'none');
      svg.style.width  = size + 'px';
      svg.style.height = size + 'px';

      /* track */
      var t = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      t.setAttribute('cx', cx); t.setAttribute('cy', cy); t.setAttribute('r', r);
      t.setAttribute('stroke', track); t.setAttribute('stroke-width', sw);
      svg.appendChild(t);

      /* arc */
      var arc = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      arc.setAttribute('cx', cx); arc.setAttribute('cy', cy); arc.setAttribute('r', r);
      arc.setAttribute('stroke', color); arc.setAttribute('stroke-width', sw);
      arc.setAttribute('stroke-linecap', 'round');
      arc.setAttribute('stroke-dasharray', C);
      arc.setAttribute('stroke-dashoffset', reducedMotion ? offset : C);
      arc.setAttribute('transform', 'rotate(-90 ' + cx + ' ' + cy + ')');
      svg.appendChild(arc);

      if (!reducedMotion) {
        requestAnimationFrame(function () {
          arc.style.transition = 'stroke-dashoffset 1s cubic-bezier(0.4,0,0.2,1)';
          arc.setAttribute('stroke-dashoffset', offset);
        });
      }

      /* center label */
      if (label) {
        var txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        txt.setAttribute('x', cx); txt.setAttribute('y', cy);
        txt.setAttribute('text-anchor', 'middle');
        txt.setAttribute('dominant-baseline', 'central');
        txt.setAttribute('fill', cssVar('--text-primary', 'oklch(0.9 0 0)'));
        txt.setAttribute('font-size', Math.max(10, size * 0.2));
        txt.setAttribute('font-family', 'var(--font-family-numeric)');
        txt.textContent = label;
        svg.appendChild(txt);
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 4. HeatGrid — data-heatgrid='{"rows":5,"cols":8}'
   * ══════════════════════════════════════════════ */
  var HeatGrid = {
    init: function () {
      document.querySelectorAll('[data-heatgrid]').forEach(function (svg) {
        var cfg = parseAttr(svg, 'data-heatgrid');
        if (!cfg) return;
        HeatGrid.render(svg, cfg);
      });
    },

    render: function (svg, cfg) {
      var rows = cfg.rows || 5;
      var cols = cfg.cols || 8;
      var data = cfg.data || HeatGrid.autoData(rows, cols);
      var cell = cfg.cellSize || 20;
      var gap  = cfg.gap || 2;
      var w = cols * (cell + gap) - gap;
      var h = rows * (cell + gap) - gap;
      var palette = cfg.colors || [
        cssVar('--heatmap-1-bg', 'oklch(0.6317 0.1567 22.64 / 0.06)'),
        cssVar('--heatmap-2-bg', 'oklch(0.6317 0.1567 22.64 / 0.15)'),
        cssVar('--heatmap-3-bg', 'oklch(1 0 0 / 0.00)'),
        cssVar('--heatmap-4-bg', 'oklch(0.55 0.15 155 / 0.15)'),
        cssVar('--heatmap-5-bg', 'oklch(0.55 0.15 155 / 0.30)'),
      ];

      svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      svg.setAttribute('fill', 'none');
      svg.style.width  = w + 'px';
      svg.style.height = h + 'px';

      for (var r = 0; r < rows; r++) {
        for (var c = 0; c < cols; c++) {
          var val = data[r * cols + c];
          if (val == null) val = Math.random();
          var idx = Math.min(palette.length - 1, Math.floor(val * palette.length));
          var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          rect.setAttribute('x', c * (cell + gap));
          rect.setAttribute('y', r * (cell + gap));
          rect.setAttribute('width', cell);
          rect.setAttribute('height', cell);
          rect.setAttribute('rx', '3');
          rect.setAttribute('fill', palette[idx]);
          rect.setAttribute('class', 'heatgrid-cell');

          /* tooltip — use data-tooltip instead of SVG <title> */
          var tip = cfg.labels && cfg.labels[r * cols + c];
          if (tip) {
            rect.setAttribute('data-tooltip', tip);
          }
          svg.appendChild(rect);
        }
      }
    },

    autoData: function (rows, cols) {
      return Array.from({ length: rows * cols }, function () { return Math.random(); });
    },
  };

  /* ══════════════════════════════════════════════
   * 5. DataCounter — unified animated number display
   *
   *    Trigger modes:
   *      trigger: 'visible'  → IntersectionObserver (animate on viewport entry)
   *      trigger: 'mutation' → MutationObserver (animate on value change)
   *
   *    Backward-compatible aliases:
   *      data-ticker="1234.56"          → trigger: 'visible'
   *      data-counter="1234.56"         → trigger: 'mutation'
   *
   *    Shared config attributes (either prefix):
   *      data-ticker-decimals / data-counter-decimals  (default: 2)
   *      data-ticker-prefix  / data-counter-prefix     (default: '')
   *      data-ticker-suffix  / data-counter-suffix     (default: '')
   *      data-counter-duration                          (default: 1200)
   *
   *    Respects prefers-reduced-motion (shows final value immediately).
   * ══════════════════════════════════════════════ */
  var dataCounterStates = new WeakMap();

  var DataCounter = {
    init: function () {
      /* ── 'visible' trigger: data-ticker (backward compat) ── */
      document.querySelectorAll('[data-ticker]').forEach(function (el) {
        var target = parseFloat(el.getAttribute('data-ticker'));
        if (isNaN(target)) return;
        DataCounter._initElement(el, target, {
          trigger: 'visible',
          decimals: parseInt(el.getAttribute('data-decimals') || '2', 10),
          prefix: el.getAttribute('data-ticker-prefix') || '',
          suffix: el.getAttribute('data-ticker-suffix') || '',
          duration: 1200,
        });
      });

      /* ── 'mutation' trigger: data-counter (backward compat) ── */
      document.querySelectorAll('[data-counter]').forEach(function (el) {
        var target = parseFloat(el.getAttribute('data-counter'));
        if (isNaN(target)) return;
        DataCounter._initElement(el, target, {
          trigger: 'mutation',
          decimals: parseInt(el.getAttribute('data-counter-decimals') || '2', 10),
          prefix: el.getAttribute('data-counter-prefix') || '',
          suffix: el.getAttribute('data-counter-suffix') || '',
          duration: parseInt(el.getAttribute('data-counter-duration') || '1200', 10),
        });
      });
    },

    /**
     * Initialize a single element with its trigger mode.
     * @param {HTMLElement} el
     * @param {number}      target  - initial numeric target
     * @param {Object}      cfg     - { trigger, decimals, prefix, suffix, duration }
     */
    _initElement: function (el, target, cfg) {
      var state = {
        from: 0,
        current: 0,
        decimals: cfg.decimals,
        prefix: cfg.prefix,
        suffix: cfg.suffix,
        duration: cfg.duration,
        raf: null,
        trigger: cfg.trigger,
      };
      dataCounterStates.set(el, state);

      /* reduced-motion: show final value immediately */
      if (reducedMotion) {
        state.current = target;
        var text = state.prefix + DataCounter.format(target, state.decimals) + state.suffix;
        el.textContent = text;
        DataCounter._announce(text);
        return;
      }

      if (cfg.trigger === 'visible') {
        DataCounter._observeVisible(el, state, target);
      } else {
        /* trigger: 'mutation' — animate immediately, then watch for changes */
        DataCounter._animate(el, state, target);
        DataCounter._observeMutation(el, state);
      }
    },

    /**
     * IntersectionObserver: animate once when the element enters the viewport.
     */
    _observeVisible: function (el, state, target) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            DataCounter._animate(el, state, target);
            observer.unobserve(el);
            observer.disconnect();
          }
        });
      }, { threshold: 0.1 });
      observer.observe(el);
    },

    /**
     * MutationObserver: re-animate when data-counter attribute changes.
     */
    _observeMutation: function (el, state) {
      if (typeof MutationObserver === 'undefined') return;
      var mo = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          if (m.type === 'attributes' && m.attributeName === 'data-counter') {
            var newTarget = parseFloat(el.getAttribute('data-counter'));
            if (isNaN(newTarget)) return;
            state.from = state.current;
            DataCounter._animate(el, state, newTarget);
          }
        });
      });
      mo.observe(el, { attributes: true, attributeFilter: ['data-counter'] });
    },

    /**
     * Shared easing animation: ease-out cubic.
     * Animates from state.from to target over state.duration ms.
     */
    _animate: function (el, state, target) {
      if (state.raf) cancelAnimationFrame(state.raf);
      var startTime = performance.now();

      function tick(now) {
        var p = Math.min((now - startTime) / state.duration, 1);
        /* ease-out cubic */
        var eased = 1 - Math.pow(1 - p, 3);
        var val = state.from + (target - state.from) * eased;
        state.current = val;
        el.textContent = state.prefix + DataCounter.format(val, state.decimals) + state.suffix;
        if (p < 1) {
          state.raf = requestAnimationFrame(tick);
        } else {
          state.current = target;
          state.raf = null;
          DataCounter._announce(state.prefix + DataCounter.format(target, state.decimals) + state.suffix);
        }
      }
      state.raf = requestAnimationFrame(tick);
    },

    /**
     * Thousand-separator formatting (e.g. 8432180.50 → "8,432,180.50").
     */
    format: function (num, decimals) {
      var parts = num.toFixed(decimals).split('.');
      parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return parts.join('.');
    },

    /**
     * Accessibility: announce the final value via live region.
     */
    _announce: function (text) {
      var liveRegion = document.querySelector('[role="status"].live-region');
      if (liveRegion) {
        liveRegion.textContent = text;
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 6. ScrollReveal — data-reveal="fade-up"
   * ══════════════════════════════════════════════ */
  var ScrollReveal = {
    transforms: {
      'fade-up':    'translateY(16px)',
      'fade-down':  'translateY(-16px)',
      'fade-left':  'translateX(-16px)',
      'fade-right': 'translateX(16px)',
      'scale-up':   'scale(0.95)',
      'fade':       '',
    },

    init: function () {
      if (reducedMotion) return;
      var items = document.querySelectorAll('[data-reveal]');
      if (!items.length) return;

      items.forEach(function (el) {
        el.style.opacity = '0';
        var tf = ScrollReveal.transforms[el.getAttribute('data-reveal')] || 'translateY(16px)';
        if (tf) el.style.transform = tf;
        el.style.transition = 'opacity 0.5s cubic-bezier(0.4,0,0.2,1), transform 0.5s cubic-bezier(0.4,0,0.2,1)';
      });

      var observedCount = items.length;
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var el = entry.target;
          var delay = parseInt(el.getAttribute('data-reveal-delay') || '0', 10);
          setTimeout(function () {
            el.style.opacity = '1';
            el.style.transform = '';
            observer.unobserve(el);
            observedCount -= 1;
            if (observedCount === 0) {
              observer.disconnect();
            }
          }, delay);
        });
      }, { threshold: 0.1 });

      items.forEach(function (el) { observer.observe(el); });
    },
  };

  /* ══════════════════════════════════════════════
   * 8. ConfidenceBar — data-confidence="0.92"
   * ══════════════════════════════════════════════ */
  var ConfidenceBar = {
    init: function () {
      document.querySelectorAll('[data-confidence]').forEach(function (el) {
        var value = parseFloat(el.getAttribute('data-confidence'));
        if (isNaN(value)) return;
        ConfidenceBar.render(el, value, el.getAttribute('data-confidence-label') || '');
      });
    },

    color: function (v) {
      if (v >= 0.8) return cssVar('--chart-series-up', 'oklch(0.55 0.15 155)');
      if (v >= 0.6) return cssVar('--amber-500', 'oklch(0.746 0.165 50)');
      return cssVar('--red-600', 'oklch(0.6317 0.1567 22.64)');
    },

    render: function (el, value, label) {
      var pct   = Math.max(0, Math.min(1, value)) * 100;
      var color = ConfidenceBar.color(value);
      el.innerHTML = '';

      var track = document.createElement('div');
      track.className = 'confidence-track';

      var fill = document.createElement('div');
      fill.className = 'confidence-fill';
      fill.style.background = color;
      fill.style.width = reducedMotion ? pct + '%' : '0%';

      track.appendChild(fill);
      el.appendChild(track);

      if (label) {
        var span = document.createElement('span');
        span.className = 'confidence-label';
        span.textContent = label;
        el.appendChild(span);
      }

      if (!reducedMotion) {
        requestAnimationFrame(function () { fill.style.width = pct + '%'; });
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 9. FlowBar — data-flow='{"segments":[...]}'
   * ══════════════════════════════════════════════ */
  var FlowBar = {
    palette: [
      cssVar('--brand-accent', 'oklch(0.700 0.120 235)'),
      cssVar('--brand-accent', 'oklch(0.700 0.120 235 / 0.55)'),
      cssVar('--chart-series-up', 'oklch(0.55 0.15 155)'),
      cssVar('--amber-500', 'oklch(0.746 0.165 50)'),
      cssVar('--overlay-8', 'oklch(1 0 0 / 0.08)'),
    ],

    init: function () {
      document.querySelectorAll('[data-flow]').forEach(function (el) {
        var cfg = parseAttr(el, 'data-flow');
        if (!cfg || !cfg.segments) return;
        FlowBar.render(el, cfg);
      });
    },

    render: function (el, cfg) {
      var segs  = cfg.segments;
      var total = segs.reduce(function (s, seg) { return s + (seg.value || 0); }, 0);
      if (total === 0) return;

      el.innerHTML = '';
      el.classList.add('flow-bar');

      segs.forEach(function (seg, i) {
        var pct = ((seg.value / total) * 100).toFixed(1);
        var bar = document.createElement('div');
        bar.className = 'flow-segment';
        bar.style.flex = String(seg.value);
        bar.style.background = FlowBar.palette[i % FlowBar.palette.length];
        if (seg.label) bar.setAttribute('data-tooltip', seg.label + ': ' + seg.value + ' (' + pct + '%)');
        el.appendChild(bar);
      });
    },
  };

  /* ══════════════════════════════════════════════
   * 11. TooltipSystem — data-tooltip="text"
   *     Singleton tooltip with auto-positioning
   *     Event delegation for minimal overhead
   * ══════════════════════════════════════════════ */
  var TooltipSystem = {
    el: null,
    timer: null,
    currentTrigger: null,

    init: function () {
      if (!document.querySelector('[data-tooltip]')) return;

      /* Create singleton tooltip element */
      if (!TooltipSystem.el) {
        TooltipSystem.el = document.createElement('div');
        TooltipSystem.el.className = 'ditto-tooltip';
        TooltipSystem.el.setAttribute('role', 'tooltip');
        TooltipSystem.el.setAttribute('aria-hidden', 'true');
        document.body.appendChild(TooltipSystem.el);
      }

      /* Event delegation */
      document.addEventListener('mouseover', TooltipSystem._onOver, true);
      document.addEventListener('mouseout', TooltipSystem._onOut, true);
      document.addEventListener('focusin', TooltipSystem._onOver, true);
      document.addEventListener('focusout', TooltipSystem._onOut, true);

      /* Touch device support: long-press (500ms) to show tooltip */
      var touchTimer = null;
      document.addEventListener('touchstart', function (e) {
        var trigger = e.target.closest('[data-tooltip]');
        if (!trigger) return;
        touchTimer = setTimeout(function () {
          var text = trigger.getAttribute('data-tooltip');
          if (text) TooltipSystem.show(trigger, text);
        }, 500);
      }, { passive: true });

      document.addEventListener('touchend', function () {
        if (touchTimer) {
          clearTimeout(touchTimer);
          touchTimer = null;
        }
        TooltipSystem.hide();
      }, { passive: true });
    },

    _onOver: function (e) {
      var target = e.target.closest('[data-tooltip]');
      if (!target) return;

      var text = target.getAttribute('data-tooltip');
      if (!text) return;

      clearTimeout(TooltipSystem.timer);
      var delay = parseInt(target.getAttribute('data-tooltip-delay') || '300', 10);

      TooltipSystem.timer = setTimeout(function () {
        TooltipSystem.show(target, text);
      }, delay);
    },

    _onOut: function (e) {
      var target = e.target.closest('[data-tooltip]');
      if (!target) return;

      /* Skip if focus moves to a child within the same trigger */
      if (e.type === 'focusout') {
        var related = e.relatedTarget;
        if (related && target.contains(related)) return;
      }
      if (e.type === 'mouseout') {
        var related = e.relatedTarget;
        if (related && target.contains(related)) return;
      }

      clearTimeout(TooltipSystem.timer);
      TooltipSystem.hide();
    },

    show: function (anchor, text) {
      var el = TooltipSystem.el;
      var pos = anchor.getAttribute('data-tooltip-pos') || 'bottom';
      el.textContent = text;
      el.setAttribute('aria-hidden', 'false');

      /* Link trigger to tooltip via aria-describedby */
      TooltipSystem._clearDescribedBy();
      var tooltipId = 'ditto-tooltip-' + Date.now();
      el.id = tooltipId;
      anchor.setAttribute('aria-describedby', tooltipId);
      TooltipSystem.currentTrigger = anchor;
      el.style.visibility = 'hidden';
      el.style.display = 'block';

      /* Wait a frame for layout measurement */
      requestAnimationFrame(function () {
        var anchorRect = anchor.getBoundingClientRect();
        var tipRect = el.getBoundingClientRect();
        var gap = 8;
        var x, y;

        /* Position calculation */
        if (pos === 'top') {
          x = anchorRect.left + (anchorRect.width - tipRect.width) / 2;
          y = anchorRect.top - tipRect.height - gap;
        } else if (pos === 'left') {
          x = anchorRect.left - tipRect.width - gap;
          y = anchorRect.top + (anchorRect.height - tipRect.height) / 2;
        } else if (pos === 'right') {
          x = anchorRect.right + gap;
          y = anchorRect.top + (anchorRect.height - tipRect.height) / 2;
        } else {
          /* bottom (default) */
          x = anchorRect.left + (anchorRect.width - tipRect.width) / 2;
          y = anchorRect.bottom + gap;
        }

        /* Boundary detection — flip if overflowing */
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        if (x < 4) x = 4;
        if (x + tipRect.width > vw - 4) x = vw - tipRect.width - 4;
        if (y < 4) {
          /* Flip to opposite side if off-screen top */
          if (pos === 'top') y = anchorRect.bottom + gap;
          else y = 4;
        }
        if (y + tipRect.height > vh - 4) {
          if (pos === 'bottom') y = anchorRect.top - tipRect.height - gap;
          else y = vh - tipRect.height - 4;
        }

        el.style.left = x + 'px';
        el.style.top = y + 'px';
        el.style.visibility = '';
        el.classList.add('ditto-tooltip--visible');
      });
    },

    hide: function () {
      if (!TooltipSystem.el) return;
      TooltipSystem._clearDescribedBy();
      TooltipSystem.el.classList.remove('ditto-tooltip--visible');
      TooltipSystem.el.setAttribute('aria-hidden', 'true');
      /* Delay display:none to allow fade-out */
      setTimeout(function () {
        if (!TooltipSystem.el.classList.contains('ditto-tooltip--visible')) {
          TooltipSystem.el.style.display = 'none';
        }
      }, 150);
    },

    _clearDescribedBy: function () {
      if (TooltipSystem.currentTrigger) {
        var describedby = TooltipSystem.currentTrigger.getAttribute('aria-describedby');
        if (describedby && describedby.startsWith('ditto-tooltip-')) {
          TooltipSystem.currentTrigger.removeAttribute('aria-describedby');
        }
        TooltipSystem.currentTrigger = null;
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 12. CollapsibleContextSections
   *     Native <details>/<summary> contract enhancement
   * ══════════════════════════════════════════════ */
  var CollapsibleContextSections = {
    init: function () {
      document.querySelectorAll('details.context-section').forEach(function (details) {
        var summary = CollapsibleContextSections._directSummary(details);
        if (!summary || !summary.classList.contains('context-section-header')) return;

        CollapsibleContextSections._sync(details, summary);
        if (details.getAttribute('data-collapsible-context-ready') === 'true') return;

        details.setAttribute('data-collapsible-context-ready', 'true');
        details.addEventListener('toggle', function () {
          CollapsibleContextSections._sync(details, summary);
        });
      });
    },

    _directSummary: function (details) {
      for (var i = 0; i < details.children.length; i++) {
        if (details.children[i].tagName.toLowerCase() === 'summary') {
          return details.children[i];
        }
      }
      return null;
    },

    _sync: function (details, summary) {
      summary.setAttribute('aria-expanded', details.open ? 'true' : 'false');
    },
  };

  /* ══════════════════════════════════════════════
   * 13. SidebarToggle
   *     Shared right sidebar expanded/collapsed state
   * ══════════════════════════════════════════════ */
  var SidebarToggle = {
    states: ['expanded', 'collapsed'],

    init: function () {
      document.querySelectorAll('[data-sidebar-shell]').forEach(function (shell) {
        var toggle = shell.querySelector('[data-sidebar-toggle]');
        var sidebar = shell.querySelector('[data-sidebar]');
        if (!toggle || !sidebar) return;

        var state = SidebarToggle._state(shell);
        SidebarToggle._sync(shell, sidebar, toggle, state);

        if (toggle.getAttribute('data-sidebar-toggle-ready') === 'true') return;
        toggle.setAttribute('data-sidebar-toggle-ready', 'true');
        toggle.addEventListener('click', function () {
          var next = SidebarToggle._state(shell) === 'expanded' ? 'collapsed' : 'expanded';
          SidebarToggle._sync(shell, sidebar, toggle, next);
        });
      });
    },

    _state: function (shell) {
      var state = shell.getAttribute('data-sidebar-state') || 'expanded';
      return SidebarToggle.states.indexOf(state) >= 0 ? state : 'expanded';
    },

    _sync: function (shell, sidebar, toggle, state) {
      var isExpanded = state === 'expanded';
      var collapsedStrip = sidebar.querySelector('[data-sidebar-collapsed-strip]');

      shell.setAttribute('data-sidebar-state', state);
      toggle.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
      toggle.setAttribute('aria-label', isExpanded ? '折叠侧边栏' : '展开侧边栏');
      toggle.setAttribute('title', isExpanded ? '折叠侧边栏' : '展开侧边栏');
      toggle.textContent = isExpanded ? '»' : '«';

      sidebar.querySelectorAll('.context-section').forEach(function (section) {
        section.setAttribute('aria-hidden', isExpanded ? 'false' : 'true');
      });

      if (collapsedStrip) {
        collapsedStrip.setAttribute('aria-hidden', isExpanded ? 'true' : 'false');
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 14. CommandPalette
   *     Prototype-only selected object command suggestions
   *     Features: search/filter, keyboard nav, category grouping, recent items
   * ══════════════════════════════════════════════ */
  var CommandPalette = {
    RECENT_KEY: 'ditto-recent-commands',
    MAX_RECENT: 3,
    triggerEl: null,
    confirmationTriggerEl: null,
    _pendingConfirmationAction: null,
    activeIndex: -1,
    actionRegistry: {
      'add-to-compare': {
        action: 'add-to-compare',
        label: '加入对比',
        category: '上下文操作',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '加入当前对比篮',
        result: '已加入回测对比',
      },
      approve: {
        action: 'approve',
        label: '批准',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '批准当前信号',
        result: '已提交批准记录',
      },
      'clone-strategy': {
        action: 'clone-strategy',
        label: '复制策略',
        category: '策略',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '生成可编辑副本',
        result: '策略副本已创建',
      },
      'copy-params': {
        action: 'copy-params',
        label: '复制参数',
        category: '策略',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '复制参数快照',
        result: '参数已复制',
      },
      'create-incident': {
        action: 'create-incident',
        label: '创建事件',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '创建平台事件单',
        result: '事件单已创建',
      },
      'explain-priority': {
        action: 'explain-priority',
        label: '解释优先级',
        category: '上下文操作',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '展开优先级依据',
        result: '优先级解释已打开',
      },
      'generate-report': {
        action: 'generate-report',
        label: '生成报告',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '生成回测报告草稿',
        result: '报告任务已启动',
      },
      'generate-signal': {
        action: 'generate-signal',
        label: '生成信号',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '生成观察标的信号',
        result: '信号生成已排队',
      },
      'mute-alert': {
        action: 'mute-alert',
        label: '静音告警',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '暂时降低告警噪声',
        result: '告警已静音',
      },
      'open-instrument-hub': {
        action: 'open-instrument-hub',
        label: '打开标的 Hub',
        category: '导航',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '跳转标的工作台',
        result: '标的 Hub 已准备打开',
      },
      'open-orders': {
        action: 'open-orders',
        label: '打开订单',
        category: '导航',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '查看关联订单',
        result: '订单视图已定位',
      },
      'open-risk': {
        action: 'open-risk',
        label: '打开风控',
        category: '导航',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '查看风险约束',
        result: '风控面板已定位',
      },
      'pause-strategy': {
        action: 'pause-strategy',
        label: '暂停策略',
        category: '策略',
        object: 'selected-object',
        riskLevel: 'high',
        preview: '暂停后续自动运行',
        result: '已提交暂停请求',
      },
      reject: {
        action: 'reject',
        label: '拒绝',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'high',
        preview: '拒绝当前信号',
        result: '已提交拒绝记录',
      },
      'remove-watch': {
        action: 'remove-watch',
        label: '移出观察',
        category: '上下文操作',
        object: 'selected-object',
        riskLevel: 'high',
        preview: '从观察列表移除',
        result: '已移出观察列表',
      },
      retry: {
        action: 'retry',
        label: '重试',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '重新执行失败任务',
        result: '重试任务已派发',
      },
      'review-signal': {
        action: 'review-signal',
        label: '复核信号',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '检查证据链',
        result: '已排入复核工作流',
      },
      'run-backtest': {
        action: 'run-backtest',
        label: '运行回测',
        category: '策略',
        object: 'selected-object',
        riskLevel: 'medium',
        preview: '按当前参数运行回测',
        result: '回测任务已启动',
      },
      'send-to-order': {
        action: 'send-to-order',
        label: '发送到订单',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'high',
        preview: '发送至订单准备队列',
        result: '已提交订单准备请求',
      },
      'send-to-research': {
        action: 'send-to-research',
        label: '发送到研究',
        category: '工作流',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '生成研究待办',
        result: '研究待办已创建',
      },
      'view-curve': {
        action: 'view-curve',
        label: '查看曲线',
        category: '导航',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '打开权益曲线',
        result: '曲线视图已定位',
      },
      'view-evidence': {
        action: 'view-evidence',
        label: '查看证据',
        category: '上下文操作',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '展开信号证据',
        result: '证据面板已定位',
      },
      'view-logs': {
        action: 'view-logs',
        label: '查看日志',
        category: '导航',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '打开关联日志',
        result: '日志视图已定位',
      },
      'view-recent-runs': {
        action: 'view-recent-runs',
        label: '查看近期运行',
        category: '导航',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '打开运行历史',
        result: '近期运行已定位',
      },
    },

    init: function () {
      var triggers = Array.from(document.querySelectorAll('[data-shell-utility="command"], .header-command-trigger'));
      if (!triggers.length) return;

      var palette = CommandPalette._ensurePalette();

      triggers.forEach(function (trigger) {
        trigger.setAttribute('aria-haspopup', 'dialog');
        trigger.setAttribute('aria-expanded', 'false');
        trigger.setAttribute('aria-controls', palette.id);

        if (trigger.getAttribute('data-command-trigger-ready') === 'true') return;
        trigger.setAttribute('data-command-trigger-ready', 'true');
        trigger.addEventListener('click', function () {
          CommandPalette._open(palette, trigger);
        });
      });

      if (document.documentElement.getAttribute('data-command-palette-ready') === 'true') return;
      document.documentElement.setAttribute('data-command-palette-ready', 'true');
      document.addEventListener('keydown', function (event) {
        var key = event.key ? event.key.toLowerCase() : '';
        if ((event.ctrlKey || event.metaKey) && key === 'k') {
          event.preventDefault();
          CommandPalette._open(palette, triggers[0]);
        }
      });

      /* Handle overlayclose from OverlayStack (Esc key stacking) */
      palette.addEventListener('overlayclose', function (e) {
        e.preventDefault();
        CommandPalette._close(palette);
      });
    },

    _ensurePalette: function () {
      var existing = document.querySelector('[data-command-palette]');
      if (existing) return existing;

      var palette = document.createElement('section');
      palette.id = 'prototype-command-palette';
      palette.className = 'ditto-command-palette';
      palette.setAttribute('data-command-palette', '');
      palette.setAttribute('role', 'dialog');
      palette.setAttribute('aria-label', '命令面板');
      palette.setAttribute('aria-hidden', 'true');
      palette.hidden = true;

      /* Search input */
      var searchWrap = document.createElement('div');
      searchWrap.className = 'ditto-command-search-wrap';
      var searchIcon = document.createElement('span');
      searchIcon.className = 'ditto-command-search-icon';
      searchIcon.setAttribute('aria-hidden', 'true');
      searchIcon.textContent = '\u{1F50D}';
      var searchInput = document.createElement('input');
      searchInput.type = 'text';
      searchInput.className = 'ditto-command-search';
      searchInput.setAttribute('data-command-search', '');
      searchInput.setAttribute('placeholder', '搜索命令...');
      searchInput.setAttribute('aria-label', '搜索命令');
      searchInput.autocomplete = 'off';
      searchWrap.appendChild(searchIcon);
      searchWrap.appendChild(searchInput);

      /* Scrollable results area */
      var results = document.createElement('div');
      results.className = 'ditto-command-results';
      results.setAttribute('data-command-results', '');
      results.setAttribute('role', 'listbox');
      results.setAttribute('aria-label', '命令列表');

      palette.appendChild(searchWrap);
      palette.appendChild(results);
      document.body.appendChild(palette);

      /* Search input: filter on type */
      searchInput.addEventListener('input', function () {
        CommandPalette._filterResults(palette, searchInput.value);
      });

      /* Keyboard navigation within palette */
      palette.addEventListener('keydown', function (e) {
        var key = e.key;
        if (key === 'ArrowDown' || key === 'ArrowUp') {
          e.preventDefault();
          CommandPalette._navigateItems(palette, key === 'ArrowDown' ? 1 : -1);
        } else if (key === 'Enter') {
          e.preventDefault();
          CommandPalette._activateCurrent(palette);
        } else if (key === 'Tab') {
          /* Focus trap: Tab/Shift+Tab wraps within dialog */
          var searchInput = palette.querySelector('[data-command-search]');
          var items = palette.querySelectorAll('[data-command-item]');
          if (!items.length) return;
          var firstItem = items[0];
          var lastItem = items[items.length - 1];
          if (e.shiftKey && document.activeElement === firstItem) {
            e.preventDefault();
            lastItem.focus();
          } else if (!e.shiftKey && document.activeElement === lastItem) {
            e.preventDefault();
            firstItem.focus();
          } else if (e.shiftKey && document.activeElement === searchInput) {
            e.preventDefault();
            lastItem.focus();
          } else if (!e.shiftKey && document.activeElement === searchInput) {
            e.preventDefault();
            firstItem.focus();
          }
        }
      });

      return palette;
    },

    _readContext: function () {
      var context = document.querySelector('[data-command-context-object]') || document.querySelector('[data-command-context-actions]');
      var actions = ((context && context.getAttribute('data-command-context-actions')) || '')
        .split(',')
        .map(function (action) { return action.trim(); })
        .filter(Boolean);

      return {
        object: (context && context.getAttribute('data-command-context-object')) || 'global',
        route: (context && context.getAttribute('data-command-context-route')) || CommandPalette._routeKey(),
        actions: actions,
      };
    },

    _routeKey: function () {
      var path = (window.location && window.location.pathname) || '/';
      return path || '/';
    },

    _storageKey: function (context) {
      var route = (context && context.route) || CommandPalette._routeKey();
      var object = (context && context.object) || 'global';
      return CommandPalette.RECENT_KEY + '::' + encodeURIComponent(route) + '::' + encodeURIComponent(object);
    },

    /* Read data-command-category from action elements in the page */
    _readCategories: function () {
      var map = {};
      document.querySelectorAll('[data-command-category]').forEach(function (el) {
        var action = el.getAttribute('data-command-action') || el.getAttribute('data-command-suggestion');
        var cat = el.getAttribute('data-command-category');
        if (action && cat) map[action] = cat;
      });
      return map;
    },

    _getRecent: function (context) {
      try {
        var raw = window.localStorage.getItem(CommandPalette._storageKey(context || CommandPalette._readContext()));
        if (!raw) return [];
        var parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed.slice(0, CommandPalette.MAX_RECENT);
      } catch (_) {
        return [];
      }
    },

    _addRecent: function (action, context) {
      var scopedContext = context || CommandPalette._readContext();
      var recent = CommandPalette._getRecent(scopedContext);
      /* Remove if already present */
      recent = recent.filter(function (r) { return r !== action; });
      recent.unshift(action);
      recent = recent.slice(0, CommandPalette.MAX_RECENT);
      try {
        window.localStorage.setItem(CommandPalette._storageKey(scopedContext), JSON.stringify(recent));
      } catch (_) { /* storage full or disabled */ }
    },

    _resolveAction: function (action, context, pageCategories) {
      var base = CommandPalette.actionRegistry[action] || {
        action: action,
        label: action,
        category: '全局操作',
        object: 'selected-object',
        riskLevel: 'low',
        preview: '执行上下文动作',
        result: '动作已完成',
      };

      return {
        action: base.action,
        label: base.label,
        category: pageCategories[action] || base.category,
        object: context.object,
        route: context.route,
        riskLevel: base.riskLevel || 'low',
        preview: base.preview,
        result: base.result,
      };
    },

    _render: function (palette) {
      var context = CommandPalette._readContext();
      var results = palette.querySelector('[data-command-results]');
      var searchInput = palette.querySelector('[data-command-search]');
      if (!results) return;

      /* Clear search and results */
      if (searchInput) searchInput.value = '';
      CommandPalette.activeIndex = -1;
      while (results.firstChild) results.removeChild(results.firstChild);

      if (!context.actions.length) {
        var empty = document.createElement('div');
        empty.className = 'ditto-command-empty';
        empty.textContent = '当前页面暂无对象上下文动作';
        results.appendChild(empty);
        return;
      }

      /* Build full items list with labels and categories */
      var pageCategories = CommandPalette._readCategories();
      var recentActions = CommandPalette._getRecent(context);
      var allItems = context.actions.map(function (action) {
        return CommandPalette._resolveAction(action, context, pageCategories);
      });

      /* Render grouped */
      CommandPalette._renderGrouped(results, allItems, recentActions);
    },

    _renderGrouped: function (container, items, recentActions) {
      /* Separate recent vs non-recent */
      var recentSet = {};
      var itemsByAction = {};
      items.forEach(function (item) { itemsByAction[item.action] = item; });
      recentActions.forEach(function (r) { recentSet[r] = true; });

      var recentItems = recentActions
        .map(function (action) { return itemsByAction[action]; })
        .filter(Boolean);
      var otherItems = items.filter(function (item) { return !recentSet[item.action]; });

      /* Group other items by category */
      var groups = {};
      otherItems.forEach(function (item) {
        if (!groups[item.category]) groups[item.category] = [];
        groups[item.category].push(item);
      });

      /* Render recent section */
      if (recentItems.length > 0) {
        CommandPalette._renderSection(container, '最近使用', recentItems);
      }

      /* Render category sections in stable order */
      var categoryOrder = ['上下文操作', '工作流', '策略', '导航', '全局操作'];
      var seen = {};
      categoryOrder.forEach(function (cat) {
        if (groups[cat] && groups[cat].length) {
          CommandPalette._renderSection(container, cat, groups[cat]);
          seen[cat] = true;
        }
      });
      Object.keys(groups).sort().forEach(function (cat) {
        if (!seen[cat]) {
          CommandPalette._renderSection(container, cat, groups[cat]);
        }
      });
    },

    _renderSection: function (container, title, items) {
      var section = document.createElement('div');
      section.className = 'ditto-command-section';
      if (title === '最近使用') section.setAttribute('data-command-recent-section', '');
      container.appendChild(section);

      var header = document.createElement('div');
      header.className = 'ditto-command-category';
      header.setAttribute('role', 'presentation');
      header.textContent = title;
      section.appendChild(header);

      items.forEach(function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ditto-command-item';
        btn.setAttribute('data-command-suggestion', '');
        btn.setAttribute('data-command-item', '');
        btn.setAttribute('data-command-action', item.action);
        btn.setAttribute('data-command-context-object', item.object);
        btn.setAttribute('data-command-label', item.label);
        btn.setAttribute('data-command-category-item', item.category);
        btn.setAttribute('data-command-risk-level', item.riskLevel);
        btn.setAttribute('data-command-preview', item.preview);
        btn.setAttribute('data-command-result', item.result);
        btn.setAttribute('role', 'option');

        var text = document.createElement('span');
        text.className = 'ditto-command-item-text';
        var label = document.createElement('span');
        label.className = 'ditto-command-item-label';
        label.textContent = item.label;
        var meta = document.createElement('span');
        meta.className = 'ditto-command-item-meta';
        meta.textContent = item.preview;
        text.appendChild(label);
        text.appendChild(meta);
        btn.appendChild(text);

        if (item.riskLevel === 'high') {
          var badge = document.createElement('span');
          badge.className = 'ditto-command-risk';
          badge.textContent = '需确认';
          btn.appendChild(badge);
        }

        btn.addEventListener('click', function () {
          CommandPalette._activateAction(item, container.closest('[data-command-palette]'));
        });
        section.appendChild(btn);
      });
    },

    _filterResults: function (palette, query) {
      var results = palette.querySelector('[data-command-results]');
      if (!results) return;
      var q = (query || '').toLowerCase().trim();
      CommandPalette.activeIndex = -1;

      var items = results.querySelectorAll('[data-command-item]');
      var categories = results.querySelectorAll('.ditto-command-category');

      if (!q) {
        /* Show all */
        items.forEach(function (item) { item.style.display = ''; });
        categories.forEach(function (cat) { cat.style.display = ''; });
        return;
      }

      /* Fuzzy match: check if all characters in q appear in order in the text */
      function fuzzyMatch(text, query) {
        var t = text.toLowerCase();
        var qi = 0;
        for (var ti = 0; ti < t.length && qi < query.length; ti++) {
          if (t[ti] === query[qi]) qi++;
        }
        return qi === query.length;
      }

      /* Track which categories have visible items */
      var visibleCategories = {};

      items.forEach(function (item) {
        var label = (item.getAttribute('data-command-label') || item.textContent).toLowerCase();
        var action = (item.getAttribute('data-command-action') || '').toLowerCase();
        var match = fuzzyMatch(label, q) || fuzzyMatch(action, q);
        item.style.display = match ? '' : 'none';
        if (match) {
          var cat = item.getAttribute('data-command-category-item');
          if (cat) visibleCategories[cat] = true;
        }
      });

      categories.forEach(function (cat) {
        var section = cat.parentElement;
        var visibleInSection = false;
        if (section) {
          section.querySelectorAll('[data-command-item]').forEach(function (item) {
            if (item.style.display !== 'none') visibleInSection = true;
          });
        }
        cat.style.display = visibleInSection || visibleCategories[cat.textContent] ? '' : 'none';
      });
    },

    _navigateItems: function (palette, direction) {
      var items = palette.querySelectorAll('[data-command-item]:not([style*="display: none"])');
      if (!items.length) return;

      /* Clear previous highlight */
      if (CommandPalette.activeIndex >= 0 && CommandPalette.activeIndex < items.length) {
        items[CommandPalette.activeIndex].classList.remove('command-item-active');
      }

      /* Calculate new index */
      CommandPalette.activeIndex += direction;
      if (CommandPalette.activeIndex < 0) CommandPalette.activeIndex = items.length - 1;
      if (CommandPalette.activeIndex >= items.length) CommandPalette.activeIndex = 0;

      var target = items[CommandPalette.activeIndex];
      target.classList.add('command-item-active');
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: 'nearest' });
    },

    _activateCurrent: function (palette) {
      /* If search input is focused and no item active, activate first visible */
      var items = palette.querySelectorAll('[data-command-item]:not([style*="display: none"])');
      var idx = CommandPalette.activeIndex;
      if (idx < 0 || idx >= items.length) idx = 0;
      if (!items.length) return;

      var item = items[idx];
      item.click();
    },

    _activateAction: function (item, palette) {
      if (!item || !item.action) return;
      if (item.riskLevel === 'high') {
        CommandPalette._openConfirmation(item, palette);
        return;
      }
      CommandPalette._completeAction(item, palette);
    },

    _completeAction: function (item, palette) {
      CommandPalette._addRecent(item.action, item);
      CommandPalette._showFeedback(item);
      if (palette && !palette.hidden) CommandPalette._close(palette);
    },

    _ensureFeedback: function () {
      var existing = document.querySelector('[data-command-action-feedback]');
      if (existing) return existing;

      var feedback = document.createElement('aside');
      feedback.className = 'ditto-command-feedback';
      feedback.setAttribute('data-command-action-feedback', '');
      feedback.setAttribute('role', 'status');
      feedback.setAttribute('aria-live', 'polite');
      feedback.hidden = true;
      document.body.appendChild(feedback);
      return feedback;
    },

    _appendFeedbackRow: function (container, label, value) {
      var row = document.createElement('div');
      row.className = 'ditto-command-feedback-row';
      var key = document.createElement('span');
      key.className = 'ditto-command-feedback-key';
      key.textContent = label;
      var val = document.createElement('span');
      val.className = 'ditto-command-feedback-value';
      val.textContent = value;
      row.appendChild(key);
      row.appendChild(val);
      container.appendChild(row);
    },

    _showFeedback: function (item) {
      var feedback = CommandPalette._ensureFeedback();
      while (feedback.firstChild) feedback.removeChild(feedback.firstChild);

      feedback.setAttribute('data-command-feedback-action', item.action);
      feedback.setAttribute('data-command-feedback-risk', item.riskLevel);

      var title = document.createElement('div');
      title.className = 'ditto-command-feedback-title';
      title.textContent = '动作完成';
      feedback.appendChild(title);
      CommandPalette._appendFeedbackRow(feedback, '命令', item.label);
      CommandPalette._appendFeedbackRow(feedback, '对象', item.object);
      CommandPalette._appendFeedbackRow(feedback, '影响', item.preview);
      CommandPalette._appendFeedbackRow(feedback, '结果', item.result);

      feedback.hidden = false;
    },

    _ensureConfirmation: function () {
      var existing = document.querySelector('[data-command-confirmation]');
      if (existing) return existing;

      var dialog = document.createElement('section');
      dialog.className = 'ditto-command-confirmation';
      dialog.setAttribute('data-command-confirmation', '');
      dialog.setAttribute('data-overlay', 'command-confirmation');
      dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');
      dialog.setAttribute('aria-hidden', 'true');
      dialog.setAttribute('aria-labelledby', 'command-confirmation-title');
      dialog.setAttribute('aria-describedby', 'command-confirmation-body');
      dialog.hidden = true;

      var surface = document.createElement('div');
      surface.className = 'ditto-command-confirmation-surface';

      var title = document.createElement('h2');
      title.id = 'command-confirmation-title';
      title.className = 'ditto-command-confirmation-title';
      title.textContent = '确认高风险动作';

      var body = document.createElement('div');
      body.id = 'command-confirmation-body';
      body.className = 'ditto-command-confirmation-body';
      body.setAttribute('data-command-confirm-body', '');

      var actions = document.createElement('div');
      actions.className = 'ditto-command-confirmation-actions';

      var cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'ditto-command-confirmation-button ditto-command-confirmation-button-secondary';
      cancel.setAttribute('data-command-confirm-cancel', '');
      cancel.textContent = '取消';

      var confirm = document.createElement('button');
      confirm.type = 'button';
      confirm.className = 'ditto-command-confirmation-button ditto-command-confirmation-button-primary';
      confirm.setAttribute('data-command-confirm-submit', '');
      confirm.textContent = '确认执行';

      actions.appendChild(cancel);
      actions.appendChild(confirm);
      surface.appendChild(title);
      surface.appendChild(body);
      surface.appendChild(actions);
      dialog.appendChild(surface);
      document.body.appendChild(dialog);

      cancel.addEventListener('click', function () {
        CommandPalette._closeConfirmation(dialog);
      });
      confirm.addEventListener('click', function () {
        var pending = CommandPalette._pendingConfirmationAction;
        CommandPalette._closeConfirmation(dialog);
        if (pending) CommandPalette._completeAction(pending, null);
      });
      dialog.addEventListener('overlayclose', function (event) {
        event.preventDefault();
        CommandPalette._closeConfirmation(dialog);
      });
      dialog.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          event.preventDefault();
          CommandPalette._closeConfirmation(dialog);
          return;
        }
        if (event.key !== 'Tab') return;
        var focusables = [cancel, confirm];
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });

      return dialog;
    },

    _openConfirmation: function (item, palette) {
      var dialog = CommandPalette._ensureConfirmation();
      var body = dialog.querySelector('[data-command-confirm-body]');
      var confirm = dialog.querySelector('[data-command-confirm-submit]');
      if (!body || !confirm) return;

      CommandPalette._pendingConfirmationAction = item;
      while (body.firstChild) body.removeChild(body.firstChild);
      CommandPalette._appendFeedbackRow(body, '命令', item.label);
      CommandPalette._appendFeedbackRow(body, '对象', item.object);
      CommandPalette._appendFeedbackRow(body, '影响', item.preview);
      CommandPalette._appendFeedbackRow(body, '结果', item.result);

      if (palette && !palette.hidden) CommandPalette._close(palette);
      CommandPalette.confirmationTriggerEl = document.activeElement;
      dialog.hidden = false;
      dialog.setAttribute('aria-hidden', 'false');
      OverlayStack.push(dialog);
      confirm.focus();
    },

    _closeConfirmation: function (dialog) {
      var target = dialog || document.querySelector('[data-command-confirmation]');
      if (!target) return;
      target.hidden = true;
      target.setAttribute('aria-hidden', 'true');
      OverlayStack.remove(target);
      CommandPalette._pendingConfirmationAction = null;
      if (CommandPalette.confirmationTriggerEl && CommandPalette.confirmationTriggerEl.focus) {
        CommandPalette.confirmationTriggerEl.focus();
      }
      CommandPalette.confirmationTriggerEl = null;
    },

    _open: function (palette, trigger) {
      CommandPalette._render(palette);
      palette.hidden = false;
      palette.setAttribute('aria-hidden', 'false');
      document.body.setAttribute('data-command-palette-open', 'true');
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
      CommandPalette.triggerEl = document.activeElement;
      CommandPalette.activeIndex = -1;

      /* Register with OverlayStack for z-index and Esc stacking */
      OverlayStack.push(palette);

      /* Focus the search input */
      var searchInput = palette.querySelector('[data-command-search]');
      if (searchInput) {
        searchInput.focus();
      } else {
        var firstItem = palette.querySelector('[data-command-suggestion]');
        if (firstItem && firstItem.focus) firstItem.focus();
      }
    },

    _close: function (palette) {
      palette.hidden = true;
      palette.setAttribute('aria-hidden', 'true');
      document.body.removeAttribute('data-command-palette-open');
      document.querySelectorAll('[data-shell-utility="command"], .header-command-trigger').forEach(function (trigger) {
        trigger.setAttribute('aria-expanded', 'false');
      });
      /* Clear active highlight */
      palette.querySelectorAll('.command-item-active').forEach(function (item) {
        item.classList.remove('command-item-active');
      });

      /* Unregister from OverlayStack */
      OverlayStack.remove(palette);
      CommandPalette.activeIndex = -1;
      if (CommandPalette.triggerEl) {
        CommandPalette.triggerEl.focus();
        CommandPalette.triggerEl = null;
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 15. BottomTray
   *     Shared collapsed → peek → expanded state contract
   * ══════════════════════════════════════════════ */
  var BottomTray = {
    states: ['collapsed', 'peek', 'expanded'],
    symbols: {
      collapsed: '⌄',
      peek: '▴',
      expanded: '—',
    },

    init: function () {
      document.querySelectorAll('[data-bottom-tray]').forEach(function (tray) {
        var toggle = tray.querySelector('[data-bottom-tray-toggle]');
        if (!toggle) return;

        var content = BottomTray._resolveContent(tray, toggle);
        if (!content) return;

        BottomTray._sync(tray, toggle, content, BottomTray._state(tray));
        if (tray.getAttribute('data-bottom-tray-ready') === 'true') return;

        tray.setAttribute('data-bottom-tray-ready', 'true');
        toggle.addEventListener('click', function () {
          BottomTray._sync(tray, toggle, content, BottomTray._nextState(BottomTray._state(tray)));
        });
      });
    },

    _resolveContent: function (tray, toggle) {
      var controls = toggle.getAttribute('aria-controls');
      if (controls) {
        var target = document.getElementById(controls);
        if (target) return target;
      }

      return tray.querySelector('[data-bottom-tray-content], .bottom-tray-content');
    },

    _state: function (tray) {
      var state = tray.getAttribute('data-bottom-tray-state');
      return BottomTray.states.indexOf(state) >= 0 ? state : 'collapsed';
    },

    _nextState: function (state) {
      if (state === 'collapsed') return 'peek';
      if (state === 'peek') return 'expanded';
      return 'collapsed';
    },

    _labelBase: function (tray, toggle, content) {
      var explicit = tray.getAttribute('data-bottom-tray-label') || toggle.getAttribute('data-bottom-tray-label');
      if (explicit) return explicit;

      var currentLabel = (toggle.getAttribute('aria-label') || '').replace(/^(预览|展开|收起)\s*/, '').trim();
      return currentLabel || tray.getAttribute('aria-label') || content.getAttribute('aria-label') || '底部面板';
    },

    _labelForState: function (state, baseLabel) {
      if (state === 'collapsed') return '预览' + baseLabel;
      if (state === 'peek') return '展开' + baseLabel;
      return '收起' + baseLabel;
    },

    _sync: function (tray, toggle, content, state) {
      var isCollapsed = state === 'collapsed';

      tray.setAttribute('data-bottom-tray-state', state);
      toggle.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
      toggle.setAttribute('aria-label', BottomTray._labelForState(state, BottomTray._labelBase(tray, toggle, content)));
      toggle.textContent = BottomTray.symbols[state];
      content.setAttribute('aria-hidden', isCollapsed ? 'true' : 'false');
    },
  };

  /* ══════════════════════════════════════════════
   * 16a. OverlayStack
   *     Manages z-index stacking and Esc dismissal for overlays.
   *     Tracks open order so Esc only closes the topmost layer.
   *
   *     Registration: elements with [data-overlay] are auto-discovered.
   *     Triggers: [data-overlay-trigger="overlay-id"] or checkbox :has() CSS.
   *     Close buttons: [data-close], .close-btn, .overlay-close within overlay.
   *     Backdrop dismiss: .overlay-dismiss within overlay.
   * ══════════════════════════════════════════════ */
  var OverlayStack = {
    /* Stack of open overlay DOM elements, bottom-first */
    _stack: [],

    /* Base z-index for the first overlay layer */
    _baseZ: 1100,

    /* Step between successive overlay layers */
    _step: 10,

    /* CSS variable name set on each overlay element */
    _varName: '--overlay-z-index',

    init: function () {
      OverlayStack._bindTriggers();
      OverlayStack._bindEsc();
      OverlayStack._observeCheckboxes();
    },

    /* ── Public API ── */

    /**
     * Push an overlay element onto the stack.
     * Sets data-overlay-active, assigns z-index, adds to stack.
     * @param {HTMLElement} el  The overlay container ([data-overlay])
     */
    push: function (el) {
      if (!el || OverlayStack._stack.indexOf(el) !== -1) return;
      el.setAttribute('data-overlay-active', '');
      var z = OverlayStack._baseZ + OverlayStack._stack.length * OverlayStack._step;
      el.style.setProperty(OverlayStack._varName, z);
      el.classList.add('overlay-active');
      OverlayStack._stack.push(el);
    },

    /**
     * Remove an overlay from the stack (any position).
     * Re-indexes z-index values for remaining items.
     * @param {HTMLElement} el
     */
    remove: function (el) {
      var idx = OverlayStack._stack.indexOf(el);
      if (idx === -1) return;
      OverlayStack._stack.splice(idx, 1);
      el.removeAttribute('data-overlay-active');
      el.classList.remove('overlay-active');
      el.style.removeProperty(OverlayStack._varName);
      OverlayStack._reindex();
    },

    /**
     * Close the topmost overlay on the stack.
     * Dispatches a 'overlayclose' CustomEvent on the element.
     * If not prevented, falls back to close button click or checkbox uncheck.
     */
    closeTop: function () {
      if (!OverlayStack._stack.length) return false;
      var top = OverlayStack._stack[OverlayStack._stack.length - 1];

      /* Allow custom close handlers via event */
      var evt = new CustomEvent('overlayclose', { cancelable: true, bubbles: false });
      if (!top.dispatchEvent(evt)) return true; /* handler called preventDefault */

      /* Try clicking a close button first */
      var closeBtn = top.querySelector('[data-close], .close-btn, .overlay-close, .drawer-close');
      if (closeBtn) {
        closeBtn.click();
      } else {
        /* Fallback: uncheck the associated checkbox toggle */
        OverlayStack._uncheckToggle(top);
        OverlayStack.remove(top);
      }
      return true;
    },

    /**
     * Return the current stack depth.
     */
    depth: function () {
      return OverlayStack._stack.length;
    },

    /* ── Internal ── */

    /** Bind click on [data-overlay-trigger] buttons, close buttons, and backdrop dismiss */
    _bindTriggers: function () {
      document.addEventListener('click', function (e) {
        /* 1. Open trigger */
        var trigger = e.target.closest('[data-overlay-trigger]');
        if (trigger) {
          var targetId = trigger.getAttribute('data-overlay-trigger');
          var overlay = document.querySelector('[data-overlay="' + targetId + '"]');
          if (!overlay) return;
          /* Check the associated hidden checkbox (CSS :has() activation) */
          var checkbox = document.getElementById(targetId);
          if (checkbox && checkbox.type === 'checkbox') {
            checkbox.checked = true;
          }
          OverlayStack.push(overlay);
          return;
        }

        /* 2. Close button inside an overlay */
        var closeBtn = e.target.closest('[data-overlay] [data-close], [data-overlay] .close-btn, [data-overlay] .overlay-close, [data-overlay] .drawer-close');
        if (closeBtn) {
          e.preventDefault();
          var overlayEl = closeBtn.closest('[data-overlay]');
          if (overlayEl) {
            OverlayStack._uncheckToggle(overlayEl);
            OverlayStack.remove(overlayEl);
          }
          return;
        }

        /* 3. Backdrop dismiss (click on overlay-dismiss area) */
        var dismiss = e.target.closest('[data-overlay] .overlay-dismiss');
        if (dismiss) {
          e.preventDefault();
          var backdropOverlay = dismiss.closest('[data-overlay]');
          if (backdropOverlay) {
            OverlayStack._uncheckToggle(backdropOverlay);
            OverlayStack.remove(backdropOverlay);
          }
          return;
        }
      });
    },

    /** Global Esc handler — closes topmost overlay only */
    _bindEsc: function () {
      document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        if (!OverlayStack._stack.length) return;
        e.preventDefault();
        e.stopPropagation();
        OverlayStack.closeTop();
      }, true);
    },

    /** Watch hidden checkbox toggles that activate overlays via :has() */
    _observeCheckboxes: function () {
      /* MutationObserver on checkbox state changes */
      var checkboxes = document.querySelectorAll('input[type="checkbox"][id^="overlay-"]');
      if (!checkboxes.length) return;

      checkboxes.forEach(function (cb) {
        cb.addEventListener('change', function () {
          var overlayId = cb.id;
          var overlay = document.querySelector('[data-overlay="' + overlayId + '"]');
          if (!overlay) return;
          if (cb.checked) {
            OverlayStack.push(overlay);
          } else {
            OverlayStack.remove(overlay);
          }
        });
      });

      /* Also catch overlays that are already visible on page load */
      requestAnimationFrame(function () {
        checkboxes.forEach(function (cb) {
          if (cb.checked) {
            var overlay = document.querySelector('[data-overlay="' + cb.id + '"]');
            if (overlay) OverlayStack.push(overlay);
          }
        });
      });
    },

    /** Uncheck the hidden checkbox associated with an overlay */
    _uncheckToggle: function (overlay) {
      var overlayId = overlay.getAttribute('data-overlay');
      if (!overlayId) return;
      var checkbox = document.getElementById(overlayId);
      if (checkbox && checkbox.type === 'checkbox') {
        checkbox.checked = false;
      }
    },

    /** Re-assign z-index values after stack mutation */
    _reindex: function () {
      for (var i = 0; i < OverlayStack._stack.length; i++) {
        var el = OverlayStack._stack[i];
        var z = OverlayStack._baseZ + i * OverlayStack._step;
        el.style.setProperty(OverlayStack._varName, z);
      }
    },
  };

  /* ══════════════════════════════════════════════
   * 16b. KeyboardShortcuts
   *     Global keyboard shortcuts: / search, ? help
   *     Escape is handled by OverlayStack._bindEsc()
   * ══════════════════════════════════════════════ */
  var KeyboardShortcuts = {
    init: function () {
      document.addEventListener('keydown', function (e) {
        /* Ignore when typing in inputs */
        if (e.target && typeof e.target.matches === 'function' && e.target.matches('input, textarea, select, [contenteditable]')) return;

        switch (e.key) {
          case '/':
            e.preventDefault();
            var searchInput = document.querySelector('.header-search input, [data-command-trigger]');
            if (searchInput) searchInput.focus();
            break;
          case '?':
            /* Future: shortcut help panel */
            break;
        }
      });
    },
  };

  /* ══════════════════════════════════════════════
   * 16b. CollapseToggle
   *     [data-collapse-toggle] buttons toggle [data-collapsed] on target
   * ══════════════════════════════════════════════ */
  var CollapseToggle = {
    init: function () {
      /* Decorate existing toggle buttons with ARIA attributes */
      document.querySelectorAll('[data-collapse-toggle]').forEach(function (toggle) {
        var targetId = toggle.getAttribute('data-collapse-toggle');
        var target = document.getElementById(targetId);
        if (!target) return;

        var isCollapsed = target.getAttribute('data-collapsed') === 'true';
        toggle.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
        toggle.setAttribute('aria-controls', targetId);
        if (!target.hasAttribute('role')) {
          target.setAttribute('role', 'region');
        }
        if (!target.hasAttribute('aria-label') && !target.hasAttribute('aria-labelledby')) {
          var toggleLabel = toggle.getAttribute('aria-label') || toggle.textContent.trim();
          target.setAttribute('aria-label', toggleLabel + ' 区域');
        }
      });

      document.addEventListener('click', function (e) {
        var toggle = e.target.closest('[data-collapse-toggle]');
        if (!toggle) return;
        var targetId = toggle.getAttribute('data-collapse-toggle');
        var target = document.getElementById(targetId);
        if (!target) return;
        var isCollapsed = target.getAttribute('data-collapsed') === 'true';
        target.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
        toggle.setAttribute('aria-expanded', isCollapsed ? 'true' : 'false');
      });
    },
  };

  /* ══════════════════════════════════════════════
   * 16. ResizablePanels
   *     Prototype-only panel resize contract
   * ══════════════════════════════════════════════ */
  var ResizablePanels = {
    defaultStep: 40,
    fineStep: 8,

    init: function () {
      document.querySelectorAll('[data-resizable-panel-group]').forEach(function (group) {
        group.querySelectorAll('[data-resize-separator]').forEach(function (separator) {
          ResizablePanels._sync(group, separator, ResizablePanels._initialValue(group, separator));
          if (!separator.getAttribute('title')) {
            separator.setAttribute('title', '拖拽调整面板，双击恢复默认宽度');
          }

          if (separator.getAttribute('data-resizable-panel-ready') === 'true') return;
          separator.setAttribute('data-resizable-panel-ready', 'true');

          separator.addEventListener('keydown', function (event) {
            ResizablePanels._onKeydown(event, group, separator);
          });
          separator.addEventListener('pointerdown', function (event) {
            ResizablePanels._onPointerDown(event, group, separator);
          });
          separator.addEventListener('dblclick', function () {
            ResizablePanels._setValue(group, separator, ResizablePanels._defaultValue(group, separator));
          });
        });
      });
    },

    _onKeydown: function (event, group, separator) {
      var isHorizontal = separator.getAttribute('aria-orientation') === 'horizontal';
      var positiveKey = isHorizontal ? 'ArrowDown' : 'ArrowRight';
      var negativeKey = isHorizontal ? 'ArrowUp' : 'ArrowLeft';
      if (event.key !== positiveKey && event.key !== negativeKey) return;

      event.preventDefault();
      var step = event.shiftKey ? ResizablePanels.fineStep : ResizablePanels.defaultStep;
      var separatorDirection = event.key === positiveKey ? 1 : -1;
      var edge = separator.getAttribute('data-resize-edge') || 'end';
      var direction = edge === 'start' ? separatorDirection : -separatorDirection;
      ResizablePanels._setValue(group, separator, ResizablePanels._currentValue(group, separator) + (direction * step));
    },

    _onPointerDown: function (event, group, separator) {
      if (event.button && event.button !== 0) return;

      event.preventDefault();
      var startX = event.clientX || 0;
      var startY = event.clientY || 0;
      var startValue = ResizablePanels._currentValue(group, separator);
      var edge = separator.getAttribute('data-resize-edge') || 'end';
      var isHorizontal = separator.getAttribute('aria-orientation') === 'horizontal';

      separator.setAttribute('data-resizing', 'true');
      group.setAttribute('data-resizing', 'true');
      document.documentElement.setAttribute('data-resizing-panel', 'true');
      if (separator.setPointerCapture && event.pointerId !== undefined) {
        separator.setPointerCapture(event.pointerId);
      }

      var onMove = function (moveEvent) {
        var delta = isHorizontal ? (moveEvent.clientY || 0) - startY : (moveEvent.clientX || 0) - startX;
        var nextValue = edge === 'start' ? startValue + delta : startValue - delta;
        ResizablePanels._setValue(group, separator, nextValue);
      };

      var onEnd = function () {
        separator.removeAttribute('data-resizing');
        group.removeAttribute('data-resizing');
        document.documentElement.removeAttribute('data-resizing-panel');
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onEnd);
        window.removeEventListener('pointercancel', onEnd);
      };

      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onEnd);
      window.addEventListener('pointercancel', onEnd);
    },

    _setValue: function (group, separator, value) {
      var nextValue = ResizablePanels._sync(group, separator, value);
      ResizablePanels._persist(group, separator, nextValue);
    },

    _sync: function (group, separator, value) {
      var nextValue = ResizablePanels._clamp(value, ResizablePanels._minValue(separator), ResizablePanels._maxValue(separator));
      group.style.setProperty(ResizablePanels._cssVar(group, separator), Math.round(nextValue) + 'px');
      separator.setAttribute('aria-valuenow', String(Math.round(nextValue)));
      separator.setAttribute('aria-valuetext', ResizablePanels._valueText(separator, nextValue));
      return nextValue;
    },

    _valueText: function (separator, value) {
      var label = separator.getAttribute('data-resize-value-label') || separator.getAttribute('aria-label') || '面板宽度';
      return label + ' ' + Math.round(value) + ' 像素';
    },

    _initialValue: function (group, separator) {
      var storedValue = ResizablePanels._storedValue(group, separator);
      return storedValue === null ? ResizablePanels._currentValue(group, separator) : storedValue;
    },

    _currentValue: function (group, separator) {
      return ResizablePanels._number(
        separator.getAttribute('aria-valuenow'),
        ResizablePanels._number(
          group.style.getPropertyValue(ResizablePanels._cssVar(group, separator)),
          ResizablePanels._defaultValue(group, separator),
        ),
      );
    },

    _defaultValue: function (group, separator) {
      return ResizablePanels._clamp(
        ResizablePanels._number(
          separator.getAttribute('data-resize-default'),
          ResizablePanels._number(separator.getAttribute('aria-valuenow'), ResizablePanels._minValue(separator)),
        ),
        ResizablePanels._minValue(separator),
        ResizablePanels._maxValue(separator),
      );
    },

    _minValue: function (separator) {
      return ResizablePanels._number(separator.getAttribute('data-resize-min'), ResizablePanels._number(separator.getAttribute('aria-valuemin'), 160));
    },

    _maxValue: function (separator) {
      return ResizablePanels._number(separator.getAttribute('data-resize-max'), ResizablePanels._number(separator.getAttribute('aria-valuemax'), 640));
    },

    _cssVar: function (group, separator) {
      return separator.getAttribute('data-resize-var') || group.getAttribute('data-resize-var') || '--prototype-detail-width';
    },

    _storageKey: function (group, separator) {
      var varName = ResizablePanels._cssVar(group, separator);
      return 'ditto:prototype:layout:' + window.location.pathname + ':' + varName;
    },

    _storedValue: function (group, separator) {
      try {
        var value = window.localStorage.getItem(ResizablePanels._storageKey(group, separator));
        if (value === null) return null;

        var parsed = ResizablePanels._number(value, null);
        if (parsed === null) return null;

        var min = ResizablePanels._minValue(separator);
        var max = ResizablePanels._maxValue(separator);
        return parsed >= min && parsed <= max ? parsed : null;
      } catch (_) {
        return null;
      }
    },

    _persist: function (group, separator, value) {
      try {
        window.localStorage.setItem(ResizablePanels._storageKey(group, separator), String(Math.round(value)));
      } catch (_) {
        // Prototype storage can be unavailable under opaque origins or locked-down previews.
      }
    },

    _number: function (value, fallback) {
      if (typeof value !== 'string' && typeof value !== 'number') return fallback;
      var parsed = Number.parseFloat(String(value).trim());
      return Number.isFinite(parsed) ? parsed : fallback;
    },

    _clamp: function (value, min, max) {
      return Math.min(Math.max(value, min), max);
    },
  };

  /* ══════════════════════════════════════════════
   * 17. BulletGraph — data-bullet-value="72" data-bullet-target="85" data-bullet-max="100"
   *     Compact horizontal bullet chart with target marker
   * ══════════════════════════════════════════════ */
  var BulletGraph = {
    render: function (el) {
      var value = parseFloat(el.getAttribute('data-bullet-value')) || 0;
      var target = parseFloat(el.getAttribute('data-bullet-target')) || 0;
      var max = parseFloat(el.getAttribute('data-bullet-max')) || 100;
      var label = el.getAttribute('data-bullet-label') || '';

      var pct = Math.min(value / max * 100, 100);
      var targetPct = Math.min(target / max * 100, 100);

      while (el.firstChild) el.removeChild(el.firstChild);

      var track = document.createElement('div');
      track.className = 'bullet-track';

      var targetMarker = document.createElement('div');
      targetMarker.className = 'bullet-target';
      targetMarker.style.position = 'absolute';
      targetMarker.style.left = targetPct + '%';
      targetMarker.style.top = '-2px';
      targetMarker.style.width = '2px';
      targetMarker.style.height = '10px';
      targetMarker.style.background = 'var(--text-primary)';
      targetMarker.style.opacity = '0.6';

      var fill = document.createElement('div');
      fill.className = 'bullet-fill';
      fill.style.height = '100%';
      fill.style.width = pct + '%';
      fill.style.background = 'var(--brand-accent)';
      fill.style.borderRadius = '3px';

      track.appendChild(targetMarker);
      track.appendChild(fill);
      el.appendChild(track);

      if (label) {
        var span = document.createElement('span');
        span.className = 'bullet-label';
        span.textContent = label;
        el.appendChild(span);
      }
    },

    init: function () {
      document.querySelectorAll('[data-bullet-value]').forEach(BulletGraph.render);
    },
  };

  /* ── Dynamic module base styles loaded via shared/prototype-interactions.css ── */

  /* ── Auto-initialize ── */
  function init() {
    watchCssVarCacheInvalidation();
    Tabs.init();
    RadioTabLabels.init();
    InteractiveRoleActions.init();
    PrimaryAnswerDrilldowns.init();
    FilterChips.init();
    Sparkline.init();
    DonutGauge.init();
    HeatGrid.init();
    DataCounter.init();
    ScrollReveal.init();
    ConfidenceBar.init();
    FlowBar.init();
    TooltipSystem.init();
    CollapsibleContextSections.init();
    SidebarToggle.init();
    OverlayStack.init();
    KeyboardShortcuts.init();
    CollapseToggle.init();
    CommandPalette.init();
    BottomTray.init();
    ResizablePanels.init();
    BulletGraph.init();
    StripCollapse.init();
  }

  /* ══════════════════════════════════════════════
   * 18. StripCollapse
   *     [data-collapsible-strip] strips with toggle header
   *     Supports both standalone strip wrappers and rail-section elements.
   *     Collapsed state: only header row visible (36px).
   *     Expanded state: full content with smooth animation.
   * ══════════════════════════════════════════════ */
  var StripCollapse = {
    init: function () {
      /* 1. Standalone collapsible-strip wrappers */
      document.querySelectorAll('[data-collapsible-strip].collapsible-strip').forEach(function (strip) {
        var toggle = strip.querySelector('[data-strip-toggle]');
        var content = strip.querySelector('.collapsible-content');
        if (!toggle || !content) return;

        var startCollapsed = strip.getAttribute('data-default-collapsed') === 'true';
        StripCollapse._sync(strip, toggle, content, startCollapsed);

        if (strip.getAttribute('data-strip-collapse-ready') === 'true') return;
        strip.setAttribute('data-strip-collapse-ready', 'true');

        toggle.addEventListener('click', function (e) {
          e.stopPropagation();
          var isCollapsed = strip.getAttribute('data-collapsed-state') === 'true';
          StripCollapse._sync(strip, toggle, content, !isCollapsed);
        });

        /* Also allow clicking the title to toggle */
        var title = strip.querySelector('.collapsible-strip-title');
        if (title) {
          title.addEventListener('click', function () {
            var isCollapsed = strip.getAttribute('data-collapsed-state') === 'true';
            StripCollapse._sync(strip, toggle, content, !isCollapsed);
          });
          title.style.cursor = 'pointer';
        }
      });

      /* 2. Rail-section collapsible elements */
      document.querySelectorAll('.rail-section[data-collapsible-strip]').forEach(function (section) {
        var header = section.querySelector('.rail-section-header');
        var body = section.querySelector('.rail-section-body');
        if (!header || !body) return;

        var startCollapsed = section.getAttribute('data-default-collapsed') === 'true';
        StripCollapse._syncRailSection(section, header, body, startCollapsed);

        if (section.getAttribute('data-strip-collapse-ready') === 'true') return;
        section.setAttribute('data-strip-collapse-ready', 'true');

        header.addEventListener('click', function () {
          var isCollapsed = section.getAttribute('data-collapsed-state') === 'true';
          StripCollapse._syncRailSection(section, header, body, !isCollapsed);
        });

        /* Keyboard support */
        header.setAttribute('tabindex', '0');
        header.setAttribute('role', 'button');
        header.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            var isCollapsed = section.getAttribute('data-collapsed-state') === 'true';
            StripCollapse._syncRailSection(section, header, body, !isCollapsed);
          }
        });
      });
    },

    _sync: function (strip, toggle, content, collapsed) {
      strip.setAttribute('data-collapsed-state', collapsed ? 'true' : 'false');
      content.setAttribute('data-collapsed', collapsed ? 'true' : 'false');
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      var label = toggle.getAttribute('data-strip-toggle') || '';
      toggle.setAttribute('aria-label', (collapsed ? '展开' : '折叠') + (label ? ' ' + label : ''));
    },

    _syncRailSection: function (section, header, body, collapsed) {
      section.setAttribute('data-collapsed-state', collapsed ? 'true' : 'false');
      body.setAttribute('data-collapsed', collapsed ? 'true' : 'false');
      header.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      var titleText = header.querySelector('.rail-section-title');
      var title = titleText ? titleText.textContent.trim() : '';
      header.setAttribute('aria-label', (collapsed ? '展开' : '折叠') + (title ? ' ' + title : ''));
    },
  };

  /* ══════════════════════════════════════════════
   * 19. Atmosphere — data-atmosphere-intensity
   *     API for manual/future perceptible chromatic mode.
   *     Not part of the init chain.
   * ══════════════════════════════════════════════ */
  var Atmosphere = {
    setIntensity: function (level) {
      if (level === 'default') {
        document.documentElement.removeAttribute('data-atmosphere-intensity');
      } else {
        document.documentElement.setAttribute('data-atmosphere-intensity', level);
      }
    },
  };

  /* Expose Atmosphere API on window for external use */
  if (typeof window !== 'undefined') {
    window.DittoAtmosphere = Atmosphere;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
