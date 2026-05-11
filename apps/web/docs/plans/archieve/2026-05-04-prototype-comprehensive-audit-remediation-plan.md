# Prototype Comprehensive Audit Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 2026-05-04 全面审计发现的全部 33 个问题（P0:4 / P1:8 / P2:12 / P3:9），将 Ditto 原型的技术质量从 13.0/20 提升至 17+/20，对标 Linear / Bloomberg Terminal / VS Code 的可访问性和交互标准。

**Architecture:** 按依赖关系分 5 个阶段执行。Phase 1 修共享 JS 交互层的键盘导航核心缺陷（解锁后续所有 ARIA 修复）；Phase 2 修全局 CSS 层的运动偏好和主题；Phase 3 修语义和视觉一致性；Phase 4 修性能和代码质量；Phase 5 做体验增强。每个 Phase 结束运行 `bun run check` 验证。

**Tech Stack:** HTML prototypes, shared prototype CSS/JS, Design Tokens, JSDOM, Vitest, Playwright, Bun, Biome.

---

## Audit Triage

### P0 — Blocking（4 个）

| # | Audit item | 处理 |
|---|---|---|
| P0-1 | Tab 系统缺少箭头键导航 | 在 `Tabs.init()` keydown handler 中添加 ArrowRight/ArrowLeft/Home/End，实现 roving tabindex |
| P0-2 | CommandPalette 无 focus trap + 关闭不恢复焦点 | 添加 focus trap 循环 + 关闭时 `triggerEl.focus()` |
| P0-3 | Tooltip 缺少 `aria-describedby` 关联 | 创建 tooltip 时在触发元素上设置 `aria-describedby="tooltip-{id}"` |
| P0-4 | 零响应式设计 | 添加 `min-width: 1024px` 保护 + overflow-x 水平滚动（最小可行性） |

### P1 — Major（8 个）

| # | Audit item | 处理 |
|---|---|---|
| P1-1 | 4/5 页面缺少 `prefers-reduced-motion` | 在 `layout-base.css` 添加全局 reduced-motion 规则 |
| P1-2 | 4/5 页面无 light mode 适配 | 为 28 个页面添加 `[data-theme="light"]` 环境光和噪点适配 |
| P1-3 | 动态内容缺少 `aria-live` | 在 shell 布局中添加 `role="status"` live region，NumberTicker/AnimatedCounter 写入 |
| P1-4 | Tab 容器缺 `role="tablist"`，面板缺 `role="tabpanel"` | `Tabs.init()` 程序化补全 ARIA 角色 |
| P1-5 | FilterChips 无键盘交互 | 添加 keydown Enter/Space/Arrow 处理 |
| P1-6 | 42 处硬编码 hex 在 `prototype-toggles.css` | 逐一替换为 `var(--token-name)` |
| P1-7 | Trading Overview 缺 skip link | 添加与其他页面一致的 skip link |
| P1-8 | 数据表格行缺 hover + sticky header | 在 `layout-base.css` 添加标准表格交互样式 |

### P2 — Minor（12 个）

| # | Audit item | 处理 |
|---|---|---|
| P2-1 | 65 处 `!important` 在 `layout-base.css` | 使用更具体选择器或 CSS Layers 替代 |
| P2-2 | MouseGlow per-element 监听器 | 改为祖先元素事件委托 |
| P2-3 | IntersectionObserver 永不断开 | 所有元素 unobserve 后 `disconnect()` |
| P2-4 | Sparkline `Math.min.apply` 栈溢出风险 | 改用 `reduce` |
| P2-5 | theme-switcher.js localStorage 无 try-catch | 包装在 try-catch 中 |
| P2-6 | 触摸设备 Tooltip/MouseGlow 不工作 | Tooltip 长按触发；MouseGlow graceful degradation |
| P2-7 | RadioTabLabels querySelector 注入风险 | 使用 `CSS.escape(input.id)` |
| P2-8 | Compare 移除按钮无事件处理 | 绑定 click + keydown 处理器 |
| P2-9 | 缺少全局键盘快捷键系统 | 添加分区焦点 + 上下文快捷键基础框架 |
| P2-10 | 涨跌指示器缺色盲冗余编码 | 所有涨跌添加 ▲/▼ 三角 + +/- 前缀 |
| P2-11 | Sparkline 嵌入覆盖率低 | 扩展到 Home 决策卡片、Signals Inbox |
| P2-12 | Calendar 视觉密度不一致 | 统一 panel padding/gap |

### P3 — Polish（9 个）

| # | Audit item | 处理 |
|---|---|---|
| P3-1 | Tab 入场动画仅 Instrument Hub 有 | 全局化 tab-fade-in + stagger |
| P3-2 | Rail active 指示器缺过渡动画 | 添加 background-color transition |
| P3-3 | 面板折叠/展开缺高度过渡 | 添加 max-height transition（reduced-motion 下跳过） |
| P3-4 | `_dittoCounter` DOM expando 属性 | 改用 WeakMap |
| P3-5 | `FlowBar.render` 用 `el.className +=` | 改用 `classList.add` |
| P3-6 | 数值更新缺覆盖面动画 | 扩展 AnimatedCounter 覆盖范围 |
| P3-7 | Console 日志无语法高亮 | 添加基础 Python/SQL 语法着色 |
| P3-8 | 风险指标未用 Bullet Graph | 添加水平 bullet graph 组件 |
| P3-9 | Chromatic Atmosphere 仅亚感知 | 极端行情时增强至可感知级别 |

---

## Scope

**Modify:**

- `docs/designs/specs/prototypes/shared/prototype-interactions.js` — Phase 1, 3, 4, 5
- `docs/designs/specs/prototypes/shared/layout-base.css` — Phase 2, 3
- `docs/designs/specs/prototypes/shared/prototype-toggles.css` — Phase 2
- `docs/designs/specs/prototypes/shared/theme-switcher.js` — Phase 4
- `docs/designs/specs/prototypes/page-trading-overview.html` — Phase 3
- `docs/designs/specs/prototypes/page-home.html` — Phase 3, 5
- `docs/designs/specs/prototypes/page-signals-inbox.html` — Phase 3, 5
- `docs/designs/specs/prototypes/page-agent-console-v2.html` — Phase 5
- `docs/designs/specs/prototypes/page-markets-calendar.html` — Phase 3
- `docs/designs/specs/prototypes/tokens-style.css` — Phase 5

**Read:**

- `docs/designs/specs/prototypes/shared/mock-data.js`
- `docs/designs/specs/prototypes/tokens-style.css`
- `docs/designs/specs/prototypes/.edition-manifest.json`
- `src/styles/design-tokens/tokens-*.css`（验证 token 名称）

**Out of scope:**

- React `src/` 实现
- 新依赖
- CI/CD 修改
- 未批准的 Design Token 新增
- 响应式完整重构（仅做 min-width 保护）

---

## Definition Of Done

- `bun run check` passes
- 所有 P0 修复后，Tab 可用箭头键导航、CommandPalette 有 focus trap、Tooltip 有 aria-describedby
- 全局 `prefers-reduced-motion: reduce` 下零动画
- `prototype-toggles.css` 零硬编码 hex
- Audit Health Score 从 13.0/20 提升至 17+/20

---

## Phase 1: Keyboard Navigation & Focus Management（P0 核心）

### Task 1: Tab 系统 arrow-key 导航 + roving tabindex

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: 扩展 Tabs keydown handler**

在 `Tabs.init()` 的 `keydown` handler（约 line 123-129）中，替换当前仅处理 Enter/Space 的逻辑，添加完整的箭头键导航：

```js
// 当前代码（仅 Enter/Space）
group.addEventListener('keydown', function (e) {
  var btn = e.target.closest('[data-tab-target]');
  if (!btn || !group.contains(btn)) return;
  if (e.key !== 'Enter' && e.key !== ' ') return;
  e.preventDefault();
  activate(btn, true);
});

// 替换为（完整箭头键导航）
group.addEventListener('keydown', function (e) {
  var btn = e.target.closest('[data-tab-target]');
  if (!btn || !group.contains(btn)) return;

  var buttons = Array.from(group.querySelectorAll('[data-tab-target]'));
  var idx = buttons.indexOf(btn);

  switch (e.key) {
    case 'ArrowRight':
    case 'ArrowDown':
      e.preventDefault();
      var next = buttons[(idx + 1) % buttons.length];
      next.focus();
      activate(next, true);
      break;
    case 'ArrowLeft':
    case 'ArrowUp':
      e.preventDefault();
      var prev = buttons[(idx - 1 + buttons.length) % buttons.length];
      prev.focus();
      activate(prev, true);
      break;
    case 'Home':
      e.preventDefault();
      buttons[0].focus();
      activate(buttons[0], true);
      break;
    case 'End':
      e.preventDefault();
      buttons[buttons.length - 1].focus();
      activate(buttons[buttons.length - 1], true);
      break;
    case 'Enter':
    case ' ':
      e.preventDefault();
      activate(btn, true);
      break;
  }
});
```

Run: `bun test scripts/prototype-interaction-ux-contract.test.ts`

Expected: Tab 组内可用 ArrowRight/ArrowLeft 循环导航，Home/End 跳首尾

---

### Task 2: CommandPalette focus trap + 焦点恢复

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: 存储 trigger 引用 + focus trap**

在 `CommandPalette` 模块中（约 line 1460-1531）：

1. 在 `_open` 中保存触发元素引用：`CommandPalette.triggerEl = document.activeElement;`
2. 添加 focus trap keydown handler：Tab/Shift+Tab 循环在 dialog 内
3. 在 `_close` 中恢复焦点：`if (CommandPalette.triggerEl) CommandPalette.triggerEl.focus();`

```js
// _open 末尾添加
CommandPalette.triggerEl = document.activeElement;

// _close 修改
_close: function () {
  CommandPalette.el.style.display = 'none';
  CommandPalette.el.setAttribute('aria-hidden', 'true');
  CommandPalette.isOpen = false;
  if (CommandPalette.triggerEl) {
    CommandPalette.triggerEl.focus();
    CommandPalette.triggerEl = null;
  }
}

// focus trap（在 _open 中绑定一次）
CommandPalette.el.addEventListener('keydown', function (e) {
  if (e.key !== 'Tab') return;
  var items = CommandPalette.el.querySelectorAll('[data-command-item], input');
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
```

Expected: Cmd+K 打开后 Tab 不会逃出 dialog，Esc 关闭后焦点回到触发按钮

---

### Task 3: Tooltip aria-describedby 关联

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: 在 show 方法中设置 aria-describedby**

在 `TooltipSystem.show()` 方法（约 line 1190-1220）中，创建 tooltip 元素时添加唯一 ID，并在触发元素上设置 `aria-describedby`：

```js
// 在 show 方法中，设置 tooltip 内容后
var tooltipId = 'ditto-tooltip-' + Date.now();
TooltipSystem.el.id = tooltipId;
trigger.setAttribute('aria-describedby', tooltipId);

// 在 hide 方法中，清除关联
var describedby = trigger.getAttribute('aria-describedby');
if (describedby && describedby.startsWith('ditto-tooltip-')) {
  trigger.removeAttribute('aria-describedby');
}
```

Expected: 屏幕阅读器可通过 `aria-describedby` 读取 tooltip 内容

---

### Task 4: ARIA 角色程序化补全

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: Tabs.init() 中补全 ARIA 角色**

在 `Tabs.init()` 的 `activate` 函数前添加：

```js
// 确保 tablist 角色存在
if (!group.hasAttribute('role')) {
  group.setAttribute('role', 'tablist');
}

// 确保按钮有 role="tab" 和 aria-controls
buttons.forEach(function (btn) {
  if (!btn.hasAttribute('role')) {
    btn.setAttribute('role', 'tab');
  }
  var target = btn.getAttribute('data-tab-target');
  if (target && !btn.hasAttribute('aria-controls')) {
    btn.setAttribute('aria-controls', target);
  }
});

// 确保面板有 role="tabpanel"
panels.forEach(function (panel) {
  if (!panel.hasAttribute('role')) {
    panel.setAttribute('role', 'tabpanel');
  }
  var target = panel.getAttribute('data-tab-panel');
  if (target && !panel.hasAttribute('aria-labelledby')) {
    var controllingBtn = buttons.find(function (b) {
      return b.getAttribute('data-tab-target') === target;
    });
    if (controllingBtn && controllingBtn.id) {
      panel.setAttribute('aria-labelledby', controllingBtn.id);
    }
  }
});
```

**Step 2: FilterChips 添加键盘交互**

在 `FilterChips.init()`（约 line 212-238）中，在 click listener 后添加 keydown：

```js
group.addEventListener('keydown', function (e) {
  var chip = e.target.closest('[data-filter]');
  if (!chip || !group.contains(chip)) return;
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    FilterChips._toggle(chip, group, true);
  }
});
```

**Step 3: Compare 移除按钮添加事件处理**

在 `ScreenerWorkflow._setupCompare`（约 line 535-542）中，为 `detailRemove` 绑定 click handler：

```js
detailRemove.addEventListener('click', function () {
  var item = detailRemove.closest('.compare-detail-item');
  if (item) item.remove();
});
detailRemove.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    var item = detailRemove.closest('.compare-detail-item');
    if (item) item.remove();
  }
});
```

Expected: 所有 Tab 组有完整 ARIA 三件套（tablist/tab/tabpanel），FilterChips 可键盘操作，Compare 移除按钮可用

---

### Task 5: 最小响应式保护

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: 添加 min-width 保护**

在 `layout-base.css` 的 `.shell` 规则后添加：

```css
/* ── Minimum viewport protection ── */
.shell,
.shell-v2,
.shell-analytical,
.shell-catalog,
.shell-studio,
.shell-hub {
  min-width: 1024px;
}

body {
  overflow-x: auto;
}
```

Run: 在 1024px 宽度下打开任何原型页面，应显示水平滚动而非布局塌陷

Expected: 1024px 以上布局完好，以下有水平滚动保护

---

## Phase 2: Motion & Theme（P0 reduced-motion + P1 主题）

### Task 6: 全局 prefers-reduced-motion

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: 在 layout-base.css 末尾添加全局规则**

```css
/* ── Global Reduced Motion ── */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  .dot-pulse,
  .dot-critical-pulse,
  .price-breathe,
  .tab-fade-in,
  [data-reveal] {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
```

Expected: 系统开启 reduced-motion 后，所有页面零动画

---

### Task 7: prototype-toggles.css 硬编码 hex 替换

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-toggles.css`

**Step 1: 逐一替换 42 处硬编码 hex**

对每一处硬编码色值，查找对应的 token 名称并替换：

```css
/* Before */
background: #1a1b23;
/* After */
background: var(--surface-app);

/* Before */
color: #e4e4e7;
/* After */
color: var(--text-primary);

/* Before */
border-color: #3f3f46;
/* After */
border-color: var(--border-default);
```

需要逐行审查 `prototype-toggles.css` 全部 hex 值，映射到正确的 semantic token。

Run: `grep -c '#[0-9a-fA-F]\{3,8\}' docs/designs/specs/prototypes/shared/prototype-toggles.css`

Expected: 输出 0（零硬编码 hex）

---

### Task 8: Light mode 页面级适配

**Files:**

- Modify: 28 个 `page-*.html`（除 trading-overview 已有）

**Step 1: 创建共享 light-mode 片段**

在 `tokens-style.css` 中添加共享的 light mode 环境光适配：

```css
/* ── Light Mode Atmosphere ── */
[data-theme="light"] .ambient-top,
[data-theme="light"] .ambient-rail {
  opacity: 0.3;
}

[data-theme="light"] .noise-layer {
  opacity: 0.005;
}

[data-theme="light"] .shell-header {
  backdrop-filter: blur(12px) saturate(1.4);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
}

[data-theme="light"] .shell-header::after {
  opacity: 0.4;
}

[data-theme="light"] .rail-logo {
  text-shadow: none;
}
```

**Step 2: 对缺少 `[data-theme="light"]` 的页面验证**

逐个在浏览器中切换到 light mode，确认视觉正确。如有页面特有问题，在该页面的 `<style>` 块中添加局部覆盖。

Expected: 所有 29 个页面在 light mode 下视觉可接受（环境光不刺眼、噪点不突兀、磨砂玻璃正确）

---

## Phase 3: ARIA Live & Semantic HTML（P1 剩余 + P2 部分）

### Task 9: aria-live 区域 + Trading Overview skip link

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`

**Step 1: 在 shell 布局中添加 live region**

在 `layout-base.css` 中：

```css
.live-region {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

**Step 2: 在 prototype-interactions.js 的 NumberTicker/AnimatedCounter 中写入 live region**

在数字更新时，额外写入一个隐藏的 `role="status"` 元素：

```js
// 在 NumberTicker 和 AnimatedCounter 更新 textContent 后
var liveRegion = document.querySelector('[role="status"].live-region');
if (liveRegion) {
  liveRegion.textContent = prefix + formattedValue + (suffix || '');
}
```

**Step 3: Trading Overview 添加 skip link**

在 `<body>` 开头添加：

```html
<a class="skip-link" href="#main">跳转到交易总览主区域</a>
```

Expected: 动态数字更新被屏幕阅读器播报（节流至合理频率）；Trading Overview 有 skip link

---

### Task 10: 涨跌色盲冗余编码

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: 添加全局涨跌三角样式**

```css
/* ── Market Direction Redundant Encoding ── */
.market-up::before {
  content: '▲';
  font-size: 0.75em;
  margin-right: var(--space-2);
}

.market-down::before {
  content: '▼';
  font-size: 0.75em;
  margin-right: var(--space-2);
}

/* 保持与现有 color class 兼容 */
.color-market-up::before {
  content: '▲';
  font-size: 0.75em;
  margin-right: var(--space-2);
}

.color-market-down::before {
  content: '▼';
  font-size: 0.75em;
  margin-right: var(--space-2);
}
```

**Step 2: 验证页面中已有的涨跌指示器**

检查 `page-home.html`、`page-trading-overview.html`、`page-instrument-hub.html` 中的涨跌数据是否使用了 `color-market-up` / `color-market-down` class。如未使用纯 class 而是直接用 token，需在该元素上添加 `data-market-dir="up/down"` 并在 CSS 中匹配。

Expected: 所有涨跌数据在色盲模拟下仍可通过 ▲/▼ 三角区分方向

---

### Task 11: 数据表格标准交互样式

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: 添加全局表格交互样式**

```css
/* ── Standard Data Table Interaction ── */
.data-table tbody tr,
.panel-body table tbody tr {
  transition: background var(--motion-duration-fast) var(--motion-easing-standard);
}

.data-table tbody tr:hover,
.panel-body table tbody tr:hover {
  background: var(--interaction-hover-subtle-bg);
}

.data-table thead th,
.panel-body table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--surface-panel-base);
}
```

Expected: 所有数据表格有 hover 行高亮 + sticky 表头

---

### Task 12: Calendar 视觉密度对齐

**Files:**

- Modify: `docs/designs/specs/prototypes/page-markets-calendar.html`

**Step 1: 统一面板间距**

检查 `page-markets-calendar.html` 中的面板 padding/gap，确保使用 `var(--density-panel-padding)` / `var(--density-section-gap)` 而非硬编码值。

Expected: Calendar 页面的面板间距与其他 Dashboard 页面一致

---

## Phase 4: Performance & Code Quality（P2 性能 + 安全）

### Task 13: MouseGlow 事件委托 + Observer 清理

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: MouseGlow 改为事件委托**

将 per-element `mousemove`/`mouseleave` 改为在 `document` 上的单次委托：

```js
init: function () {
  if (reducedMotion) return;

  document.addEventListener('mousemove', function (e) {
    var el = e.target.closest('[data-mouse-glow]');
    if (!el) {
      // 清除上一个 glow
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

  document.addEventListener('mouseleave', function () {
    if (MouseGlow.currentEl) MouseGlow._clear(MouseGlow.currentEl);
  });
},
```

**Step 2: Observer 主动断开**

在 NumberTicker 和 ScrollReveal 的 IntersectionObserver callback 中，当所有元素都已 unobserve 后：

```js
// NumberTicker callback 末尾
if (observedCount === 0) {
  observer.disconnect();
}
```

Expected: 鼠标发光效果功能不变但监听器数量从 N×2 降至 2；Observer 在完成后断开

---

### Task 14: Sparkline 安全 + localStorage try-catch + CSS.escape

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: `docs/designs/specs/prototypes/shared/theme-switcher.js`

**Step 1: Sparkline Math 安全**

替换 `Math.min.apply(null, data)` / `Math.max.apply(null, data)` 为 reduce：

```js
var min = data.reduce(function (m, v) { return v < m ? v : m; }, Infinity);
var max = data.reduce(function (m, v) { return v > m ? v : m; }, -Infinity);
```

**Step 2: theme-switcher.js localStorage try-catch**

包装所有 localStorage 调用：

```js
function safeStorageGet(key) {
  try { return localStorage.getItem(key); }
  catch (_) { return null; }
}

function safeStorageSet(key, value) {
  try { localStorage.setItem(key, value); }
  catch (_) { /* noop */ }
}
```

**Step 3: RadioTabLabels CSS.escape**

```js
// Before
document.querySelectorAll('[role="tab"][for="' + input.id + '"]')
// After
document.querySelectorAll('[role="tab"][for="' + CSS.escape(input.id) + '"]')
```

Expected: 大数据集不栈溢出；隐私模式不崩溃；特殊 ID 不注入

---

### Task 15: CSS !important 瘦身

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: 审计 65 处 !important**

逐行分析每一处 `!important` 的必要性：

- **保留**：`@media (prefers-reduced-motion: reduce)` 中的全局覆盖（Task 6 新增的也需要）
- **保留**：prototype toggle 状态覆盖（`:has()` 系统依赖 specificity 打赢）
- **替换**：能用更具体选择器解决的（如 `.shell .shell-header` → 增加 shell 前缀提高 specificity）
- **替换**：能用 CSS Layers 解决的（但原型层可能不支持，需评估）

Target: 从 65 处降至 ≤ 20 处（仅保留真正必要的 override）

Expected: `grep -c '!important' layout-base.css` ≤ 20

---

### Task 16: 触摸设备基础适配

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: Tooltip 触摸支持**

在 TooltipSystem 中添加 touch 长按支持：

```js
var touchTimer = null;
document.addEventListener('touchstart', function (e) {
  var trigger = e.target.closest('[data-tooltip]');
  if (!trigger) return;
  touchTimer = setTimeout(function () {
    TooltipSystem.show(trigger);
  }, 500); // 长按 500ms 触发
}, { passive: true });

document.addEventListener('touchend', function () {
  if (touchTimer) {
    clearTimeout(touchTimer);
    touchTimer = null;
  }
  TooltipSystem.hide();
}, { passive: true });
```

Expected: 触摸设备长按可显示 tooltip

---

## Phase 5: UX Enhancements（P2 快捷键 + P3 Polish）

### Task 17: 全局键盘快捷键基础框架

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: 添加 KeyboardShortcuts 模块**

在 prototype-interactions.js 中添加新模块：

```js
var KeyboardShortcuts = {
  init: function () {
    document.addEventListener('keydown', function (e) {
      // 忽略输入框内的按键
      if (e.target.matches('input, textarea, select, [contenteditable]')) return;

      switch (e.key) {
        case '/':
          e.preventDefault();
          // 打开搜索
          var searchInput = document.querySelector('.header-search input, [data-command-trigger]');
          if (searchInput) searchInput.focus();
          break;
        case '?':
          // 快捷键面板（future）
          break;
        case 'Escape':
          // 关闭最顶层的 overlay
          var topOverlay = document.querySelector('[data-overlay].overlay-active, [aria-modal="true"]:not([aria-hidden="true"])');
          if (topOverlay) topOverlay.click(); // 或 trigger close
          break;
      }
    });
  }
};
```

**Step 2: 在初始化链中注册**

在 IIFE 底部的初始化序列中添加 `KeyboardShortcuts.init();`

Expected: `/` 聚焦搜索框，`Esc` 关闭 overlay

---

### Task 18: 动画增强（Rail 过渡 + Tab 入场全局化）

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: Rail active 过渡动画**

```css
.rail-icon {
  transition: background var(--motion-duration-fast) var(--motion-easing-standard),
              box-shadow var(--motion-duration-normal) var(--motion-easing-standard);
}
```

**Step 2: 全局 Tab 入场动画**

```css
@keyframes ditto-tab-enter {
  from { opacity: 0; transform: translateY(2px); }
  to { opacity: 1; transform: translateY(0); }
}

.tab-bar .tab-item,
[data-tabs] [data-tab-target] {
  animation: ditto-tab-enter var(--motion-duration-fast) var(--motion-easing-standard) both;
}

.tab-bar .tab-item:nth-child(1) { animation-delay: 0ms; }
.tab-bar .tab-item:nth-child(2) { animation-delay: 30ms; }
.tab-bar .tab-item:nth-child(3) { animation-delay: 60ms; }
.tab-bar .tab-item:nth-child(4) { animation-delay: 90ms; }
.tab-bar .tab-item:nth-child(5) { animation-delay: 120ms; }
```

Expected: Rail 活跃指示器有平滑过渡；Tab 入场有微妙的 stagger 动画

---

### Task 19: 面板折叠动画

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: 添加折叠过渡 CSS**

```css
.collapsible-content {
  overflow: hidden;
  transition: max-height var(--motion-duration-normal) var(--motion-easing-standard),
              opacity var(--motion-duration-fast) var(--motion-easing-standard);
}

.collapsible-content[data-collapsed="true"] {
  max-height: 0 !important;
  opacity: 0;
}

[data-reduced-motion] .collapsible-content {
  transition: none;
}
```

Expected: 面板折叠/展开有平滑高度过渡，reduced-motion 下跳过

---

### Task 20: Sparkline 扩展覆盖

**Files:**

- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`

**Step 1: 在 Home 决策卡片中嵌入 sparkline**

为每个 decision-card 的因子信号区域添加 `data-sparkline` 属性和逗号分隔数据：

```html
<svg class="inline-sparkline" data-sparkline="12,14,11,15,13,16,18,17" width="48" height="20"></svg>
```

**Step 2: 在 Signals Inbox 信号条目中嵌入 sparkline**

类似处理。

Expected: Home 和 Signals 页面有 sparkline 趋势可视化

---

### Task 21: DOM expando 清理 + FlowBar classList

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: AnimatedCounter 用 WeakMap 替代 expando**

```js
var counterStates = new WeakMap();

// 替换 el._dittoCounter = state
counterStates.set(el, state);

// 替换 var state = el._dittoCounter
var state = counterStates.get(el);
```

**Step 2: FlowBar 用 classList.add**

```js
// Before
el.className = (el.className || '') + ' flow-bar';
// After
el.classList.add('flow-bar');
```

Expected: 零 DOM expando 属性，零 className 拼接

---

### Task 22: 数值动画扩展 + Bullet Graph 基础

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`

**Step 1: AnimatedCounter 自动检测**

在 DOM ready 时，自动为所有带 `data-counter` 的元素初始化 AnimatedCounter（当前可能需要手动触发）。

**Step 2: 添加 BulletGraph 模块**

```js
var BulletGraph = {
  render: function (el) {
    var value = parseFloat(el.getAttribute('data-bullet-value')) || 0;
    var target = parseFloat(el.getAttribute('data-bullet-target')) || 0;
    var max = parseFloat(el.getAttribute('data-bullet-max')) || 100;
    var label = el.getAttribute('data-bullet-label') || '';

    var pct = Math.min(value / max * 100, 100);
    var targetPct = Math.min(target / max * 100, 100);

    el.innerHTML =
      '<div class="bullet-track">' +
        '<div class="bullet-target" style="left:' + targetPct + '%"></div>' +
        '<div class="bullet-fill" style="width:' + pct + '%"></div>' +
      '</div>' +
      (label ? '<span class="bullet-label">' + label + '</span>' : '');
  },
  init: function () {
    document.querySelectorAll('[data-bullet-value]').forEach(BulletGraph.render);
  }
};
```

Expected: 风险指标和 conviction level 可用水平 bullet graph 展示

---

### Task 23: Console 日志语法高亮

**Files:**

- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html`

**Step 1: 添加基础 Python 语法着色 CSS**

```css
.log-line .kw { color: var(--brand-accent); }
.log-line .fn { color: var(--system-healthy-fg); }
.log-line .str { color: var(--market-up-fg); }
.log-line .num { color: var(--market-down-fg); font-family: var(--font-family-numeric); }
.log-line .cmt { color: var(--text-tertiary); font-style: italic; }
```

**Step 2: 在 mock-data.js 中为日志条目添加预着色标记**

对已有的日志字符串用 `<span class="kw">` 等标记关键字。

Expected: Agent Console 日志面板有基础语法着色

---

### Task 24: Chromatic Atmosphere 可感知模式

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: `docs/designs/specs/prototypes/tokens-style.css`

**Step 1: 添加 `data-atmosphere-intensity` 属性**

```css
[data-atmosphere-intensity="elevated"] .ambient-top {
  opacity: calc(var(--ambient-top-opacity, 0.15) * 3);
}

[data-atmosphere-intensity="elevated"] .noise-layer {
  opacity: calc(var(--surface-noise-opacity) * 2);
}
```

**Step 2: 在 prototype-interactions.js 中添加 API**

```js
var Atmosphere = {
  setIntensity: function (level) {
    // 'default' | 'elevated' | 'intense'
    document.documentElement.setAttribute('data-atmosphere-intensity', level);
  }
};
```

Expected: 可通过 JS API 切换氛围强度，为未来实时数据联动预留接口

---

## Recommended Execution Order

1. **Task 1** → Tab 箭头键（解锁后续所有 ARIA 修复的基础模式）
2. **Task 4** → ARIA 角色补全 + FilterChips + Compare（依赖 Task 1 的 keydown 架构）
3. **Task 2** → CommandPalette focus trap
4. **Task 3** → Tooltip aria-describedby
5. **Task 5** → 最小响应式保护
6. **Task 6** → 全局 prefers-reduced-motion（P0 收尾）
7. **Task 7** → prototype-toggles.css hex 替换
8. **Task 8** → Light mode 适配
9. **Task 9** → aria-live + skip link
10. **Task 10** → 色盲冗余编码
11. **Task 11** → 数据表格交互
12. **Task 12** → Calendar 密度对齐
13. **Task 13** → MouseGlow + Observer
14. **Task 14** → Sparkline 安全 + localStorage + CSS.escape
15. **Task 15** → CSS !important 瘦身
16. **Task 16** → 触摸适配
17. **Task 17** → 键盘快捷键
18. **Task 18** → 动画增强
19. **Task 19** → 面板折叠动画
20. **Task 20** → Sparkline 扩展
21. **Task 21** → DOM expando 清理
22. **Task 22** → 数值动画 + Bullet Graph
23. **Task 23** → 语法高亮
24. **Task 24** → Chromatic Atmosphere

---

## Final Verification

```bash
# 工程验证
bun run check

# 原型交互验证
bun run prototype:interaction

# 特定页面 gate
bun run prototype:gates

# 硬编码颜色审计
grep -rn '#[0-9a-fA-F]\{3,8\}' docs/designs/specs/prototypes/shared/prototype-toggles.css
# Expected: 0 matches

# !important 计数
grep -c '!important' docs/designs/specs/prototypes/shared/layout-base.css
# Expected: ≤ 20

# Tab 箭头键手动验证
# 1. 打开任意有 tab 的原型页面
# 2. Tab 到第一个 tab 按钮
# 3. 按 ArrowRight → 焦点移到下一个 tab
# 4. 按 Home → 焦点跳到第一个 tab

# CommandPalette 手动验证
# 1. 打开任意页面
# 2. 点击 Cmd+K 触发器
# 3. 按 Tab → 焦点在 dialog 内循环
# 4. 按 Esc → 焦点回到触发按钮

# Reduced motion 手动验证
# 1. 系统开启 prefers-reduced-motion
# 2. 刷新任意页面
# 3. 所有 dot-pulse、price-breathe 动画停止
```
