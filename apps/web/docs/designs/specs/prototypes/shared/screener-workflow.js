/* ─────────────────────────────────────────────
 * Ditto Prototype — ScreenerWorkflow
 * Root: [data-screener-workflow]
 * Adds visible draft/apply/sort/compare state for screener prototypes
 *
 * Page-specific module — loaded only by page-markets-screener.html
 * ───────────────────────────────────────────── */
;(function () {
  'use strict';

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

      /* Announce filter state to screen readers */
      ScreenerWorkflow._announceFilterChange(root, state);
    },

    _announceFilterChange: function (root, state) {
      var liveRegion = root.querySelector('[role="status"][data-screener-live]');
      if (!liveRegion) {
        liveRegion = document.createElement('div');
        liveRegion.setAttribute('role', 'status');
        liveRegion.setAttribute('data-screener-live', '');
        liveRegion.setAttribute('aria-live', 'polite');
        liveRegion.className = 'sr-only';
        liveRegion.style.cssText = 'position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;';
        root.appendChild(liveRegion);
      }
      var conditionCount = state.hasValuationCondition ? 2 : 1;
      var previewCount = state.hasValuationCondition ? 126 : 188;
      liveRegion.textContent = '筛选已更新: ' + conditionCount + ' 个条件, 预计显示 ' + previewCount + ' 只股票';
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

  /* ── Auto-initialize on DOMContentLoaded ── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ScreenerWorkflow.init);
  } else {
    ScreenerWorkflow.init();
  }
})();
