# Ditto Edition Review Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `2026-04-28-edition-review-analysis.md` 与 `docs/reviews/2026-04-28-prototype-edition-review-ui-ux-pro-max.md` 中仍然有效的审查结论转化为可执行的原型与规范修复计划，优先解决共享 CSS/Token 基线、紧凑视口遮挡、颜色依赖、Command 可发现性、Light mode 审计和危险操作确认链路。

**Architecture:** 先抽象跨页合同和门禁，再落到代表页面，最后扩展到页面家族。共享行为进入 `docs/designs/specs/prototypes/shared/`，页面特殊结构留在单页原型，规范同步写入 `docs/designs/specs/`，测试以原型合同、Playwright 交互和 visual gate 组合验证。

**Tech Stack:** HTML prototypes, shared CSS/JS, Vitest, Playwright, JSDOM, Bun, Biome, Edition Gates.

---

## Scope

本计划只处理 review 报告中无需 PM 决策的系统精修：

- P1：Bottom Tray 三态与遮挡门禁。
- P1：数据可视化非颜色编码。
- P1：Global Command 可发现性。
- P1：Light mode / comfortable density 视觉审计。
- P1/P2：危险动作确认、右栏 sticky 摘要和选中反馈。
- P1/P2：Pro Max 报告中确认仍有效的 CSS/Token/Accessibility 基线问题。
- P2：评分体系与逐页 gate 扩展。

本计划不处理：

- 角色化密度预设。
- Copilot 到 Signals / Strategy Studio 的审批策略细化。
- Agent Finding 生命周期重定义。
- 可转债 T+0 等交易规则扩展。
- 新依赖引入。
- Design Token 语义变更。若实施中必须改 token，需要先同步架构文档并人工确认。

## Integrated Pro Max Findings

`2026-04-28-prototype-edition-review-ui-ux-pro-max.md` 的部分结论来自较早分支状态：它按 29 页统计，而当前 Edition manifest 为 27 个活跃原型；它提到的“多数页面缺 Zone”和“零 reduced-motion”在当前样本中已不完全成立。因此本计划不直接照搬所有数字，而是把建议拆成三类处理。

| 分类 | Pro Max 建议 | 当前处理 |
|---|---|---|
| 立即纳入 | `.filter-select::after` 后存在游离 CSS 声明 | 纳入 Task 0，先写 CSS 结构测试，再修共享 CSS。 |
| 立即纳入 | `layout-base.css` 存在未定义或跨层 token 引用 | 纳入 Task 0，先生成 missing-token 清单；能映射到既有 token 的直接修，语义新增 token 需人工确认。 |
| 立即纳入 | `oklch(from...)` 与 `color-mix()` 混用 | 纳入 Task 0，统一为兼容性更稳的 `color-mix(in oklch, ...)`。 |
| 立即纳入 | title / viewport / skip-link / heading / aria-label / reduced-motion 基线 | 纳入 Task 0，转成 active prototypes 的机器可检查门禁。 |
| 立即纳入 | z-index、line-height、letter-spacing、重复组件样式缺少系统治理 | 纳入 Task 0 和 Task 7，先做审计和低风险收敛；涉及 Design Token 语义新增时暂停确认。 |
| 校验后纳入 | Zone / `data-contract-slot` 覆盖不均 | 当前 27 页已有大量 Zone，需要以 manifest 为准重新扫描；缺口进入 Task 0 / Task 7。 |
| 延后处理 | 全量响应式窄屏重构 | 原型当前固定桌面工作台视口；本轮只加强 1366x768 与 light/density 矩阵，移动/窄屏另立计划。 |
| 已由本计划覆盖 | Light mode 测试不足、Home 状态覆盖不足、Catalog 右栏和危险动作 | 分别进入 Task 4、Task 7、Task 5、Task 6。 |

## Execution Order

1. 先做 Pro Max 基线校准：共享 CSS 结构、Token 引用、CSS 加载顺序、Accessibility、Zone/contract-slot 机器门禁。
2. 再做共享合同：Bottom Tray、Command hint、danger confirmation、non-color data-viz markers。
3. 再做代表页：Strategy Studio、Agent Console、A Shares、Cross Market、Platform Settings、Trading Overview。
4. 再扩展家族页：Catalog、Analytical、Object Hub、Ops Console。
5. 最后更新评分门禁和截图矩阵。

## Definition of Done

- `docs/designs/specs/` 中对应合同已同步。
- 27 个活跃原型仍全部通过 Edition Gates。
- 每个 P1 项都有至少一个失败优先的测试覆盖。
- Pro Max 纳入项均有机器门禁或显式审计清单。
- `bun run check` 通过。
- 新截图产物覆盖 dark / light 与 compact / comfortable 的代表页矩阵。

---

### Task 0: Pro Max Baseline Verification And System Hygiene

**Files:**

- Modify: `docs/designs/specs/13_ditto_component_spec.md`
- Modify: `docs/designs/specs/19_ditto_shell_chrome_contract.md`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-toggles.css`
- Modify: active `docs/designs/specs/prototypes/page-*.html` only where audits fail
- Test: `scripts/prototype-design-consistency.test.ts`
- Create: `docs/plans/2026-04-29-pro-max-findings-triage.md`

**Step 1: Write failing baseline tests**

Extend `prototype-design-consistency.test.ts` with machine-checkable Pro Max gates:

- no orphan declarations immediately after a CSS rule block in `shared/layout-base.css`, covering the `.filter-select::after` case.
- shared CSS token references resolve to either project tokens or documented prototype-local custom properties.
- active pages include `<title>`, viewport meta, skip link, and one visible semantic heading or documented shell title equivalent.
- active pages expose `proto-nav`, `#default-view`, `#states-gallery`, and `#overlays-gallery`.
- interactive `role="button"` elements have `aria-label`, `aria-labelledby`, or meaningful text.
- active prototypes avoid `oklch(from...)` in favor of `color-mix(in oklch, ...)`.
- reduced-motion fallback exists at shared level or page level for pages with animation / reveal / glow behavior.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on current confirmed gaps, including the `.filter-select::after` orphan declarations and remaining `oklch(from...)` usage.

**Step 2: Re-scan Pro Max claims against current manifest**

Create `2026-04-29-pro-max-findings-triage.md` with:

- current active page count from `.edition-manifest.json`.
- confirmed findings.
- outdated findings.
- findings requiring Design Token approval.
- deferred responsive/mobile findings.

Run:

```bash
node -e "const m=require('./docs/designs/specs/prototypes/.edition-manifest.json'); console.log(m.pages.filter(p=>p.status==='reviewed').length)"
rg "oklch\\(from|role=\"button\"|prefers-reduced-motion|proto-nav|data-contract-slot" docs/designs/specs/prototypes
```

Expected: triage document lists current facts, not stale counts.

**Step 3: Fix low-risk shared CSS issues**

In `layout-base.css`:

- move the orphaned `appearance`, `cursor`, and `transition` declarations back into `.filter-select`.
- remove duplicate declarations where the same selector already owns them.
- replace remaining local `oklch(from...)` expressions with `color-mix(in oklch, ...)` where visual semantics are equivalent.

Do not introduce new color values.

**Step 4: Resolve token references conservatively**

For each missing token reference:

- if an equivalent token already exists, remap to it.
- if it is prototype-only shell geometry, define it in the prototype shared scope with a documented prefix.
- if it is a new semantic token, stop and request approval before adding it to the product token SSOT.

Known candidates from the Pro Max report and current scan:

- `--brand-signature-glow`
- `--risk-warning-fg`
- `--shell-rail-radar-width`
- `--space-1`
- `--surface-secondary`

**Step 5: Normalize CSS loading and accessibility baseline**

For active pages:

- enforce token CSS loading order where the page explicitly loads token layers.
- ensure shared CSS order keeps tokens before component/page CSS.
- add missing skip links, title, viewport meta, and heading equivalents.
- add `aria-label` or text labels to `role="button"` controls that currently rely only on icon or visual context.
- add shared `@media (prefers-reduced-motion: reduce)` fallback for reveal / glow / ticker behavior.

**Step 6: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun run check
```

Expected: PASS.

**Step 7: Commit**

```bash
git add docs/plans/2026-04-29-pro-max-findings-triage.md docs/designs/specs/13_ditto_component_spec.md docs/designs/specs/19_ditto_shell_chrome_contract.md docs/designs/specs/prototypes/shared docs/designs/specs/prototypes/page-*.html scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): harden pro max baseline"
```

---

### Task 1: Bottom Tray Contract And Gates

**Files:**

- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Modify: `docs/designs/specs/13_ditto_component_spec.md`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-toggles.css`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console.html`
- Modify: `docs/designs/specs/prototypes/page-platform.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/page-strategy-studio-prototype.test.ts`
- Test: `scripts/page-agent-console-prototype.test.ts`

**Step 1: Write failing contract tests**

Add tests that require every default Bottom Tray to expose:

- `data-bottom-tray`
- `data-bottom-tray-state="collapsed|peek|expanded"`
- a toggle button with `aria-controls`
- a content region with `data-bottom-tray-content`
- compact viewport max height <= 22vh in default state
- main work surface min height >= 420px at 1366x768 where applicable

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts
```

Expected: FAIL on missing `data-bottom-tray` contract.

**Step 2: Document the contract**

In `04_interaction_state_spec.md` and `13_ditto_component_spec.md`, define:

- `collapsed`: only status summary and critical count.
- `peek`: one-row latest status, active error, and expand affordance.
- `expanded`: full logs / validation / dry run output.

In `11_ditto_page_pattern_library.md`, map usage:

- Studio: default `peek`.
- Ops Console: default `collapsed` or `peek` depending on alert level.
- Analytical: avoid tray unless workflow requires it.

**Step 3: Implement shared CSS and semantics**

In shared CSS:

- create `.bottom-tray`, `.bottom-tray-header`, `.bottom-tray-content`, `.bottom-tray-toggle`.
- use stable `minmax()` rows and viewport-bound max heights.
- ensure compact density defaults to `peek`.
- keep tray in document flow, not fixed overlay.

**Step 4: Apply to representative pages**

Update:

- `page-strategy-studio.html`: convert `.studio-logs` into the contract.
- `page-agent-console.html`: align status / logs panel with same contract.
- `page-platform.html`: wrap audit / task log region where it behaves as tray.
- `page-trading-overview.html`: ensure execution/risk status strip cannot cover order workflow.

**Step 5: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-strategy-studio.html --out-dir test-results/edition-gates/strategy-studio
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-agent-console.html --out-dir test-results/edition-gates/agent-console
```

Expected: PASS.

**Step 6: Commit**

```bash
git add docs/designs/specs/04_interaction_state_spec.md docs/designs/specs/11_ditto_page_pattern_library.md docs/designs/specs/13_ditto_component_spec.md docs/designs/specs/prototypes/shared docs/designs/specs/prototypes/page-strategy-studio.html docs/designs/specs/prototypes/page-agent-console.html docs/designs/specs/prototypes/page-platform.html docs/designs/specs/prototypes/page-trading-overview.html scripts/prototype-design-consistency.test.ts scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts
git commit -m "fix(prototypes): add bottom tray contract"
```

---

### Task 2: Non-Color Data Visualization Encoding

**Files:**

- Modify: `docs/designs/specs/12_ditto_data_views_spec.md`
- Modify: `docs/designs/specs/13_ditto_component_spec.md`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
- Modify: `docs/designs/specs/prototypes/page-cross-market.html`
- Modify: `docs/designs/specs/prototypes/page-risk-center.html`
- Modify: `docs/designs/specs/prototypes/page-regime-monitor.html`
- Modify: `docs/designs/specs/prototypes/page-factor-analysis.html`
- Modify: `docs/designs/specs/prototypes/page-backtest-result.html`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Write failing tests**

Add a test that scans active prototypes for heatmaps / matrices / risk charts and requires:

- visible legend container: `data-viz-legend`
- sign marker: `data-viz-sign="positive|negative|neutral"`
- threshold label for risk or heat map cells where applicable
- selected or strong cell affordance not expressed only by background color

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on current pages missing full marker contract.

**Step 2: Update data-view spec**

Document the rule:

- red/green may express market direction, but never be the only signal.
- every diverging chart needs legend + sign + numeric value.
- risk and critical states need icon, label, border or weight in addition to color.

**Step 3: Implement shared marker styles**

Add shared classes:

- `.viz-legend`
- `.viz-sign-marker`
- `.viz-threshold-label`
- `.viz-cell-strong`
- `.viz-cell-selected`

Keep the palette restrained; do not introduce new hue families unless token-approved.

**Step 4: Apply representative pages**

- `page-a-shares.html`: heatmap legend, selected block boundary, arrow/label for涨跌.
- `page-cross-market.html`: correlation matrix positive/negative sign and strong-correlation border.
- `page-risk-center.html`: threshold labels on risk charts.
- `page-regime-monitor.html`: regime legend and non-color regime labels.
- `page-factor-analysis.html`: factor health / IC change markers.
- `page-backtest-result.html`: drawdown and verdict markers.

**Step 5: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-a-shares.html --out-dir test-results/edition-gates/a-shares
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-cross-market.html --out-dir test-results/edition-gates/cross-market
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-risk-center.html --out-dir test-results/edition-gates/risk-center
```

Expected: PASS, with no new color hardcode violations.

**Step 6: Commit**

```bash
git add docs/designs/specs/12_ditto_data_views_spec.md docs/designs/specs/13_ditto_component_spec.md docs/designs/specs/prototypes/shared/layout-base.css docs/designs/specs/prototypes/page-a-shares.html docs/designs/specs/prototypes/page-cross-market.html docs/designs/specs/prototypes/page-risk-center.html docs/designs/specs/prototypes/page-regime-monitor.html docs/designs/specs/prototypes/page-factor-analysis.html docs/designs/specs/prototypes/page-backtest-result.html scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): add non-color data viz encoding"
```

---

### Task 3: Global Command Discoverability

**Files:**

- Modify: `docs/designs/specs/19_ditto_shell_chrome_contract.md`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/theme-switcher.js`
- Modify: all active `docs/designs/specs/prototypes/page-*.html` only if markup lacks required attrs
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-view-preferences.test.ts`

**Step 1: Write failing tests**

Require the global command utility to expose:

- `data-shell-utility="command"`
- `data-command-scope="global"`
- title or aria label containing `Ctrl+K`
- focus-visible affordance
- no loose header search input masquerading as global command

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL if `Ctrl+K` hint or command scope is missing.

**Step 2: Update chrome contract**

In `19_ditto_shell_chrome_contract.md`, state:

- icon-only is default.
- hover/focus reveals `全局命令 Ctrl+K`.
- opened command palette must show scope: global / workspace / current object.

**Step 3: Implement affordance**

Add shared tooltip / focus hint styling in `layout-base.css`.

If JS is needed, keep it in an existing shared script; do not add a dependency.

**Step 4: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/prototype-view-preferences.test.ts
bun run check
```

Expected: PASS.

**Step 5: Commit**

```bash
git add docs/designs/specs/19_ditto_shell_chrome_contract.md docs/designs/specs/prototypes/shared scripts/prototype-design-consistency.test.ts scripts/prototype-view-preferences.test.ts docs/designs/specs/prototypes/page-*.html
git commit -m "fix(prototypes): improve command discoverability"
```

---

### Task 4: Light Mode And Density Visual Audit Matrix

**Files:**

- Create: `scripts/prototype-visual-matrix.ts`
- Modify: `package.json`
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
- Modify: `docs/plans/2026-04-28-edition-review-analysis.md`
- Test: `scripts/prototype-view-preferences.test.ts`

**Step 1: Select representative pages**

Use one page per shell family:

- radar: `page-a-shares.html`
- ops-console: `page-platform-settings.html`
- command-center: `page-home.html`
- catalog: `page-watchlist.html`
- analytical: `page-risk-center.html`
- object-hub: `page-instrument-hub.html`
- studio: `page-strategy-studio.html`

**Step 2: Write screenshot matrix script**

Create `scripts/prototype-visual-matrix.ts` to generate:

- dark + compact
- dark + comfortable
- light + compact
- light + comfortable

Output:

```text
test-results/edition-review/visual-matrix/<page-id>/<theme>-<density>.png
```

Use Playwright already in the repo. Do not add dependencies.

**Step 3: Add package script**

In `package.json`, add:

```json
"prototype:visual-matrix": "bun scripts/prototype-visual-matrix.ts"
```

**Step 4: Extend preference test**

Add assertions that theme and density produce non-zero screenshot surfaces and no menu overlap in the representative pages.

Run:

```bash
bun run prototype:visual-matrix
bun test scripts/prototype-view-preferences.test.ts
```

Expected: screenshots generated and tests pass.

**Step 5: Update review report**

Append a short visual audit section to `2026-04-28-edition-review-analysis.md` that links to the new matrix path and notes any follow-up findings.

**Step 6: Commit**

```bash
git add package.json scripts/prototype-visual-matrix.ts scripts/prototype-view-preferences.test.ts docs/designs/specs/prototypes/.edition-manifest.json docs/plans/2026-04-28-edition-review-analysis.md test-results/edition-review/visual-matrix
git commit -m "test(prototypes): add visual matrix audit"
```

---

### Task 5: Catalog Family Interaction Refinement

**Files:**

- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/page-watchlist.html`
- Modify: `docs/designs/specs/prototypes/page-factor-list.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Modify: `docs/designs/specs/prototypes/page-backtest-list.html`
- Modify: `docs/designs/specs/prototypes/page-experiment-list.html`
- Modify: `docs/designs/specs/prototypes/page-universe-list.html`
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html`
- Modify: `docs/designs/specs/prototypes/page-markets-calendar.html`
- Test: corresponding `scripts/page-*-prototype.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Write family tests**

Require Catalog pages to expose:

- selected row marker beyond background color
- optional `data-batch-action-bar` when checkboxes exist
- right rail sticky summary region: `data-detail-sticky-summary`
- danger action confirmation affordance when delete/destructive actions exist

Run:

```bash
bun test scripts/page-watchlist-prototype.test.ts scripts/page-universe-list-prototype.test.ts scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on missing sticky summary / danger confirmation contract.

**Step 2: Update pattern spec**

Define Catalog right rail order:

```text
summary -> status/risk -> insight/event -> actions
```

For destructive actions:

```text
impact preview -> confirmation -> recovery hint
```

**Step 3: Apply shared styles**

Add:

- `.detail-sticky-summary`
- `.batch-action-bar`
- `.row-selection-marker`
- `.danger-confirmation-summary`

**Step 4: Apply pages**

Priority:

1. `page-universe-list.html`: delete impact preview.
2. `page-watchlist.html`: selected row marker + batch action bar.
3. `page-strategy-list.html`: right rail action position.
4. `page-backtest-list.html`: running / failed progress and recovery hint.
5. `page-experiment-list.html`: p-value / effect explanation.
6. Remaining Catalog pages: align summary and selected affordances.

**Step 5: Verify**

Run:

```bash
bun test scripts/page-watchlist-prototype.test.ts scripts/page-universe-list-prototype.test.ts scripts/page-strategy-list-prototype.test.ts scripts/page-backtest-list-prototype.test.ts scripts/page-experiment-list-prototype.test.ts scripts/page-factor-list-prototype.test.ts scripts/page-markets-screener-prototype.test.ts
bun run check
```

Expected: PASS.

**Step 6: Commit**

```bash
git add docs/designs/specs/11_ditto_page_pattern_library.md docs/designs/specs/prototypes/shared/layout-base.css docs/designs/specs/prototypes/page-watchlist.html docs/designs/specs/prototypes/page-factor-list.html docs/designs/specs/prototypes/page-strategy-list.html docs/designs/specs/prototypes/page-backtest-list.html docs/designs/specs/prototypes/page-experiment-list.html docs/designs/specs/prototypes/page-universe-list.html docs/designs/specs/prototypes/page-markets-screener.html docs/designs/specs/prototypes/page-markets-calendar.html scripts/page-*-prototype.test.ts scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): refine catalog interactions"
```

---

### Task 6: High-Risk Action Confirmation

**Files:**

- Modify: `docs/designs/specs/04_interaction_state_spec.md`
- Modify: `docs/designs/specs/prototypes/page-platform-settings.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-universe-list.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/page-universe-list-prototype.test.ts`
- Test: create or update `scripts/page-platform-settings-prototype.test.ts` if present

**Step 1: Find existing tests**

Run:

```bash
rg "platform-settings|danger|delete|rollback|confirm" scripts docs/designs/specs/prototypes
```

Use existing page-specific test files where present. Create a new one only if no test exists.

**Step 2: Write failing tests**

Require destructive or high-cost actions to include:

- impact summary
- explicit confirm control
- cancel path
- recovery or rollback hint
- non-color danger affordance

**Step 3: Update interaction spec**

Define high-risk action categories:

- trading: submit / cancel / bulk order
- config: save / rollback / diff apply
- catalog: delete universe / delete strategy / bulk delete

**Step 4: Apply representative pages**

- `page-platform-settings.html`: sticky save / validate / rollback with diff preview.
- `page-trading-overview.html`: risk CTA with confirmation and protection copy.
- `page-universe-list.html`: delete impact preview.
- `page-strategy-list.html`: delete strategy confirmation.

**Step 5: Verify**

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/page-universe-list-prototype.test.ts
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-platform-settings.html --out-dir test-results/edition-gates/platform-settings
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-trading-overview.html --out-dir test-results/edition-gates/trading-overview
```

Expected: PASS.

**Step 6: Commit**

```bash
git add docs/designs/specs/04_interaction_state_spec.md docs/designs/specs/prototypes/page-platform-settings.html docs/designs/specs/prototypes/page-trading-overview.html docs/designs/specs/prototypes/page-universe-list.html docs/designs/specs/prototypes/page-strategy-list.html scripts
git commit -m "fix(prototypes): add high-risk action confirmation"
```

---

### Task 7: Expert Efficiency Scoring Calibration

**Files:**

- Modify: `.claude/skills/ditto-design-cycle/review-scoring.md`
- Modify: `.claude/skills/ditto-design-cycle/quality-levels.md`
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console.html`
- Modify: `scripts/prototype-design-consistency.test.ts`
- Create: `scripts/prototype-expert-efficiency.test.ts`
- Test: `scripts/page-home-prototype.test.ts`
- Test: `scripts/page-strategy-studio-prototype.test.ts`
- Test: `scripts/page-agent-console-prototype.test.ts`

**Step 1: Define scoring dimensions**

Add five expert-efficiency checks:

- 5-second task answer is visible.
- selected object drives at least two regions where page pattern expects it.
- compact viewport preserves primary workflow.
- key status is not color-only.
- local search/filter is distinct from global command.

Fold in Pro Max scoring corrections:

- Home must cover `stale` and `selected` states to at least 90% of its declared state model.
- Strategy Studio and Agent Console need stronger `data-contract-slot` coverage for React parity.
- z-index / line-height / letter-spacing hardcodes should count as system hygiene deductions unless documented as intentional micro-adjustments.

**Step 2: Write tests**

Create `prototype-expert-efficiency.test.ts` to enforce machine-checkable parts:

- presence of `data-primary-answer`
- selected row / selected object region marker
- `data-local-search` on table search inputs
- no color-only critical status markers
- Home `states-gallery` includes stale and selected examples.
- Studio / Agent pages expose main, sidebar, activity/log, and status contract slots.

**Step 3: Update manifest scoring**

Do not inflate scores. Add a `reviewNotes` or equivalent non-breaking field only if manifest consumers tolerate it. If not safe, keep scoring notes in docs rather than schema.

**Step 4: Verify**

Run:

```bash
bun test scripts/prototype-expert-efficiency.test.ts scripts/prototype-design-consistency.test.ts scripts/page-home-prototype.test.ts scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts
bun run check
```

Expected: PASS.

**Step 5: Commit**

```bash
git add .claude/skills/ditto-design-cycle/review-scoring.md .claude/skills/ditto-design-cycle/quality-levels.md docs/designs/specs/prototypes/.edition-manifest.json docs/designs/specs/prototypes/page-home.html docs/designs/specs/prototypes/page-strategy-studio.html docs/designs/specs/prototypes/page-agent-console.html scripts/prototype-design-consistency.test.ts scripts/prototype-expert-efficiency.test.ts scripts/page-home-prototype.test.ts scripts/page-strategy-studio-prototype.test.ts scripts/page-agent-console-prototype.test.ts
git commit -m "test(prototypes): calibrate expert efficiency scoring"
```

---

### Task 8: Full Edition Regression

**Files:**

- Modify: `docs/plans/2026-04-28-edition-review-analysis.md`
- Modify: `docs/plans/2026-04-29-pro-max-findings-triage.md`
- Create: `docs/plans/2026-04-29-edition-review-remediation-results.md`
- No production/prototype edits unless failures require fixes.

**Step 1: Run full active prototype gates**

Run the same 27-page loop used in review, writing outputs to:

```text
test-results/edition-gates/<page-id>
```

Expected: 27 pass / 0 blocking / 0 non-blocking.

**Step 2: Regenerate per-page review contact sheets**

Run the existing screenshot generator or script used for:

```text
test-results/edition-review/per-page/*.png
```

Expected: all 27 pages render standard and compact viewports.

**Step 3: Run full project check**

Run:

```bash
bun run check
```

Expected: PASS.

**Step 4: Write results report**

Create `2026-04-29-edition-review-remediation-results.md` with:

- summary of changed pages
- before / after risk table
- Pro Max finding disposition table: fixed / superseded / deferred / requires approval
- remaining P2/P3 items
- verification commands and results

**Step 5: Commit**

```bash
git add docs/plans/2026-04-28-edition-review-analysis.md docs/plans/2026-04-29-pro-max-findings-triage.md docs/plans/2026-04-29-edition-review-remediation-results.md test-results/edition-gates test-results/edition-review
git commit -m "docs(prototypes): summarize edition remediation results"
```

---

## Risk Controls

- Do not change IA or route count while fixing visual/interaction issues.
- Do not add dependencies.
- Do not introduce inline styles.
- Keep shared CSS additions token-based.
- Any Design Token semantic change requires explicit approval and spec sync.
- If a page requires large restructuring, stop and split into a separate page-specific plan.

## Verification Commands

Use these at the end of every task group:

```bash
bun test scripts/prototype-design-consistency.test.ts
bun test scripts/prototype-view-preferences.test.ts
bun run check
```

Use these before final completion:

```bash
bun run check
```

Expected final output:

```text
Test Files  136 passed (136)
Tests       1501 passed (1501)
```

The exact counts may increase when new tests are added; zero failures is mandatory.
