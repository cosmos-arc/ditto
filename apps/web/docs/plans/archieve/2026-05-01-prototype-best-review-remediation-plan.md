# Prototype Best Review Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `2026-04-30-prototype-audit-impeccable.md` 与 `2026-04-30-prototype-ui-ux-pro-max-best-review.md` 中仍然有效的原型审查结论转化为可执行整改任务，使 `docs/designs/specs/prototypes/` 从可演示状态推进到 Best 级冻结候选。

**Architecture:** 先补机器门禁，防止继续依赖人工审查记忆；再按共享基础设施、设计 token、Shell 响应式、页面模式和专家效率分层修复。所有跨页行为进入 `shared/` 与 `scripts/`，页面特定业务主答案留在对应 `page-*.html`，规范同步写回 `docs/designs/specs/`。

**Tech Stack:** HTML prototypes, shared prototype CSS/JS, Design Tokens, Vitest, JSDOM, Playwright, Bun, Biome.

---

## Scope

本计划处理当前活跃原型与设计规范：

- `docs/designs/specs/prototypes/page-*.html`
- `docs/designs/specs/prototypes/shared/layout-base.css`
- `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- `docs/designs/specs/prototypes/tokens-style.css`
- `src/styles/design-tokens/tokens-semantic.css`
- `scripts/prototype-*.test.ts`
- `scripts/audit-wcag-contrast.mjs`
- `docs/designs/specs/04_interaction_state_spec.md`
- `docs/designs/specs/10_ditto_shell_family_spec.md`
- `docs/designs/specs/11_ditto_page_pattern_library.md`
- `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
- `docs/designs/specs/20_interaction_ux_audit.md`

本计划不处理：

- `src/` React 页面重构，除非某个 gate 需要补测试工具类型。
- 新依赖安装。
- IA 路由重组。
- 真实交易、API、Mock 数据模型变化。
- Design Token 语义新增的直接实现。若必须新增或改变语义 token，先停下请求人工批准。

## Current Baseline

2026-05-01 复核结果：

| 项 | 当前事实 | 判断 |
|---|---:|---|
| `bun run prototype:gates` | PASS, 27/27 active prototypes | 页面骨架没有阻塞问题 |
| `bun run prototype:interaction` | PASS, 9 tests | 现有交互门禁覆盖不够严 |
| `bun run audit:tokens:contrast` | FAIL, 9 fail / 8 warn | Best 级前必须修 |
| `bun run check` | PASS, 140 files / 1560 tests | 当前工程基线健康 |
| 活跃页缺 `<h1>` | 19 页 | P0 A11y |
| `role="button"` | 至少 78 处活跃页相关实例 | P0 键盘操作风险 |
| `data-primary-answer` | 3 页 | 5 秒主答案合同覆盖不足 |
| `100vh` | 共享 CSS 与多页仍存在 | 移动和窄屏风险 |
| `transition: all` | 共享 CSS 与多页仍存在 | 性能与可预测性风险 |

## Remediation Strategy

执行顺序固定为：

1. 先补门禁：heading、ARIA、keyboard、contrast、viewport、primary answer、data-viz light mode。
2. 再修共享基础：focus、role button、tabs、motion、CSS 性能、density。
3. 再修视觉系统：contrast usage tiers、Light Mode data viz、A 股热力图。
4. 再修页面任务：Home 主答案、Catalog 家族差异化。
5. 最后补专家效率：布局持久化、表格高级操作、Command Palette 上下文动作。

每个任务完成后都运行局部验证；最后必须运行 `bun run check`。

## Definition of Done

- `bun run check` 通过。
- `bun run prototype:gates` 通过，27/27 active prototypes 无 blocking / non-blocking issues。
- `bun run prototype:interaction` 通过。
- `bun run audit:tokens:contrast` 对 operational / data-critical 文本 0 fail。
- 活跃原型全部有语义 `<h1>`。
- 所有 `[role="button"]` 要么换成原生按钮/链接，要么由共享键盘激活模块覆盖。
- 所有 tab pattern 有完整 `role="tab"`、`aria-selected`、`aria-controls`、`role="tabpanel"`、`aria-labelledby`。
- 每个页面有 `data-primary-answer` 或明确的 `data-primary-answer-equivalent`。
- A 股 Light Mode 数据可视化不再复用 Dark Mode 大色块基底。
- Catalog 家族页面的 summary / inspector 明确区分业务任务。
- 规范文档与原型事实一致。

---

### Task 1: Add Best Review Regression Gates

**Files:**

- Modify: `scripts/prototype-design-consistency.test.ts`
- Modify: `scripts/prototype-interaction-ux-contract.test.ts`
- Modify: `scripts/audit-wcag-contrast.mjs`
- Read: `docs/designs/specs/prototypes/.edition-manifest.json`
- Read: `docs/reviews/2026-04-30-prototype-audit-impeccable.md`
- Read: `docs/reviews/2026-04-30-prototype-ui-ux-pro-max-best-review.md`

**Step 1: Write failing heading and style-label tests**

Extend the active prototype scan to assert:

```ts
expect(document.querySelectorAll("h1").length).toBeGreaterThanOrEqual(1);
expect(document.querySelectorAll(".style-label:not([aria-hidden='true'])")).toHaveLength(0);
```

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on active pages that still use `<span class="header-title">` and visible `.style-label`.

**Step 2: Write failing `role="button"` keyboard contract tests**

In `prototype-interaction-ux-contract.test.ts`, add a JSDOM test that loads `shared/prototype-interactions.js`, injects:

```html
<div id="target" role="button" tabindex="0" aria-label="测试动作"></div>
```

Attach a click listener, dispatch `keydown` for Enter and Space, and assert two click activations.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL until shared JS adds a global role button keyboard activation module.

**Step 3: Write failing ARIA tabs tests**

For every active prototype:

- every `[role="tab"]` has `aria-selected`.
- every `[role="tab"]` has `aria-controls`.
- `aria-controls` points to an existing `role="tabpanel"`.
- every `role="tabpanel"` has `aria-labelledby` pointing back to a tab.

Run:

```bash
bun test scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL on current incomplete tab implementations.

**Step 4: Write failing CSS hygiene tests**

Add tests that scan active prototype CSS and shared CSS:

- no `100vh`; use `100dvh` or documented fixed canvas exception.
- no `transition: all`.
- no `outline: none` unless the same selector block defines `box-shadow` or `outline`.
- no `font-size: 9px` in real information surfaces.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on shared CSS and A Shares heatmap.

**Step 5: Add contrast usage tiers**

Extend `audit-wcag-contrast.mjs` to classify checked text tokens:

```js
const TEXT_USAGE_TIERS = {
  "text-disabled": "decorative",
  "text-quaternary": "metadata",
  "text-data-stale": "operational",
  "text-tertiary": "metadata",
  "text-secondary": "operational",
};
```

Rules:

- `decorative`: report only, no fail.
- `metadata`: warn below 4.5:1, fail below 3:1.
- `operational`: fail below 4.5:1.
- `data-critical`: fail below 4.5:1 and require non-color marker if applicable.

Run:

```bash
bun run audit:tokens:contrast
```

Expected: FAIL until token values and usage rules are fixed.

**Step 6: Commit**

```bash
git add scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts scripts/audit-wcag-contrast.mjs
git commit -m "test(prototypes): add best review regression gates"
```

---

### Task 2: Harden Shared Accessibility And Interaction Baseline

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: active `docs/designs/specs/prototypes/page-*.html`
- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Run the failing tests**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL on heading, style-label, role button, tabs, focus and CSS hygiene.

**Step 2: Add semantic heading baseline**

In active page headers, replace:

```html
<span class="header-title">首页</span>
```

with:

```html
<h1 class="header-title">首页</h1>
```

For object pages that already use `<h1 class="object-name">`, leave them unchanged.

In `layout-base.css`, ensure:

```css
.header-title,
h1.header-title {
  margin: 0;
  font: inherit;
  color: inherit;
}
```

**Step 3: Hide prototype style labels from assistive tech**

Add `aria-hidden="true"` to every active-page `.style-label`:

```html
<div class="style-label" aria-hidden="true">Graphite Studio ...</div>
```

**Step 4: Implement global role button keyboard activation**

In `prototype-interactions.js`, add an `InteractiveRoleButtons` module:

```js
var InteractiveRoleButtons = {
  init: function () {
    document.addEventListener("keydown", function (event) {
      var target = event.target.closest('[role="button"]');
      if (!target) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      target.click();
    });
  },
};
```

Call it from the shared init sequence.

**Step 5: Complete tab ARIA pattern**

Use `page-signals-inbox.html` as the template, then normalize all active tab groups:

```html
<label
  id="tab-agent-plans"
  for="agent-plans"
  class="agent-tab"
  role="tab"
  aria-selected="true"
  aria-controls="panel-agent-plans"
>
  计划
</label>

<div
  id="panel-agent-plans"
  class="tab-panel"
  role="tabpanel"
  aria-labelledby="tab-agent-plans"
>
```

For JS-driven tabs, update `Tabs` to maintain `aria-selected` and `aria-hidden`.

**Step 6: Fix focus visible baseline**

In `layout-base.css`, replace weak focus rules:

```css
.filter-select:focus,
.filter-search:focus {
  border-color: var(--brand-accent);
  outline: none;
}
```

with:

```css
.filter-select:focus-visible,
.filter-search:focus-visible {
  border-color: var(--brand-accent);
  outline: none;
  box-shadow: 0 0 0 2px var(--interaction-focus-ring);
}
```

If `--interaction-focus-ring` is not available, map it to an existing focus token in shared prototype scope without adding product SSOT tokens.

**Step 7: Replace broken select arrow styling**

Remove `.filter-select::after`, because pseudo-elements do not render on native select. Use background image on `.filter-select`:

```css
.filter-select {
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23888' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right var(--space-8) center;
}
```

**Step 8: Make reduced motion live**

Replace the load-only value:

```js
var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
```

with a live media query object:

```js
var motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
var reducedMotion = motionQuery.matches;
motionQuery.addEventListener("change", function (event) {
  reducedMotion = event.matches;
  document.documentElement.toggleAttribute("data-reduced-motion", reducedMotion);
});
```

**Step 9: Verify**

Run:

```bash
bun run prototype:interaction
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates
```

Expected: PASS.

**Step 10: Commit**

```bash
git add docs/designs/specs/prototypes docs/designs/specs/04_interaction_state_spec.md scripts/prototype-interaction-ux-contract.test.ts scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): harden accessibility baseline"
```

---

### Task 3: Fix Contrast Usage Tiers And Token Documentation

**Files:**

- Modify: `scripts/audit-wcag-contrast.mjs`
- Modify: `src/styles/design-tokens/tokens-semantic.css`
- Modify: `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Test: `scripts/audit-wcag-contrast.mjs`

**Step 1: Confirm approval gate for token semantic changes**

Before changing product token values, confirm whether the remediation may adjust existing semantic text tokens.

If approval is not granted, stop after documenting the tier rules and usage restrictions.

**Step 2: Run the contrast audit**

Run:

```bash
bun run audit:tokens:contrast
```

Expected: FAIL on operational `text-data-stale` and metadata failures.

**Step 3: Document usage tiers**

In `14_ditto_token_naming_layering_spec.md`, add:

| Tier | Examples | Contrast Gate |
|---|---|---|
| decorative | disabled affordance, watermark | report only |
| metadata | optional timestamp, decorative caption | warn below 4.5, fail below 3 |
| operational | stale status, table metadata, queue time | fail below 4.5 |
| data-critical | risk, trade, error, approval | fail below 4.5 and require non-color marker |

**Step 4: Adjust existing token values conservatively**

In `tokens-semantic.css`, tune only existing semantic values:

- raise `--text-data-stale` to at least 4.5:1 on `surface-modal`, `surface-overlay`, `surface-strip`, and `surface-muted`.
- keep `--text-disabled` decorative and exclude it from operational pass/fail.
- restrict `--text-quaternary` to decorative or low-risk metadata in docs.

Do not add new token names unless approved.

**Step 5: Replace operational uses of quaternary text**

Scan:

```bash
rg "text-quaternary|text-data-stale" docs/designs/specs/prototypes src
```

For status, timestamps, stale indicators, table metadata and queue timing, use `text-tertiary`, `text-secondary`, or `text-data-stale` according to the tier.

**Step 6: Verify**

Run:

```bash
bun run audit:tokens:contrast
bun run build:tokens:check
bun run check
```

Expected: PASS for operational / data-critical contrast tiers. Decorative disabled text may remain reported but not fail.

**Step 7: Commit**

```bash
git add scripts/audit-wcag-contrast.mjs src/styles/design-tokens/tokens-semantic.css docs/designs/specs/14_ditto_token_naming_layering_spec.md docs/designs/specs/04_interaction_state_spec.md docs/designs/specs/prototypes src
git commit -m "fix(tokens): enforce contrast usage tiers"
```

---

### Task 4: Responsive Shell Hardening

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-toggles.css`
- Modify: active `docs/designs/specs/prototypes/page-*.html` with page-local `100vh`
- Modify: `docs/designs/specs/10_ditto_shell_family_spec.md`
- Modify: `scripts/run-prototype-gates.ts`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/run-prototype-gates.ts`

**Step 1: Write failing viewport tests**

Extend prototype design consistency tests:

- active prototype CSS must not contain raw `100vh`.
- active prototype CSS should use `100dvh` for locked viewport shells.
- shared Shell CSS must define breakpoints for `1200px`, `1024px`, and `768px`.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL.

**Step 2: Replace raw viewport height**

Replace common patterns:

```css
height: 100vh;
min-height: 100vh;
max-height: 100vh;
```

with:

```css
height: 100dvh;
min-height: 100dvh;
max-height: 100dvh;
```

For calculated heights:

```css
height: calc(100dvh - var(--shell-status-bar-height));
```

**Step 3: Define Shell degradation rules**

In `layout-base.css`, add breakpoint sections:

```css
@media (max-width: 1200px) {
  .shell-catalog {
    --prototype-detail-width: min(300px, 28vw);
  }
}

@media (max-width: 1024px) {
  .shell-header [data-header-utility-bar] {
    max-width: 44vw;
  }
}

@media (max-width: 768px) {
  .shell-catalog,
  .shell-studio,
  .shell-agent,
  .shell-radar {
    overflow-x: auto;
  }
}
```

Keep desktop terminal behavior intact.

**Step 4: Extend gates**

In `run-prototype-gates.ts`, add at least one narrow-professional viewport:

```ts
{ name: "VP-NARROW", width: 1200, height: 800 }
```

Do not add mobile phone gates until Shell spec defines mobile product intent.

**Step 5: Update Shell Family spec**

In `10_ditto_shell_family_spec.md`, add responsive strategy per Shell:

- Command Center: pulse single row, context rail collapses.
- Analytical: right stack narrows, analysis band remains accessible.
- Catalog: inspector can collapse to summary rail.
- Object Hub: bottom timeline becomes tabbed strip.
- Studio: source panel and inspector can collapse independently.
- Ops: detail panel collapses before main queue.
- Radar: right rail collapses to event/risk summary.

**Step 6: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates
```

Expected: PASS.

**Step 7: Commit**

```bash
git add docs/designs/specs/prototypes docs/designs/specs/10_ditto_shell_family_spec.md scripts/run-prototype-gates.ts scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): harden shell viewport behavior"
```

---

### Task 5: Light Mode Data Visualization Remediation For A Shares

**Files:**

- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
- Modify: `docs/designs/specs/12_ditto_data_views_spec.md`
- Modify: `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-visual-matrix.ts`

**Step 1: Write failing data-viz tests**

Add checks for `page-a-shares.html`:

- no real data label uses `font-size: 9px`.
- heatmap cells include non-color sign markers or accessible sign text.
- light theme defines a separate map scale, not only dark scale reuse.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL.

**Step 2: Add light/dark map scales**

In `page-a-shares.html`, keep local prototype tokens if product token approval is not available:

```css
:root {
  --map-light-up-1: color-mix(in oklch, var(--market-up-fg) 14%, var(--surface-panel-base));
  --map-light-up-2: color-mix(in oklch, var(--market-up-fg) 20%, var(--surface-panel-base));
  --map-light-down-1: color-mix(in oklch, var(--market-down-fg) 14%, var(--surface-panel-base));
  --map-light-down-2: color-mix(in oklch, var(--market-down-fg) 20%, var(--surface-panel-base));
}

[data-theme="light"] .map-container {
  --heat-up-1: var(--map-light-up-1);
  --heat-up-2: var(--map-light-up-2);
  --heat-down-1: var(--map-light-down-1);
  --heat-down-2: var(--map-light-down-2);
}
```

Use page-local names until the token layer accepts dedicated data-viz light scale tokens.

**Step 3: Add non-color encoding**

Inside `.heatmap-cell`, ensure visible sign markers:

```html
<span class="hm-sign" aria-hidden="true">▲</span>
<span class="hm-change up">+3.24%</span>
```

For down cells:

```html
<span class="hm-sign" aria-hidden="true">▼</span>
<span class="hm-change down">-5.23%</span>
```

Accessible labels already include `涨幅` / `跌幅`; preserve them.

**Step 4: Raise minimum label size**

Replace:

```css
.heatmap-cell[data-size-bucket="sm"] .hm-name { font-size: 9px; }
```

with:

```css
.heatmap-cell[data-size-bucket="sm"] .hm-name {
  font-size: var(--font-size-10);
}
```

Hide low-priority sub labels before shrinking real labels below 10px.

**Step 5: Update data view spec**

In `12_ditto_data_views_spec.md`, add:

- data viz light/dark scales are independent.
- large red/green fill cannot be the only information channel.
- chart labels carrying real information are minimum 10px; interactive scan labels target 12px.

**Step 6: Generate visual matrix**

Run:

```bash
bun run prototype:visual-matrix
```

Expected: new light/compact A Shares screenshot shows lighter map fills, stronger boundary and readable labels.

**Step 7: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates
```

Expected: PASS.

**Step 8: Commit**

```bash
git add docs/designs/specs/prototypes/page-a-shares.html docs/designs/specs/12_ditto_data_views_spec.md docs/designs/specs/14_ditto_token_naming_layering_spec.md scripts/prototype-design-consistency.test.ts test-results
git commit -m "fix(prototypes): improve a shares light data visualization"
```

---

### Task 6: Primary Answer Contract Across Active Pages

**Files:**

- Modify: active `docs/designs/specs/prototypes/page-*.html`
- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Modify: `docs/designs/specs/10_ditto_shell_family_spec.md`
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Write failing primary answer tests**

For every active prototype, assert one of:

- `[data-primary-answer]`
- `[data-primary-answer-equivalent]`

Also assert the region contains:

- one judgment sentence or summary label.
- one key metric.
- one primary action or drill-down target.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL because only a few pages currently expose the contract.

**Step 2: Define the contract in specs**

In `04_interaction_state_spec.md` and `11_ditto_page_pattern_library.md`, define:

```text
Primary Answer = 一句话判断 + 1 个关键数字 + 2-3 个证据 + 1 个主动作 + 明确影响范围。
```

Shell mapping:

- Command Center: decision card.
- Analytical: main instrument readout or context strip.
- Catalog: task-specific summary strip.
- Object Hub: object status header.
- Studio: current build/run status.
- Ops: incident/service health priority.
- Radar: market scope strip + selected map summary.

**Step 3: Annotate existing equivalents**

Add `data-primary-answer-equivalent` to already valid main answer regions, for example:

```html
<div class="scope-strip" data-primary-answer-equivalent ...>
```

Only add the attribute where the content truly answers the page's core question.

**Step 4: Fill missing main answer content**

For pages whose current header or summary is too generic, add or revise a compact summary strip:

```html
<div class="catalog-answer-strip" data-primary-answer>
  <span class="answer-judgment">5 个策略可直接运行，1 个需要风险复核</span>
  <span class="answer-metric">最佳 Sharpe 1.85</span>
  <button class="answer-action" type="button">运行回测</button>
</div>
```

Avoid adding card clutter. Prefer one dense strip or existing summary surface.

**Step 5: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates
```

Expected: PASS.

**Step 6: Commit**

```bash
git add docs/designs/specs/prototypes docs/designs/specs/04_interaction_state_spec.md docs/designs/specs/10_ditto_shell_family_spec.md docs/designs/specs/11_ditto_page_pattern_library.md scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): define primary answer contract"
```

---

### Task 7: Home First Screen Decision Redesign

**Files:**

- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/10_ditto_shell_family_spec.md`
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/run-prototype-gates.ts`

**Step 1: Write failing Home-specific test**

Assert `page-home.html` has:

- one `data-contract-slot="global-pulse"` or equivalent single pulse strip.
- one `data-contract-slot="decision-card"` with `data-primary-answer`.
- priority queue default content contains only P1/P2 visible items.
- regular activity stream is not before the decision card in DOM order.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL if current Today Pulse competes with the Decision Banner.

**Step 2: Compress top status into Global Pulse**

Convert the current five equal pulse cards into a denser single row:

```html
<div class="global-pulse" data-contract-slot="global-pulse">
  <span>总权益 ¥25.43M</span>
  <span>风险 中等</span>
  <span>待处理 2, P1 1</span>
  <span>后台任务 3</span>
</div>
```

Keep it scannable and secondary to the decision card.

**Step 3: Upgrade decision banner into Decision Card**

The card must answer:

1. 今天最该处理什么。
2. 为什么。
3. 风险或机会多大。
4. 下一步动作是什么。

Suggested structure:

```html
<section class="decision-card" data-contract-slot="decision-card" data-primary-answer>
  <p class="decision-card-judgment">优先复核贵州茅台卖出信号，组合回撤接近预警线。</p>
  <div class="decision-card-evidence">
    <span>Alpha v3 置信度 87%</span>
    <span>科技集中度 37.2%</span>
    <span>VaR 95% 分位</span>
  </div>
  <div class="decision-card-actions">
    <label for="overlay-signal-detail" class="decision-cta primary">复核信号</label>
    <button class="decision-cta secondary" type="button">查看风控</button>
  </div>
</section>
```

**Step 4: Reduce competing modules**

- Priority Queue: visible area only P1/P2.
- Activity stream: move below priority queue or reduce visual weight.
- Data health: keep only abnormal state in right rail; normal state collapses.

**Step 5: Verify screenshots**

Run:

```bash
bun run prototype:gates
```

Expected: Home screenshots show one dominant decision surface within first screen.

**Step 6: Commit**

```bash
git add docs/designs/specs/prototypes/page-home.html docs/designs/specs/10_ditto_shell_family_spec.md docs/designs/specs/11_ditto_page_pattern_library.md scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): sharpen home primary decision"
```

---

### Task 8: Catalog Family Task Differentiation

**Files:**

- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Modify: `docs/designs/specs/prototypes/page-backtest-list.html`
- Modify: `docs/designs/specs/prototypes/page-experiment-list.html`
- Modify: `docs/designs/specs/prototypes/page-factor-list.html`
- Modify: `docs/designs/specs/prototypes/page-watchlist.html`
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Write failing Catalog subtype tests**

For the five pages, assert each has task-specific summary labels:

| Page | Required labels |
|---|---|
| strategy-list | 可运行, 需处理, Sharpe, 风险约束 |
| backtest-list | 对比, 失败, 基线, MDD |
| experiment-list | 胜出, 参数稳定性, 显著性, 待复核 |
| factor-list | IC, IR, 衰减, 覆盖 |
| watchlist | 触发动作, 信号结构, stale, 下一步 |

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL where current summaries are too generic.

**Step 2: Update Page Pattern Library**

In Catalog / Screener Workspace, add subtypes:

- Strategy Library Catalog.
- Backtest Comparison Ledger.
- Experiment Result Matrix.
- Factor Quality Catalog.
- Watchlist Action Queue.

Each subtype must define main answer, inspector role and recommended summary metrics.

**Step 3: Revise Strategy List**

Replace generic performance summary with:

- 可运行策略数量。
- 需处理策略数量。
- 最佳健康策略。
- 最近运行状态。
- 风险约束 / 暂停原因.

Right inspector emphasizes strategy health, last run, risk constraints and run action.

**Step 4: Revise Backtest List**

Summary emphasizes:

- 可加入对比。
- 失败 / 异常。
- 当前基线。
- 最佳 Sharpe.
- 中位 MDD.

Right inspector includes small equity curve, diagnostic summary and "加入对比".

**Step 5: Revise Experiment List**

Summary emphasizes:

- 胜出参数。
- 参数稳定性。
- 显著性。
- 失败原因。
- 待复核.

Add a lightweight result matrix or parameter stability strip before the table if space allows.

**Step 6: Revise Factor List**

Summary emphasizes:

- 平均 IC / IR.
- 衰减数量。
- 覆盖率。
- 关联策略。
- 最近失效信号.

Right inspector becomes quality diagnostic, not generic detail.

**Step 7: Revise Watchlist**

Summary emphasizes:

- 下一动作对象。
- 买/卖/观望结构。
- stale quote.
- trigger reason.
- send-to workflow.

Right inspector emphasizes signal structure and action recommendation.

**Step 8: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates
```

Expected: PASS and screenshots show clear family differences without card clutter.

**Step 9: Commit**

```bash
git add docs/designs/specs/prototypes/page-strategy-list.html docs/designs/specs/prototypes/page-backtest-list.html docs/designs/specs/prototypes/page-experiment-list.html docs/designs/specs/prototypes/page-factor-list.html docs/designs/specs/prototypes/page-watchlist.html docs/designs/specs/11_ditto_page_pattern_library.md scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): differentiate catalog task surfaces"
```

---

### Task 9: Expert Efficiency Contracts

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: active Catalog / Studio / Ops pages where contracts are visible
- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Modify: `docs/plans/prototype-to-react-enhancement-backlog.md`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Write failing persistence and command context tests**

Add tests for:

- resizable panel writes route-scoped preference key.
- double-click separator resets to default.
- separator Arrow keys adjust by 40px.
- Shift + Arrow adjusts by 8px.
- pages with selected rows expose `data-selected-object-region`.
- pages with command trigger expose `data-command-scope`.
- selected object pages expose `data-command-context-actions`.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL until contracts are added.

**Step 2: Add layout persistence**

In `ResizablePanels`, persist values:

```js
var key = "ditto:prototype:layout:" + location.pathname + ":" + varName;
localStorage.setItem(key, String(nextValue));
```

On init, restore the value if it is within min/max.

**Step 3: Add double-click reset**

On `[data-resize-separator]`:

```js
separator.addEventListener("dblclick", function () {
  ResizablePanels._setValue(group, separator, defaultValue);
});
```

**Step 4: Define table expert contracts**

In specs and prototype markup, add declarative hooks:

- `data-table-column-resize-ready`
- `data-table-freeze-ready`
- `data-bulk-action-bar`
- `data-active-filters-summary`
- `data-row-context-menu-ready`

Prototype may show static affordances; React implementation goes to backlog.

**Step 5: Add Command Palette context action contracts**

For representative pages:

```html
<div data-command-context-actions="run-backtest,clone-strategy,view-recent-runs,pause-strategy"></div>
```

Required examples:

| Page | Actions |
|---|---|
| Watchlist | generate-signal, open-instrument-hub, send-to-research, remove-watch |
| Strategy List | run-backtest, clone-strategy, view-recent-runs, pause-strategy |
| Backtest List | add-to-compare, view-curve, copy-params, generate-report |
| Signals Inbox | approve, reject, send-to-order, view-evidence |
| Platform | retry, view-logs, mute-alert, create-incident |

**Step 6: Update React backlog**

Add follow-ups:

- persisted table columns.
- frozen columns.
- full command palette implementation.
- selected object driven cross-region state.
- modal focus trap and overlay background inertness in React.

**Step 7: Verify**

Run:

```bash
bun run prototype:interaction
bun run prototype:gates
```

Expected: PASS.

**Step 8: Commit**

```bash
git add docs/designs/specs/prototypes docs/designs/specs/04_interaction_state_spec.md docs/designs/specs/11_ditto_page_pattern_library.md docs/plans/prototype-to-react-enhancement-backlog.md scripts/prototype-interaction-ux-contract.test.ts
git commit -m "feat(prototypes): add expert efficiency contracts"
```

---

### Task 10: Performance And Maintainability Hygiene

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/tokens-style.css`
- Modify: active page-local CSS with `transition: all`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Run failing hygiene tests**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts
```

Expected: FAIL on `transition: all`, raw `100vh`, no-op comfortable density, CSS var recalculation and MouseGlow throttling tests.

**Step 2: Cache CSS variable reads**

In `prototype-interactions.js`:

```js
var computedStyleCache = null;

function cssVar(name, fallback) {
  if (!computedStyleCache) {
    computedStyleCache = getComputedStyle(document.documentElement);
  }
  var value = computedStyleCache.getPropertyValue(name);
  return value ? value.trim() : fallback;
}

document.addEventListener("themechange", function () {
  computedStyleCache = null;
});
```

Also clear cache when density changes if density-dependent vars are read.

**Step 3: Throttle MouseGlow**

Replace direct `mousemove` background updates with requestAnimationFrame:

```js
var frame = 0;
var lastEvent = null;

el.addEventListener("mousemove", function (event) {
  lastEvent = event;
  if (frame) return;
  frame = requestAnimationFrame(function () {
    frame = 0;
    var rect = el.getBoundingClientRect();
    var x = lastEvent.clientX - rect.left;
    var y = lastEvent.clientY - rect.top;
    el.style.setProperty("--_glow-x", x + "px");
    el.style.setProperty("--_glow-y", y + "px");
  });
});
```

Move the gradient itself into CSS where possible.

**Step 4: Remove `transition: all`**

Replace with explicit properties:

```css
transition:
  background-color var(--motion-duration-fast) var(--motion-easing-standard),
  border-color var(--motion-duration-fast) var(--motion-easing-standard),
  color var(--motion-duration-fast) var(--motion-easing-standard);
```

**Step 5: Scope resize transition suppression**

Replace:

```css
html[data-resizing-panel="true"] * {
  transition: none !important;
  animation: none !important;
}
```

with:

```css
html[data-resizing-panel="true"] .shell,
html[data-resizing-panel="true"] .shell * {
  transition: none !important;
  animation: none !important;
}
```

If a page uses `shell-body` outside `.shell`, include a specific selector rather than universal document scope.

**Step 6: Make comfortable density real**

In `tokens-style.css`, define:

```css
[data-density="comfortable"] {
  --density-panel-padding: var(--space-16);
  --density-section-gap: var(--space-16);
  --density-gutter: var(--space-20);
  --density-strip-height: 2.5rem;
  --density-toolbar-height: 2.5rem;
  --density-row-height: 2.625rem;
  --density-cell-padding-x: var(--space-16);
  --density-cell-padding-y: var(--space-8);
  --density-header-height: 2.25rem;
  --density-input-height: 2.25rem;
  --density-action-height: 2.25rem;
  --density-chart-header: 2.25rem;
  --density-chart-padding: var(--space-16);
  --density-font-delta: 0;
}
```

**Step 7: Replace unsafe innerHTML construction**

In shared JS compare basket code, replace string concatenation with `document.createElement` and `textContent`.

**Step 8: Verify**

Run:

```bash
bun run prototype:interaction
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates
```

Expected: PASS.

**Step 9: Commit**

```bash
git add docs/designs/specs/prototypes/shared docs/designs/specs/prototypes/tokens-style.css docs/designs/specs/prototypes/page-*.html scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): improve interaction performance hygiene"
```

---

### Task 11: Spec Synchronization And Final Review Evidence

**Files:**

- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Modify: `docs/designs/specs/10_ditto_shell_family_spec.md`
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Modify: `docs/designs/specs/12_ditto_data_views_spec.md`
- Modify: `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
- Modify: `docs/designs/specs/20_interaction_ux_audit.md`
- Create: `docs/plans/2026-05-01-prototype-best-review-remediation-results.md`

**Step 1: Update specs from implemented facts**

Make sure the specs contain final contracts for:

- keyboard navigation.
- focus ring.
- motion scale and reduced motion behavior.
- tab ARIA pattern.
- primary answer.
- responsive Shell degradation.
- Catalog subtype differentiation.
- data-viz light/dark scales.
- contrast usage tiers.
- expert efficiency contracts.

**Step 2: Create remediation results document**

Create `docs/plans/2026-05-01-prototype-best-review-remediation-results.md` with:

- original P0/P1 issue list.
- implemented fix.
- files changed.
- test evidence.
- deferred React backlog items.
- remaining risks.

**Step 3: Run full verification**

Run:

```bash
bun run audit:tokens:contrast
bun run build:tokens:check
bun run prototype:interaction
bun run prototype:gates
bun run audit:routes
bun run check
```

Expected:

- contrast audit has 0 operational / data-critical fail.
- tokens export check passes.
- interaction and prototype gates pass.
- route coverage passes.
- full project check passes.

**Step 4: Commit**

```bash
git add docs/designs/specs docs/plans/2026-05-01-prototype-best-review-remediation-results.md
git commit -m "docs(prototypes): record best review remediation results"
```

---

## Execution Notes

- Run tasks in order. Later page work depends on the gates from Task 1.
- Keep commits small. If a task touches more than one concern, split the commit.
- Do not add dependencies.
- Do not change Design Token semantics without approval.
- Prefer shared CSS/JS contracts over page-local patches when the issue appears in 2 or more pages.
- Keep prototype visual language restrained: no new decorative card walls, no gradient ornament, no single-hue theme drift.

## Final Verification Bundle

Run before declaring completion:

```bash
bun run audit:tokens:contrast
bun run build:tokens:check
bun run prototype:interaction
bun run prototype:gates
bun run audit:routes
bun run check
```

Expected final state:

- all commands pass.
- active prototypes remain 27/27 green.
- accessibility and contrast findings from the two 2026-04-30 reviews have documented closure or explicit deferral.
- React-only expert efficiency items are recorded in `docs/plans/prototype-to-react-enhancement-backlog.md`.
