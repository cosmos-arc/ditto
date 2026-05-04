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
   * 1e. ScreenerWorkflow
   *     Root: [data-screener-workflow]
   *     Adds visible draft/apply/sort/compare state for screener prototypes
   * ══════════════════════════════════════════════ */
  var ScreenerWorkflow = {
    init: function () {
      document.querySelectorAll('[data-screener-workflow]').forEach(function (root) {
        var state = {
          universe: ScreenerWorkflow._activeChipText(root, '股票池') || '沪深300',
          hasValuationCondition: false,
          compareTickers: ScreenerWorkflow._readInitialCompareTickers(root),
        };

        ScreenerWorkflow._syncFilterDraft(root, state);
        ScreenerWorkflow._setupFilter(root, state);
        ScreenerWorkflow._setupSort(root);
        ScreenerWorkflow._setupCompare(root, state);
      });
    },

    _setupFilter: function (root, state) {
      root.addEventListener('ditto:filter-chip-change', function (event) {
        var group = event.target.closest('.filter-group');
        if (!group || !root.contains(group)) return;
        var label = ScreenerWorkflow._groupLabel(group);
        if (label === '股票池') {
          state.universe = event.detail.value;
        }
        ScreenerWorkflow._syncFilterDraft(root, state);
      });

      root.addEventListener('click', function (event) {
        var action = event.target.closest('[data-filter-action]');
        if (!action || !root.contains(action)) return;
        var type = action.getAttribute('data-filter-action');

        if (type === 'add-condition') {
          state.hasValuationCondition = true;
          ScreenerWorkflow._syncFilterDraft(root, state);
          return;
        }

        if (type === 'apply') {
          ScreenerWorkflow._applyFilter(root, state);
        }
      });
    },

    _setupSort: function (root) {
      root.addEventListener('click', function (event) {
        var option = event.target.closest('[data-sort-option]');
        if (option && root.contains(option)) {
          ScreenerWorkflow._selectSortOption(root, option);
          return;
        }

        var action = event.target.closest('[data-sort-action]');
        if (!action || !root.contains(action)) return;
        if (action.getAttribute('data-sort-action') === 'apply') {
          ScreenerWorkflow._applySort(root);
        } else {
          var first = root.querySelector('[data-sort-option="change"]');
          if (first) ScreenerWorkflow._selectSortOption(root, first);
          ScreenerWorkflow._applySort(root);
        }
      });
    },

    _setupCompare: function (root, state) {
      ScreenerWorkflow._decorateCompareTable(root, state);

      root.addEventListener('click', function (event) {
        var button = event.target.closest('[data-compare-add]');
        if (!button || !root.contains(button)) return;

        var row = button.closest('tr.row');
        if (!row) return;
        var ticker = button.getAttribute('data-compare-add');
        if (!ticker || state.compareTickers[ticker]) return;

        state.compareTickers[ticker] = true;
        var nameCell = row.children[1];
        var changeCell = row.querySelector('.cell-change-up, .cell-change-down');
        var name = nameCell ? nameCell.textContent.trim() : ticker;
        var change = changeCell ? changeCell.textContent.trim() : '';

        ScreenerWorkflow._appendCompareItem(root, ticker, name, change);
        ScreenerWorkflow._syncCompareCount(root, state);
        button.setAttribute('aria-pressed', 'true');
        button.textContent = '已加入';
      });

      ScreenerWorkflow._syncCompareCount(root, state);
    },

    _syncFilterDraft: function (root, state) {
      var active = root.querySelector('[data-active-conditions]');
      if (active) {
        active.innerHTML = '';
        active.appendChild(ScreenerWorkflow._conditionChip('universe', '股票池 = ' + state.universe));
        if (state.hasValuationCondition) {
          active.appendChild(ScreenerWorkflow._conditionChip('valuation', 'PE < 20'));
        }
      }

      var count = state.hasValuationCondition ? 2 : 1;
      ScreenerWorkflow._setText(root, '[data-filter-status]', '草稿 ' + count + ' 条');
      ScreenerWorkflow._setText(root, '[data-filter-draft]', '股票池 = ' + state.universe + ' · PE < 20');
    },

    _applyFilter: function (root, state) {
      var count = state.hasValuationCondition ? 126 : 188;
      var conditionCount = state.hasValuationCondition ? 2 : 1;
      var conditionLabel = state.hasValuationCondition ? '股票池/估值' : '股票池';

      ScreenerWorkflow._setText(root, '.filter-count', '共 ' + count + ' 只');
      ScreenerWorkflow._setText(root, '[data-filter-applied-at]', '已应用');
      ScreenerWorkflow._setText(root, '[data-filter-preview-count]', count + ' 只');
      ScreenerWorkflow._setText(root, '[data-screener-scope] .screener-insight-value', state.universe + ' · A股 · ' + count + ' 只');
      ScreenerWorkflow._setText(root, '[data-screener-filters] .screener-insight-value', conditionCount + ' 条激活 · ' + conditionLabel);
      ScreenerWorkflow._setText(root, '.table-footer-info span', '显示 1-22 / 共 ' + count + ' 只 · 第 1/6 页');
    },

    _selectSortOption: function (root, option) {
      var options = Array.from(root.querySelectorAll('[data-sort-option]'));
      var rank = 2;

      options.forEach(function (item) {
        var rankEl = item.querySelector('.sort-item-rank');
        item.classList.remove('sort-item--active');
        item.setAttribute('aria-pressed', 'false');
        if (rankEl) rankEl.textContent = String(rank++);
      });

      option.classList.add('sort-item--active');
      option.setAttribute('aria-pressed', 'true');
      var firstRank = option.querySelector('.sort-item-rank');
      if (firstRank) firstRank.textContent = '1';
    },

    _applySort: function (root) {
      var active = root.querySelector('[data-sort-option].sort-item--active');
      if (!active) return;

      root.querySelectorAll('.data-table th.sorted').forEach(function (th) {
        th.classList.remove('sorted');
        var icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = '';
      });

      var target = active.getAttribute('data-sort-target');
      var th = target ? root.querySelector('.data-table th' + target) : null;
      if (th) {
        th.classList.add('sorted');
        var icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = '▼';
      }

      var label = active.getAttribute('data-sort-label') || '涨跌幅';
      ScreenerWorkflow._setText(root, '[data-screener-rank] .screener-insight-value', '排序: ' + label + ' → 涨跌幅 → 信号强度');
    },

    _decorateCompareTable: function (root, state) {
      var table = root.querySelector('.data-table[data-compare-source]');
      if (!table || table.querySelector('th.col-compare-action')) return;

      var headerRow = table.querySelector('thead tr');
      if (headerRow) {
        var th = document.createElement('th');
        th.scope = 'col';
        th.className = 'col-compare-action';
        th.textContent = '操作';
        headerRow.appendChild(th);
      }

      table.querySelectorAll('tbody tr.row').forEach(function (row) {
        var tickerEl = row.querySelector('.cell-ticker');
        if (!tickerEl) return;
        var ticker = tickerEl.textContent.trim();
        var nameCell = row.children[1];
        var name = nameCell ? nameCell.textContent.trim() : ticker;
        var selected = Boolean(state.compareTickers[ticker]);

        var td = document.createElement('td');
        td.className = 'col-compare-action';

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'compare-add-btn';
        button.setAttribute('data-compare-add', ticker);
        button.setAttribute('aria-pressed', selected ? 'true' : 'false');
        button.setAttribute('aria-label', (selected ? '已加入对比 ' : '加入对比 ') + name);
        button.textContent = selected ? '已加入' : '+ 对比';

        td.appendChild(button);
        row.appendChild(td);
      });
    },

    _appendCompareItem: function (root, ticker, name, change) {
      var detailBody = root.querySelector('[data-compare-basket-body]');
      if (!detailBody) {
        var compareCta = root.querySelector('.catalog-detail .compare-cta');
        detailBody = compareCta ? compareCta.closest('.context-section-body') : null;
      }
      if (!detailBody) {
        detailBody = root.querySelector('.catalog-detail details[open] .context-section-body');
      }
      if (detailBody) {
        var detailItem = document.createElement('div');
        var detailInfo = document.createElement('div');
        var detailInfoInner = document.createElement('div');
        var detailTextGroup = document.createElement('div');
        var detailName = ScreenerWorkflow._textElement('div', 'compare-item-name', name);
        var detailCode = ScreenerWorkflow._textElement('div', 'compare-item-code', ticker);
        var detailActions = document.createElement('div');
        var detailRemove = ScreenerWorkflow._textElement('span', 'compare-item-remove', '×');

        detailItem.className = 'compare-item';
        detailInfo.className = 'compare-item-info';
        detailActions.className = 'compare-item-actions';
        detailRemove.setAttribute('role', 'button');
        detailRemove.setAttribute('tabindex', '0');
        detailRemove.setAttribute('aria-label', '移除' + name);
        detailRemove.addEventListener('click', function () {
          var item = detailRemove.closest('.compare-item');
          if (item) item.remove();
        });
        detailRemove.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            var item = detailRemove.closest('.compare-item');
            if (item) item.remove();
          }
        });

        detailTextGroup.appendChild(detailName);
        detailTextGroup.appendChild(detailCode);
        detailInfoInner.appendChild(detailTextGroup);
        detailInfo.appendChild(detailInfoInner);
        detailActions.appendChild(detailRemove);
        detailItem.appendChild(detailInfo);
        detailItem.appendChild(detailActions);
        var cta = detailBody.querySelector('.compare-cta');
        detailBody.insertBefore(detailItem, cta || null);
      }

      var compareList = root.querySelector('.compare-list');
      if (compareList) {
        var row = document.createElement('div');
        row.className = 'compare-row';
        row.appendChild(ScreenerWorkflow._textElement('span', 'compare-row-ticker', ticker));
        row.appendChild(ScreenerWorkflow._textElement('span', 'compare-row-name', name));
        row.appendChild(ScreenerWorkflow._textElement('span', 'text-up', change));
        compareList.appendChild(row);
      }
    },

    _textElement: function (tagName, className, text) {
      var element = document.createElement(tagName);
      element.className = className;
      element.textContent = text;
      return element;
    },

    _syncCompareCount: function (root, state) {
      var count = Object.keys(state.compareTickers).length;
      root.querySelectorAll('[data-compare-count]').forEach(function (el) {
        el.textContent = String(count);
      });
    },

    _readInitialCompareTickers: function (root) {
      var tickers = {};
      root.querySelectorAll('.compare-item-code, .compare-row-ticker').forEach(function (el) {
        var ticker = el.textContent.trim();
        if (ticker) tickers[ticker] = true;
      });
      return tickers;
    },

    _activeChipText: function (root, label) {
      var groups = Array.from(root.querySelectorAll('.filter-group'));
      for (var i = 0; i < groups.length; i++) {
        if (ScreenerWorkflow._groupLabel(groups[i]) !== label) continue;
        var active = groups[i].querySelector('.filter-chip.active');
        if (active) return active.textContent.trim().replace('▾', '').trim();
      }
      return '';
    },

    _groupLabel: function (group) {
      var label = group.querySelector('.filter-label');
      return label ? label.textContent.replace(':', '').trim() : '';
    },

    _conditionChip: function (name, text) {
      var chip = document.createElement('span');
      chip.className = 'condition-chip';
      chip.setAttribute('data-condition-chip', name);
      chip.textContent = text;
      return chip;
    },

    _setText: function (root, selector, text) {
      var el = root.querySelector(selector);
      if (el) el.textContent = text;
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
          var formattedValue = prefix + target.toFixed(decimals) + suffix;
          el.textContent = formattedValue;
          NumberTicker._announce(formattedValue);
          return;
        }

        var observer = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              NumberTicker.animate(el, target, decimals, prefix, suffix);
              observer.unobserve(el);
              observer.disconnect();
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
        else NumberTicker._announce(prefix + target.toFixed(decimals) + suffix);
      }
      requestAnimationFrame(tick);
    },

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
   * 7. MouseGlow — data-mouse-glow="true"
   * ══════════════════════════════════════════════ */
  var MouseGlow = {
    currentEl: null,
    frame: 0,
    lastEvent: null,

    init: function () {
      if (reducedMotion) return;

      /* Apply initial glow tokens to all glow elements */
      document.querySelectorAll('[data-mouse-glow]').forEach(function (el) {
        MouseGlow._applyTokens(el);
      });

      /* Event delegation: single mousemove on document */
      document.addEventListener('mousemove', function (e) {
        var el = e.target.closest('[data-mouse-glow]');
        if (!el) {
          if (MouseGlow.currentEl) MouseGlow._clear(MouseGlow.currentEl);
          MouseGlow.currentEl = null;
          return;
        }
        if (el !== MouseGlow.currentEl) {
          if (MouseGlow.currentEl) MouseGlow._clear(MouseGlow.currentEl);
          MouseGlow.currentEl = el;
        }
        MouseGlow._update(el, e);
      });

      /* Clear glow when mouse leaves a glow element (delegated via mouseout) */
      document.addEventListener('mouseout', function (e) {
        if (!MouseGlow.currentEl) return;
        var el = e.target.closest('[data-mouse-glow]');
        if (!el || el !== MouseGlow.currentEl) return;
        var related = e.relatedTarget;
        if (related && el.contains(related)) return;
        MouseGlow._clear(el);
        MouseGlow.currentEl = null;
      });

      /* Clear glow when mouse leaves the document entirely */
      document.addEventListener('mouseleave', function () {
        if (MouseGlow.currentEl) {
          MouseGlow._clear(MouseGlow.currentEl);
          MouseGlow.currentEl = null;
        }
      });

      /* Also listen for mouseleave on each glow element directly (non-bubbling) */
      document.querySelectorAll('[data-mouse-glow]').forEach(function (el) {
        el.addEventListener('mouseleave', function () {
          MouseGlow._clear(el);
          if (MouseGlow.currentEl === el) {
            MouseGlow.currentEl = null;
          }
        });
      });
    },

    _applyTokens: function (el) {
      var color = el.getAttribute('data-mouse-glow-color') || cssVar('--brand-accent-subtle', 'oklch(from var(--brand-500) l c h / 0.06)');
      var size = el.getAttribute('data-mouse-glow-size') || '200px';
      el.style.setProperty('--_glow-size', size);
      el.style.setProperty('--_glow-color', color);
    },

    _update: function (el, event) {
      MouseGlow.lastEvent = event;
      var background =
        'radial-gradient(circle var(--_glow-size) at var(--_glow-x, 50%) var(--_glow-y, 50%), var(--_glow-color), transparent)';

      if (!el.style.backgroundImage || !el.style.getPropertyValue('--_glow-size') || !el.style.getPropertyValue('--_glow-color')) {
        MouseGlow._applyTokens(el);
        el.style.backgroundImage = background;
      }
      if (MouseGlow.frame) return;

      MouseGlow.frame = requestAnimationFrame(function () {
        MouseGlow.frame = 0;
        if (!MouseGlow.lastEvent) return;

        var rect = el.getBoundingClientRect();
        var x = MouseGlow.lastEvent.clientX - rect.left;
        var y = MouseGlow.lastEvent.clientY - rect.top;
        el.style.setProperty('--_glow-x', x + 'px');
        el.style.setProperty('--_glow-y', y + 'px');
      });
    },

    _clear: function (el) {
      if (MouseGlow.frame) {
        cancelAnimationFrame(MouseGlow.frame);
      }
      MouseGlow.frame = 0;
      MouseGlow.lastEvent = null;
      el.style.backgroundImage = '';
      el.style.removeProperty('--_glow-x');
      el.style.removeProperty('--_glow-y');
      el.style.removeProperty('--_glow-size');
      el.style.removeProperty('--_glow-color');
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

    /* ══════════════════════════════════════════════
   * 10. AnimatedCounter — data-counter="1234.56"
   *     Smoothly transitions between numeric values
   *     MutationObserver watches data-counter for changes
   * ══════════════════════════════════════════════ */
  var AnimatedCounter = {
    init: function () {
      var els = document.querySelectorAll('[data-counter]');
      if (!els.length) return;

      els.forEach(function (el) {
        var target = parseFloat(el.getAttribute('data-counter'));
        if (isNaN(target)) return;
        AnimatedCounter._setup(el, target);
      });

      /* Observe data-counter attribute changes for live updates */
      if (typeof MutationObserver === 'undefined') return;
      var mo = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          var el = m.target;
          if (m.type === 'attributes' && m.attributeName === 'data-counter') {
            var newTarget = parseFloat(el.getAttribute('data-counter'));
            if (isNaN(newTarget)) return;
            var state = el._dittoCounter;
            if (state) {
              state.from = state.current;
              AnimatedCounter._animate(el, state, newTarget);
            }
          }
        });
      });

      els.forEach(function (el) {
        mo.observe(el, { attributes: true, attributeFilter: ['data-counter'] });
      });
    },

    _setup: function (el, target) {
      var decimals = parseInt(el.getAttribute('data-counter-decimals') || '2', 10);
      var prefix   = el.getAttribute('data-counter-prefix') || '';
      var suffix   = el.getAttribute('data-counter-suffix') || '';
      var duration = parseInt(el.getAttribute('data-counter-duration') || '800', 10);

      var state = {
        from: 0,
        current: 0,
        decimals: decimals,
        prefix: prefix,
        suffix: suffix,
        duration: duration,
        raf: null,
      };

      el._dittoCounter = state;

      if (reducedMotion) {
        state.current = target;
        var formattedValue = prefix + AnimatedCounter.format(target, decimals) + suffix;
        el.textContent = formattedValue;
        AnimatedCounter._announce(formattedValue);
        return;
      }

      AnimatedCounter._animate(el, state, target);
    },

    _animate: function (el, state, target) {
      if (state.raf) cancelAnimationFrame(state.raf);
      var startTime = performance.now();

      function tick(now) {
        var p = Math.min((now - startTime) / state.duration, 1);
        /* ease-out cubic */
        var eased = 1 - Math.pow(1 - p, 3);
        var val = state.from + (target - state.from) * eased;
        state.current = val;
        el.textContent = state.prefix + AnimatedCounter.format(val, state.decimals) + state.suffix;
        if (p < 1) {
          state.raf = requestAnimationFrame(tick);
        } else {
          state.current = target;
          state.raf = null;
          AnimatedCounter._announce(state.prefix + AnimatedCounter.format(target, state.decimals) + state.suffix);
        }
      }
      state.raf = requestAnimationFrame(tick);
    },

    /* Thousand-separator formatting */
    format: function (num, decimals) {
      var parts = num.toFixed(decimals).split('.');
      parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      return parts.join('.');
    },

    _announce: function (text) {
      var liveRegion = document.querySelector('[role="status"].live-region');
      if (liveRegion) {
        liveRegion.textContent = text;
      }
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
   * ══════════════════════════════════════════════ */
  var CommandPalette = {
    triggerEl: null,
    labels: {
      'add-to-compare': '加入对比',
      approve: '批准',
      'clone-strategy': '复制策略',
      'copy-params': '复制参数',
      'create-incident': '创建事件',
      'explain-priority': '解释优先级',
      'generate-report': '生成报告',
      'generate-signal': '生成信号',
      'mute-alert': '静音告警',
      'open-instrument-hub': '打开标的 Hub',
      'open-orders': '打开订单',
      'open-risk': '打开风控',
      'pause-strategy': '暂停策略',
      reject: '拒绝',
      'remove-watch': '移出观察',
      retry: '重试',
      'review-signal': '复核信号',
      'run-backtest': '运行回测',
      'send-to-order': '发送到订单',
      'send-to-research': '发送到研究',
      'view-curve': '查看曲线',
      'view-evidence': '查看证据',
      'view-logs': '查看日志',
      'view-recent-runs': '查看近期运行',
    },

    init: function () {
      var triggers = Array.from(document.querySelectorAll('[data-shell-utility="command"], .header-command-trigger'));
      if (!triggers.length) return;

      var palette = CommandPalette._ensurePalette();
      CommandPalette._render(palette);

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
        } else if (key === 'escape' && !palette.hidden) {
          CommandPalette._close(palette);
        }
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
      palette.setAttribute('aria-label', '上下文命令');
      palette.setAttribute('aria-hidden', 'true');
      palette.hidden = true;

      var title = document.createElement('div');
      title.className = 'ditto-command-title';
      title.textContent = '上下文命令';

      var context = document.createElement('div');
      context.className = 'ditto-command-context';
      context.setAttribute('data-command-context-label', '');

      var list = document.createElement('div');
      list.className = 'ditto-command-list';
      list.setAttribute('data-command-suggestion-list', '');

      palette.appendChild(title);
      palette.appendChild(context);
      palette.appendChild(list);
      document.body.appendChild(palette);

      /* Focus trap: Tab/Shift+Tab wraps within dialog */
      palette.addEventListener('keydown', function (e) {
        if (e.key !== 'Tab') return;
        var items = palette.querySelectorAll('[data-command-item], input, [data-command-suggestion]');
        if (!items.length) return;
        var first = items[0];
        var last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
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
        actions: actions,
      };
    },

    _render: function (palette) {
      var context = CommandPalette._readContext();
      var contextLabel = palette.querySelector('[data-command-context-label]');
      var list = palette.querySelector('[data-command-suggestion-list]');
      if (!list || !contextLabel) return;

      contextLabel.textContent = '对象: ' + context.object;
      while (list.firstChild) {
        list.removeChild(list.firstChild);
      }

      if (!context.actions.length) {
        var empty = document.createElement('div');
        empty.className = 'ditto-command-empty';
        empty.textContent = '当前页面暂无对象上下文动作';
        list.appendChild(empty);
        return;
      }

      context.actions.forEach(function (action) {
        var item = document.createElement('button');
        item.type = 'button';
        item.className = 'ditto-command-item';
        item.setAttribute('data-command-suggestion', '');
        item.setAttribute('data-command-action', action);
        item.setAttribute('data-command-context-object', context.object);
        item.textContent = (CommandPalette.labels[action] || action) + ' · ' + action;
        list.appendChild(item);
      });
    },

    _open: function (palette, trigger) {
      CommandPalette._render(palette);
      palette.hidden = false;
      palette.setAttribute('aria-hidden', 'false');
      document.body.setAttribute('data-command-palette-open', 'true');
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
      CommandPalette.triggerEl = document.activeElement;

      var firstItem = palette.querySelector('[data-command-suggestion]');
      if (firstItem && firstItem.focus) {
        firstItem.focus();
      }
    },

    _close: function (palette) {
      palette.hidden = true;
      palette.setAttribute('aria-hidden', 'true');
      document.body.removeAttribute('data-command-palette-open');
      document.querySelectorAll('[data-shell-utility="command"], .header-command-trigger').forEach(function (trigger) {
        trigger.setAttribute('aria-expanded', 'false');
      });
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
   * 16a. KeyboardShortcuts
   *     Global keyboard shortcuts: / search, Escape close overlay
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
          case 'Escape':
            /* Close topmost overlay */
            var topOverlay = document.querySelector('[data-overlay].overlay-active, [aria-modal="true"]:not([aria-hidden="true"])');
            if (topOverlay) {
              var closeBtn = topOverlay.querySelector('[data-close], .close-btn');
              if (closeBtn) closeBtn.click();
            }
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
      document.addEventListener('click', function (e) {
        var toggle = e.target.closest('[data-collapse-toggle]');
        if (!toggle) return;
        var target = document.getElementById(toggle.getAttribute('data-collapse-toggle'));
        if (!target) return;
        var isCollapsed = target.getAttribute('data-collapsed') === 'true';
        target.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
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

  /* ── Inject shared CSS for dynamic modules ── */
  var style = document.createElement('style');
  style.textContent = [
    '/* Ditto Interactions — dynamic module base styles */',
    '.confidence-track { flex:1; height:4px; border-radius:2px; overflow:hidden; background:var(--overlay-6); }',
    '.confidence-fill  { height:100%; border-radius:2px; transition:width 1s cubic-bezier(0.4,0,0.2,1); }',
    '[data-confidence] { display:flex; align-items:center; gap:8px; }',
    '.confidence-label { font-size:11px; color:var(--text-tertiary); white-space:nowrap; }',
    '.flow-bar { display:flex; height:6px; border-radius:3px; overflow:hidden; gap:1px; }',
    '.flow-segment { border-radius:1px; transition:flex 0.8s cubic-bezier(0.4,0,0.2,1); }',
    '[data-tab-target] { cursor:pointer; }',
    '[data-tab-target].active { color:var(--brand-accent); }',
    '[data-tab-panel][aria-hidden="true"] { display:none; }',
    '.filter-chip[aria-pressed="true"] { border-color:var(--brand-accent); }',
    '/* Tooltip */',
    '.ditto-tooltip { position:fixed; z-index:9999; padding:6px 10px; border-radius:6px;',
    '  background:var(--surface-overlay, oklch(0.260 0.008 253));',
    '  color:var(--text-primary, oklch(0.925 0.004 253));',
    '  font-size:12px; line-height:1.4; max-width:240px; pointer-events:none;',
    '  border:1px solid var(--border-default, oklch(0.325 0.008 253));',
    '  box-shadow:0 4px 12px oklch(0 0 0 / 0.3); /* no shadow token — oklch fallback is intentional */',
    '  opacity:0; transition:opacity 150ms cubic-bezier(0.4,0,0.2,1); display:none; }',
    '.ditto-tooltip--visible { opacity:1; }',
  ].join('\n');
  document.head.appendChild(style);

  /* ── Auto-initialize ── */
  function init() {
    watchCssVarCacheInvalidation();
    Tabs.init();
    RadioTabLabels.init();
    InteractiveRoleActions.init();
    PrimaryAnswerDrilldowns.init();
    FilterChips.init();
    ScreenerWorkflow.init();
    Sparkline.init();
    DonutGauge.init();
    HeatGrid.init();
    NumberTicker.init();
    ScrollReveal.init();
    MouseGlow.init();
    ConfidenceBar.init();
    FlowBar.init();
    AnimatedCounter.init();
    TooltipSystem.init();
    CollapsibleContextSections.init();
    SidebarToggle.init();
    KeyboardShortcuts.init();
    CollapseToggle.init();
    CommandPalette.init();
    BottomTray.init();
    ResizablePanels.init();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
