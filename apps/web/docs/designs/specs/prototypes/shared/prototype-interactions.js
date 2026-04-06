/* ─────────────────────────────────────────────
 * Ditto Prototype Interactions — Shared Library
 * Edition v1 Iteration v3 — Vanilla JS 交互增强
 *
 * 声明式 data-* 属性驱动，零外部依赖
 * 渐进增强：JS 未加载时 CSS 基线 ≥9.0
 * 所有动效尊重 prefers-reduced-motion
 * ───────────────────────────────────────────── */
;(function () {
  'use strict';

  /* ── Motion Preference ─────────────────────── */
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Utility: Parse JSON from data attribute ── */
  function parseAttr(el, attr) {
    try { return JSON.parse(el.getAttribute(attr)); }
    catch (_) { return null; }
  }

  /* ── Utility: Resolve CSS custom property ── */
  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return v ? v.trim() : fallback;
  }

  /* ══════════════════════════════════════════════
   * 1. Tabs
   *    Container: data-tabs="group-name"
   *    Buttons:   data-tab-target="panel-id"
   *    Panels:    data-tab-panel="panel-id"
   * ══════════════════════════════════════════════ */
  var Tabs = {
    init: function () {
      document.querySelectorAll('[data-tabs]').forEach(function (group) {
        var buttons = group.querySelectorAll('[data-tab-target]');
        var panels  = group.querySelectorAll('[data-tab-panel]');
        if (!buttons.length || !panels.length) return;

        /* default active = first button */
        var hasActive = Array.from(buttons).some(function (b) {
          return b.classList.contains('active') || b.getAttribute('aria-selected') === 'true';
        });
        if (!hasActive) {
          buttons[0].classList.add('active');
          buttons[0].setAttribute('aria-selected', 'true');
        }

        /* show/hide initial panels */
        var activeTarget = group.querySelector('[data-tab-target].active');
        if (activeTarget) {
          var tid = activeTarget.getAttribute('data-tab-target');
          panels.forEach(function (p) {
            p.style.display = p.getAttribute('data-tab-panel') === tid ? '' : 'none';
          });
        }

        /* delegated click */
        group.addEventListener('click', function (e) {
          var btn = e.target.closest('[data-tab-target]');
          if (!btn) return;
          var target = btn.getAttribute('data-tab-target');

          buttons.forEach(function (b) {
            b.classList.remove('active');
            b.setAttribute('aria-selected', 'false');
          });
          btn.classList.add('active');
          btn.setAttribute('aria-selected', 'true');

          panels.forEach(function (p) {
            var match = p.getAttribute('data-tab-panel') === target;
            p.style.display = match ? '' : 'none';
            p.setAttribute('aria-hidden', match ? 'false' : 'true');
          });

          group.dispatchEvent(new CustomEvent('ditto:tab-change', {
            detail: { target: target },
            bubbles: true,
          }));
        });
      });
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
      var stroke = cfg.stroke || cssVar('--chart-series-up', 'oklch(0.7 0.085 265)');
      var sw     = cfg.strokeWidth || parseFloat(cssVar('--sparkline-stroke-width')) || 1.5;
      var w      = cfg.width  || parseFloat(svg.getAttribute('width'))  || parseFloat(cssVar('--sparkline-width'))  || 48;
      var h      = cfg.height || parseFloat(svg.getAttribute('height')) || parseFloat(cssVar('--sparkline-height')) || 20;

      svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      svg.setAttribute('fill', 'none');
      svg.style.width  = w + 'px';
      svg.style.height = h + 'px';

      var min = Math.min.apply(null, data);
      var max = Math.max.apply(null, data);
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
      var color = cfg.color || cssVar('--brand-accent', 'oklch(0.700 0.165 255)');
      var track = cfg.trackColor || 'oklch(1 0 0 / 0.06)';
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
        txt.setAttribute('font-family', 'var(--font-family-mono)');
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

          /* tooltip */
          var tip = cfg.labels && cfg.labels[r * cols + c];
          if (tip) {
            var title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = tip;
            rect.appendChild(title);
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
   * 5. NumberTicker — data-ticker="12345.67"
   * ══════════════════════════════════════════════ */
  var NumberTicker = {
    init: function () {
      document.querySelectorAll('[data-ticker]').forEach(function (el) {
        var target = parseFloat(el.getAttribute('data-ticker'));
        if (isNaN(target)) return;
        var decimals = parseInt(el.getAttribute('data-decimals') || '2', 10);
        var prefix   = el.getAttribute('data-ticker-prefix') || '';
        var suffix   = el.getAttribute('data-ticker-suffix') || '';

        if (reducedMotion) {
          el.textContent = prefix + target.toFixed(decimals) + suffix;
          return;
        }

        var observer = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              NumberTicker.animate(el, target, decimals, prefix, suffix);
              observer.unobserve(el);
            }
          });
        }, { threshold: 0.1 });
        observer.observe(el);
      });
    },

    animate: function (el, target, decimals, prefix, suffix) {
      var duration = 1200;
      var start = performance.now();
      function tick(now) {
        var p = Math.min((now - start) / duration, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = prefix + (target * eased).toFixed(decimals) + suffix;
        if (p < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
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

      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var el = entry.target;
          var delay = parseInt(el.getAttribute('data-reveal-delay') || '0', 10);
          setTimeout(function () {
            el.style.opacity = '1';
            el.style.transform = '';
            observer.unobserve(el);
          }, delay);
        });
      }, { threshold: 0.1 });

      items.forEach(function (el) { observer.observe(el); });
    },
  };

  /* ══════════════════════════════════════════════
   * 7. MouseGlow — data-mouse-glow="true"
   * ══════════════════════════════════════════════ */
  var MouseGlow = {
    init: function () {
      if (reducedMotion) return;
      document.querySelectorAll('[data-mouse-glow]').forEach(function (el) {
        var color = el.getAttribute('data-mouse-glow-color') || 'oklch(from var(--brand-500) l c h / 0.06)';
        var size  = el.getAttribute('data-mouse-glow-size')  || '200px';

        el.addEventListener('mousemove', function (e) {
          var rect = el.getBoundingClientRect();
          var x = e.clientX - rect.left;
          var y = e.clientY - rect.top;
          el.style.setProperty('--_glow-x', x + 'px');
          el.style.setProperty('--_glow-y', y + 'px');
          el.style.backgroundImage =
            'radial-gradient(circle ' + size + ' at var(--_glow-x) var(--_glow-y), ' + color + ', transparent)';
        });

        el.addEventListener('mouseleave', function () {
          el.style.backgroundImage = '';
          el.style.removeProperty('--_glow-x');
          el.style.removeProperty('--_glow-y');
        });
      });
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
      if (v >= 0.8) return 'oklch(0.55 0.15 155)';
      if (v >= 0.6) return 'oklch(0.746 0.165 50)';
      return 'oklch(0.6317 0.1567 22.64)';
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
      'oklch(0.700 0.165 255)',
      'oklch(0.700 0.165 255 / 0.55)',
      'oklch(0.55 0.15 155)',
      'oklch(0.746 0.165 50)',
      'oklch(1 0 0 / 0.08)',
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
      el.className = (el.className || '') + ' flow-bar';

      segs.forEach(function (seg, i) {
        var pct = ((seg.value / total) * 100).toFixed(1);
        var bar = document.createElement('div');
        bar.className = 'flow-segment';
        bar.style.flex = String(seg.value);
        bar.style.background = FlowBar.palette[i % FlowBar.palette.length];
        if (seg.label) bar.title = seg.label + ': ' + seg.value + ' (' + pct + '%)';
        el.appendChild(bar);
      });
    },
  };

  /* ── Inject shared CSS for dynamic modules ── */
  var style = document.createElement('style');
  style.textContent = [
    '/* Ditto Interactions — dynamic module base styles */',
    '.confidence-track { flex:1; height:4px; border-radius:2px; overflow:hidden; background:oklch(1 0 0 / 0.06); }',
    '.confidence-fill  { height:100%; border-radius:2px; transition:width 1s cubic-bezier(0.4,0,0.2,1); }',
    '[data-confidence] { display:flex; align-items:center; gap:8px; }',
    '.confidence-label { font-size:11px; color:var(--text-tertiary); white-space:nowrap; }',
    '.flow-bar { display:flex; height:6px; border-radius:3px; overflow:hidden; gap:1px; }',
    '.flow-segment { border-radius:1px; transition:flex 0.8s cubic-bezier(0.4,0,0.2,1); }',
    '[data-tab-target] { cursor:pointer; }',
    '[data-tab-target].active { color:var(--brand-accent); }',
    '[data-tab-panel][aria-hidden="true"] { display:none; }',
  ].join('\n');
  document.head.appendChild(style);

  /* ── Auto-initialize ── */
  function init() {
    Tabs.init();
    Sparkline.init();
    DonutGauge.init();
    HeatGrid.init();
    NumberTicker.init();
    ScrollReveal.init();
    MouseGlow.init();
    ConfidenceBar.init();
    FlowBar.init();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
