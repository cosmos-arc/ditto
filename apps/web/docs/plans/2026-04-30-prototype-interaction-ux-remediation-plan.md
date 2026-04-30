# Prototype Interaction UX Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 仅在 `docs/designs/specs/prototypes/` 原型层修复 `20_interaction_ux_audit.md` 中确认有效的交互体验问题，并把 React 实现工作记录为后续 TODO。

**Architecture:** 先把跨页交互语义转成可机器检查的 prototype contract，再按共享 chrome、页面家族和代表页面分层修复。原型阶段允许修改 HTML、共享 CSS、共享 JS 和原型测试，不引入 React 依赖，不改 `src/` 运行时代码。

**Tech Stack:** HTML prototypes, shared prototype CSS/JS, JSDOM, Vitest, Playwright, Bun, Biome.

---

## Scope

本计划只处理 prototype 层：

- `docs/designs/specs/prototypes/page-*.html`
- `docs/designs/specs/prototypes/shared/layout-base.css`
- `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- `docs/designs/specs/prototypes/shared/theme-switcher.js`
- `scripts/*prototype*.test.ts`
- 必要时更新 `docs/designs/specs/20_interaction_ux_audit.md` 中的原型事实校准

本计划不处理：

- `src/` React 组件实现
- 新依赖安装，包括 `react-resizable-panels`
- Design Token 语义新增
- 路由、API、数据模型、Mock 数据结构
- 移动端响应式重构
- 原型外的产品 IA 调整

React 后续工作记录在本文末尾和 `docs/plans/prototype-to-react-enhancement-backlog.md`。

## Current Baseline

来自 2026-04-30 静态扫描和人工审查：

| 项 | 当前事实 | 风险 |
|---|---:|---|
| 活跃原型 | 27 页 | 范围明确 |
| `.rail-icon` | 150 个 | 跨页 chrome 不一致 |
| Rail 原生 `<button>` | 10 个 | 少量页面语义接近正确，但导航不应是 button |
| Rail `div role="button"` | 51 个 | 需要额外键盘行为，易漂移 |
| Rail `role="listitem"` | 70 个 | 把导航项误标为列表项 |
| Rail 无 `title` | 65 个 | icon-only 可发现性不足 |
| Rail 无 `aria-label` | 19 个 | Screen reader 不可靠 |
| `.context-section` | 50 个 | 折叠合同覆盖不足 |
| `<details class="context-section">` | 3 个 | 只有少数右栏能真正折叠 |
| Bottom Tray | 4 个 | 已有合同，可增强动画与测试 |

## Prototype Contract Decisions

### Rail

Rail 是跨页面导航，不是页面内动作。原型阶段统一为：

- 使用 `<a class="rail-icon" href="...">` 表达导航。
- 每页必须只有 5 个 `data-rail-domain`：`home`、`markets`、`research`、`trading`、`platform`。
- 中文可访问名固定为：`首页`、`市场`、`研究`、`交易`、`平台`。
- `aria-label` 与 `title` 必须一致。
- 当前域使用 `aria-current="page"`。
- SVG 图标使用 `aria-hidden="true"`，按钮/链接本身负责 accessible name。

域入口映射：

| Domain | Prototype href |
|---|---|
| `home` | `page-home.html` |
| `markets` | `page-cross-market.html` |
| `research` | `page-research.html` |
| `trading` | `page-trading-overview.html` |
| `platform` | `page-platform.html` |

### Icons

原型阶段不引入 icon library。继续使用 inline SVG，但添加 `data-icon` 作为机器合同。

| 语义 | `data-icon` | 原型图形 |
|---|---|---|
| Home | `home` | 房子 |
| Markets | `trending-up` | 趋势线 |
| Research | `book-open` 或 `microscope` | 书本或显微镜 |
| Trading | `arrow-left-right` | 双向交易箭头 |
| Platform | `settings-2` 或 `cpu` | 设置滑杆或芯片 |
| Copilot | `sparkles` 或 `bot` | 闪光或机器人 |
| Density | `density-levels` | 三层间距条，不用汉堡 |
| Submit backtest | `rocket` 或 `timer` | 火箭或计时器 |
| Dry Run | `test-tube` | 试管，避免裸播放 |
| Validate | `shield-check` | 盾牌校验 |

### Collapsible Sections

右侧上下文区使用三层语义：

| Level | Attribute | 默认 | 用途 |
|---|---|---|---|
| L1 | `data-collapse-priority="l1"` | 常驻 | sticky summary、主对象身份、核心动作 |
| L2 | `data-collapse-priority="l2"` | 展开 | 当前任务必需上下文 |
| L3 | `data-collapse-priority="l3"` | 折叠 | 低频补充、历史、关联研究、普通队列 |

原型实现规则：

- L2/L3 使用 `<details class="context-section">`。
- L2 默认带 `open`，L3 默认不带 `open`。
- `summary.context-section-header` 必须包含标题、`.collapse-count`，L3 还必须包含 `.collapse-summary`。
- 折叠态保留 count 和关键摘要，不只显示标题。
- 动画尊重 `prefers-reduced-motion`。

### Resizable Panels

原型阶段不安装 `react-resizable-panels`。先用共享 HTML/CSS/JS 表达交互合同：

- 添加 `data-resizable-panel-group`。
- 添加 `data-resize-separator`，语义为 `role="separator"`。
- separator 必须有 `tabindex="0"`、`aria-controls`、`aria-valuemin`、`aria-valuemax`、`aria-valuenow`。
- 视觉线可以是 1px，但 hit area 至少 24px。
- 鼠标拖拽、方向键、双击重置只在 prototype JS 中实现。
- 优先覆盖 Catalog 和 Studio 原型；Analytical/Ops/Radar 只记录后续批次，避免一次改动过宽。

---

### Task 1: Interaction Contract Tests

**Files:**

- Create: `scripts/prototype-interaction-ux-contract.test.ts`
- Modify: `package.json`
- Read: `docs/designs/specs/prototypes/.edition-manifest.json`
- Read: `docs/designs/specs/20_interaction_ux_audit.md`

**Step 1: Write failing Rail contract tests**

Create JSDOM tests that load every active route prototype and assert:

- exactly 5 `.shell-rail [data-rail-domain]` items.
- every item is an `<a>` element.
- allowed domains are exactly `home`, `markets`, `research`, `trading`, `platform`.
- `aria-label` and `title` match the fixed Chinese label for the domain.
- each page has exactly one `aria-current="page"` rail item.
- no rail item has label `AI`、`运维`、`Platform`、`Home`、`Markets`、`Research`、`Trading`.
- every rail SVG has `aria-hidden="true"`.

Run:

```bash
bun test scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL on current mixed Rail implementations.

**Step 2: Write failing icon collision tests**

In the same test file, assert:

- `#density-toggle` has `data-icon="density-levels"` and its SVG path set is not the three-line hamburger used for menus.
- `[data-shell-utility="copilot"]` has `data-icon="sparkles"` or `data-icon="bot"`.
- `page-strategy-studio.html` has `data-action-icon="shield-check"` for validation.
- `page-strategy-studio.html` has `data-action-icon="test-tube"` for Dry Run.
- `page-strategy-studio.html` has `data-action-icon="rocket"` or `data-action-icon="timer"` for submit backtest.
- no non-notification action uses `data-icon="bell"` or a bell-shaped SVG marked as notification.

Run:

```bash
bun test scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL on density, Copilot, validation, Dry Run, and submit backtest.

**Step 3: Write failing collapsible section tests**

Assert for pages with right/context panels:

- every `.context-section` has `data-collapse-priority`.
- every L2/L3 `.context-section` is a `<details>` element.
- every L2 details has `open`.
- every L3 details does not have `open`.
- every L3 summary includes `.collapse-count` and `.collapse-summary`.
- plain non-details `.context-section` is allowed only for L1.

Run:

```bash
bun test scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL because most context sections are plain divs without priority.

**Step 4: Write failing resizable prototype tests**

Assert only P0 prototype groups for now:

- Catalog pages expose `data-resizable-panel-group="catalog-main-detail"` when they have a right detail panel.
- `page-strategy-studio.html` and `page-agent-console.html` expose `data-resizable-panel-group="studio-workspace"`.
- each group has one or more `[data-resize-separator]`.
- each separator has `role="separator"`、`tabindex="0"`、`aria-controls`、`aria-valuemin`、`aria-valuemax`、`aria-valuenow`.

Run:

```bash
bun test scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL because no separator contract exists yet.

**Step 5: Wire the test command**

Add a script:

```json
"prototype:interaction": "vitest run scripts/prototype-interaction-ux-contract.test.ts"
```

Run:

```bash
bun run prototype:interaction
```

Expected: same failing output as direct test.

**Step 6: Commit**

```bash
git add package.json scripts/prototype-interaction-ux-contract.test.ts
git commit -m "test(prototypes): add interaction ux contract gates"
```

---

### Task 2: Canonical Rail And Header Icon Vocabulary

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: all active `docs/designs/specs/prototypes/page-*.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Update shared Rail styles to support anchors**

Make `.rail-icon` styling tag-agnostic:

- reset link underline.
- preserve current square hit target.
- preserve active, hover, focus-visible states.
- keep target size at least 32px in current chrome.

Run:

```bash
bun run prototype:interaction
```

Expected: still FAIL until pages are updated.

**Step 2: Replace every Rail implementation**

For each active prototype:

- replace `div.rail-icon`, `button.rail-icon`, and `role="listitem"` rail items with `<a class="rail-icon" href="...">`.
- keep existing `active` class on the current domain.
- add `aria-current="page"` only on the active domain.
- add fixed Chinese `aria-label` and `title`.
- remove the obsolete extra AI/运维 duplicate item where present.
- add `data-icon` to every rail item.
- add `aria-hidden="true"` to rail SVG.

Run:

```bash
bun run prototype:interaction
```

Expected: Rail contract tests PASS; icon collision and collapsible/resizable tests still FAIL.

**Step 3: Replace domain SVG vocabulary**

Use the canonical icon table:

- Home: keep house.
- Markets: keep trend line.
- Research: replace magnifier with book-open or microscope.
- Trading: replace grid/table with arrow-left-right.
- Platform: replace grid with settings-2 or cpu.

Avoid using the same SVG path for different domains.

Run:

```bash
bun run prototype:interaction
bun test scripts/prototype-design-consistency.test.ts
```

Expected: PASS for Rail and existing design consistency gates.

**Step 4: Fix header utility icon semantics**

Across all active prototypes:

- Copilot: replace star with sparkles or bot, add `data-icon="sparkles"` or `data-icon="bot"`.
- Density: replace hamburger with density-levels icon, add `data-icon="density-levels"`.
- Theme/notifications/help/account keep current semantic icons but add `data-icon`.

Run:

```bash
bun run prototype:interaction
bun test scripts/prototype-view-preferences.test.ts
```

Expected: PASS for header utility and view preference tests.

**Step 5: Commit**

```bash
git add docs/designs/specs/prototypes package.json scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): standardize rail and utility icon semantics"
```

---

### Task 3: Strategy Studio Critical Action Icons

**Files:**

- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: `scripts/page-strategy-studio-prototype.test.ts`

**Step 1: Fix Validate icon**

In `page-strategy-studio.html`, update the validation action:

- add `data-action-icon="shield-check"`.
- replace tally SVG with shield-check SVG.
- keep visible text `校验`.
- keep `aria-label="校验策略"`.

Run:

```bash
bun run prototype:interaction
```

Expected: validation icon assertion PASS.

**Step 2: Fix Dry Run icon**

Update the Dry Run action:

- add `data-action-icon="test-tube"`.
- replace bare play triangle with test-tube SVG.
- keep visible text `Dry Run`.
- change `aria-label` to `执行 Dry Run 模拟`.

Run:

```bash
bun run prototype:interaction
```

Expected: Dry Run icon assertion PASS.

**Step 3: Fix submit backtest icon**

Update submit backtest:

- add `data-action-icon="rocket"` or `data-action-icon="timer"`.
- replace bell SVG.
- keep visible text `提交回测`.
- keep `aria-label="提交回测"`.

Run:

```bash
bun run prototype:interaction
bun test scripts/page-strategy-studio-prototype.test.ts
```

Expected: PASS.

**Step 4: Review local icon reuse**

Still in `page-strategy-studio.html`:

- strategy name badge must not reuse Copilot star.
- inspector tabs must not reuse Rail icons when the semantics differ.
- factor type icons should distinguish momentum, volatility, valuation, liquidity.

Add `data-icon` attributes for these local icons so future tests can detect collisions.

Run:

```bash
bun run prototype:interaction
bun test scripts/page-strategy-studio-prototype.test.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/page-strategy-studio.html scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): clarify strategy studio action icons"
```

---

### Task 4: Shared Collapsible Section Contract

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Add shared styles for summaries**

In `layout-base.css`, support:

- `details.context-section`.
- `summary.context-section-header`.
- `.collapse-count`.
- `.collapse-summary`.
- `.collapse-summary` visible in collapsed state and toned down in expanded state.
- 150ms max-height/opacity transition where feasible.
- `prefers-reduced-motion: reduce` fallback.

Run:

```bash
bun run prototype:interaction
```

Expected: still FAIL until pages add attributes and details.

**Step 2: Add optional JS enhancement**

In `prototype-interactions.js`, add lightweight behavior only if native details is insufficient:

- sync `aria-expanded` on summary.
- preserve native `<details>` keyboard behavior.
- do not replace native disclosure with custom div buttons.

Run:

```bash
bun run prototype:interaction
```

Expected: still FAIL until pages are migrated.

**Step 3: Commit shared contract**

```bash
git add docs/designs/specs/prototypes/shared/layout-base.css docs/designs/specs/prototypes/shared/prototype-interactions.js
git commit -m "fix(prototypes): add collapsible context section contract"
```

---

### Task 5: Catalog Family Collapsible Detail Panels

**Files:**

- Modify: `docs/designs/specs/prototypes/page-markets-screener.html`
- Modify: `docs/designs/specs/prototypes/page-factor-list.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Modify: `docs/designs/specs/prototypes/page-backtest-list.html`
- Modify: `docs/designs/specs/prototypes/page-experiment-list.html`
- Modify: `docs/designs/specs/prototypes/page-watchlist.html`
- Modify: `docs/designs/specs/prototypes/page-markets-calendar.html`
- Modify: `docs/designs/specs/prototypes/page-universe-list.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: relevant `scripts/page-*-prototype.test.ts`

**Step 1: Classify sections**

For each Catalog detail panel:

- Summary/sticky object identity: L1, no details.
- Status/risk/score/selected object context: L2, details open.
- History/presets/related/recent events/normal queue: L3, details collapsed.
- Actions: L1 or L2, but visible by default because operations must stay discoverable.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL until all sections have valid markup.

**Step 2: Convert L2/L3 sections**

For every L2/L3 section:

- convert wrapper to `<details class="context-section" data-collapse-priority="l2" open>`.
- or `<details class="context-section" data-collapse-priority="l3">`.
- convert header to `<summary class="context-section-header">`.
- add `.collapse-count`.
- add `.collapse-summary` for L3.
- keep existing section content unchanged.

Run:

```bash
bun run prototype:interaction
```

Expected: Catalog pages pass collapsible contract tests.

**Step 3: Verify family tests**

Run:

```bash
bun test \
  scripts/page-markets-screener-prototype.test.ts \
  scripts/page-factor-list-prototype.test.ts \
  scripts/page-strategy-list-prototype.test.ts \
  scripts/page-backtest-list-prototype.test.ts \
  scripts/page-experiment-list-prototype.test.ts \
  scripts/page-watchlist-prototype.test.ts \
  scripts/page-markets-calendar-prototype.test.ts \
  scripts/page-universe-list-prototype.test.ts
```

Expected: PASS.

**Step 4: Commit**

```bash
git add docs/designs/specs/prototypes/page-*.html scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): apply catalog collapsible detail panels"
```

---

### Task 6: Analytical, Ops, And Object Hub Collapsible Panels

**Files:**

- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-portfolio.html`
- Modify: `docs/designs/specs/prototypes/page-risk-center.html`
- Modify: `docs/designs/specs/prototypes/page-regime-monitor.html`
- Modify: `docs/designs/specs/prototypes/page-markets-intelligence.html`
- Modify: `docs/designs/specs/prototypes/page-research.html`
- Modify: `docs/designs/specs/prototypes/page-platform.html`
- Modify: `docs/designs/specs/prototypes/page-platform-settings.html`
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`
- Modify: `docs/designs/specs/prototypes/page-orders-ledger.html`
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html`
- Modify: `docs/designs/specs/prototypes/page-factor-analysis.html`
- Modify: `docs/designs/specs/prototypes/page-strategies-detail.html`
- Modify: `docs/designs/specs/prototypes/page-backtest-result.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: relevant `scripts/page-*-prototype.test.ts`

**Step 1: Classify sections by shell family**

Use these defaults:

- Analytical Activity Stack: risk/current queue L2 open; normal queue/history L3 collapsed.
- Ops Detail: incidents/actions L2 open; recent events/log tail L3 collapsed unless currently critical.
- Object Hub: active tab context L2 open; related research/history/notes L3 collapsed.
- Radar: keep existing right rail collapse, but ensure internal low-priority sections use L3 where present.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL until migrated.

**Step 2: Convert L2/L3 markup**

Apply the same `<details>` contract from Task 5. Keep L1 sticky summaries as normal sections with `data-collapse-priority="l1"`.

Run:

```bash
bun run prototype:interaction
```

Expected: all collapsible contract tests PASS.

**Step 3: Run affected page tests**

Run:

```bash
bun test \
  scripts/page-markets-intelligence-prototype.test.ts \
  scripts/page-platform-prototype.test.ts \
  scripts/page-platform-settings-prototype.test.ts \
  scripts/page-signals-inbox-prototype.test.ts \
  scripts/page-orders-ledger-prototype.test.ts \
  scripts/page-instrument-hub-prototype.test.ts \
  scripts/page-factor-analysis-prototype.test.ts \
  scripts/page-strategies-detail-prototype.test.ts
```

Expected: PASS. Pages without dedicated tests, currently including Trading Overview, Portfolio, Risk Center, Regime Monitor, Research, and Backtest Result, stay covered by `scripts/prototype-interaction-ux-contract.test.ts` unless implementation adds meaningful page-specific behavior.

**Step 4: Commit**

```bash
git add docs/designs/specs/prototypes/page-*.html scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): apply workspace collapsible section defaults"
```

---

### Task 7: Bottom Tray Motion And State Contract

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console.html`
- Modify: `docs/designs/specs/prototypes/page-platform.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Add Bottom Tray tests**

Assert:

- exactly these pages expose `[data-bottom-tray]`: Strategy Studio, Agent Console, Platform, Trading Overview.
- each has `data-bottom-tray-state="collapsed|peek|expanded"`.
- each has `[data-bottom-tray-toggle][aria-controls]`.
- each controlled content id exists.
- toggle label changes between collapsed/peek/expanded states in JS.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL on motion/toggle state details if not implemented.

**Step 2: Improve shared CSS**

In `layout-base.css`:

- `collapsed`: content max-height 0, opacity 0, summary visible.
- `peek`: one-line or compact latest state visible.
- `expanded`: logs/content area visible within viewport budget.
- use max-height/opacity for layout-safe transition.
- do not rely on transform-only hiding.
- add reduced-motion fallback.

Run:

```bash
bun run prototype:interaction
```

Expected: CSS-related gates PASS.

**Step 3: Implement prototype toggle behavior**

In `prototype-interactions.js`:

- cycle `collapsed -> peek -> expanded -> collapsed`.
- update `aria-expanded`.
- update toggle `aria-label`.
- keep content in document flow.

Run:

```bash
bun run prototype:interaction
bun test scripts/prototype-view-preferences.test.ts
```

Expected: PASS.

**Step 4: Commit**

```bash
git add docs/designs/specs/prototypes/shared docs/designs/specs/prototypes/page-*.html scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): refine bottom tray state transitions"
```

---

### Task 8: Prototype Resizable Panel Contract For P0 Shells

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: Catalog pages from Task 5
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: `scripts/prototype-view-preferences.test.ts`

**Step 1: Add shared separator styles**

In `layout-base.css`, add:

- `.resize-separator` visual 1px line.
- `::before` or equivalent 24px hit area.
- hover/focus/active states using existing brand accent tokens.
- `cursor: col-resize` for horizontal splits.
- `cursor: row-resize` for bottom tray if later enabled.
- no animation while dragging.

Run:

```bash
bun run prototype:interaction
```

Expected: still FAIL until separators are added.

**Step 2: Add prototype JS behavior**

In `prototype-interactions.js`, implement small scoped behavior:

- only activates inside `[data-resizable-panel-group]`.
- pointer drag updates a CSS variable on the group root.
- keyboard arrows update `aria-valuenow`.
- Shift+Arrow adjusts by a smaller step.
- double click resets to default.
- clamp to min/max.

Use no external dependencies.

Run:

```bash
bun run prototype:interaction
```

Expected: still FAIL until pages add DOM hooks.

**Step 3: Apply Catalog shell separators**

For each Catalog page with a right detail panel:

- wrap main and detail areas with `data-resizable-panel-group="catalog-main-detail"`.
- add separator between main and detail.
- control right panel width through a CSS variable such as `--prototype-detail-width`.
- set `aria-valuemin="220"`、`aria-valuemax="520"`、default `aria-valuenow="320"`.

Run:

```bash
bun run prototype:interaction
```

Expected: Catalog resizable assertions PASS.

**Step 4: Apply Studio shell separators**

For Strategy Studio and Agent Console:

- add `data-resizable-panel-group="studio-workspace"`.
- add separator between source/sidebar and main if present.
- add separator between main and inspector/detail.
- set accessible labels such as `aria-label="调整检查器宽度"`.

Run:

```bash
bun run prototype:interaction
bun test scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts
```

Expected: Studio assertions PASS.

**Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/shared docs/designs/specs/prototypes/page-*.html scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): add p0 resizable panel affordances"
```

---

### Task 9: Audit Document Calibration

**Files:**

- Modify: `docs/designs/specs/20_interaction_ux_audit.md`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Correct outdated implementation guidance**

Update the audit document:

- Rail navigation should use links, not generic buttons.
- `react-resizable-panels` current version is deferred to React TODO, not prototype implementation.
- prototype resize hit area should be at least 24px even when visual line is 1px.
- context section baseline should mention the measured 50 sections / 3 details gap.

Run:

```bash
bun run prototype:interaction
```

Expected: PASS.

**Step 2: Add prototype-only remediation status**

Append a short status section:

- fixed in prototype.
- deferred to React.
- needs product/design approval.

Run:

```bash
bun run prototype:interaction
```

Expected: PASS.

**Step 3: Commit**

```bash
git add docs/designs/specs/20_interaction_ux_audit.md
git commit -m "docs(prototypes): calibrate interaction ux audit plan"
```

---

### Task 10: React TODO Backlog

**Files:**

- Modify: `docs/plans/prototype-to-react-enhancement-backlog.md`

**Step 1: Add interaction UX section**

Append a "Prototype Interaction UX 2026-04-30" section with TODOs:

- Implement React Rail with Router links and canonical icon registry.
- Replace prototype inline SVGs with Lucide/custom icon components.
- Implement React disclosure/accordion component for context sections.
- Implement Bottom Tray state machine and persisted user preference.
- Evaluate and, after approval, install `react-resizable-panels`.
- Implement Shell-level resizable panel groups for Catalog and Studio first.
- Persist layouts with Zustand/localStorage or library storage.
- Add Playwright keyboard tests for disclosure, tray, and separator interactions.

Run:

```bash
rg -n "Prototype Interaction UX 2026-04-30|react-resizable-panels|Bottom Tray state machine" docs/plans/prototype-to-react-enhancement-backlog.md
```

Expected: all TODO entries are present.

**Step 2: Commit**

```bash
git add docs/plans/prototype-to-react-enhancement-backlog.md
git commit -m "docs(react): record prototype interaction ux followups"
```

---

## Verification

Run in this order:

```bash
bun run prototype:interaction
bun test scripts/prototype-design-consistency.test.ts
bun test scripts/prototype-view-preferences.test.ts
bun run prototype:gates
bun run prototype:visual-matrix
bun run check
```

Expected:

- interaction contract passes across 27 active prototypes.
- existing prototype design gates still pass.
- direct theme/density toggles still work.
- visual matrix produces non-empty screenshots for representative pages.
- full project check passes.

## React Implementation TODO

Do not implement these in this prototype phase:

- Add a React `RailNav` component in `src/features/shell/components/rail.tsx` using TanStack Router links.
- Add a typed icon registry for domain icons, header utilities, and local action icons.
- Add a `ContextDisclosureSection` React component with `aria-expanded` and `aria-controls`.
- Add persisted section preferences in `src/features/shell/hooks/use-ui-preferences.ts`.
- Add a Bottom Tray state machine for `collapsed | peek | expanded`.
- Request approval before installing `react-resizable-panels`.
- Current package lookup on 2026-04-30 returned `react-resizable-panels@4.10.0`; re-check before requesting approval.
- If approved, wrap Catalog and Studio layouts with resizable panel primitives first.
- Persist panel layout with Zustand or the library storage API.
- Add RTL/Playwright tests for keyboard arrows, Enter collapse/restore, double-click reset, and reduced-motion behavior.

## Execution Notes

- Work one task at a time.
- Prefer a dedicated worktree before implementation.
- Do not modify `src/` during this plan.
- Keep each commit focused.
- If a task requires a new dependency or design token, pause and ask for approval.
- Before declaring completion, run `bun run check`.
