# Prototype UI/UX Audit Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 只修复 `docs/designs/specs/audits/2026-05-03-prototype-uiux-audit.md` 中真实、可验证、对原型体验有实际收益的问题，并把误报校准回审核工具。

**Architecture:** 先校准活跃原型范围和自动化合同，再修复高风险可访问性问题。跨页规则进入 shared CSS 和 prototype contract tests；页面特有问题留在对应 `page-*.html`；需要新增或调整 Design Token 的事项作为审批检查点，不在无批准状态下直接落地。

**Tech Stack:** HTML prototypes, shared prototype CSS/JS, Design Tokens, JSDOM, Vitest, Playwright, Bun, Biome.

---

## Audit Triage

### 采纳为真实且高价值

| Audit item | 结论 | 证据 | 处理优先级 |
|---|---|---|---|
| 活跃原型范围不一致 | 真实问题 | `.edition-manifest.json` 仍是 27 active；审核覆盖 `agent-console-v2`、`alpha-explorer`，且已有单页测试/contract 文件 | P0 |
| Alpha Explorer 键盘可达性缺口 | 真实问题 | `.candidate-card` 6 个、`.queue-item` 3 个均缺少 `tabindex`；样式仅有 hover | P0 |
| Alpha Explorer CVD 状态编码缺口 | 真实问题 | `page-alpha-explorer.html` 的 `.status-pill.*::before` 数为 0；`agent-console-v2` 已有 3 个非颜色编码 | P0 |
| Focus-visible 跨页碎片化 | 真实问题但需收敛表述 | `--interaction-focus-ring` 已存在并被 shared 使用，但页面内仍混用 `brand-accent`、`selected-border`、box-shadow 组合 | P0 |
| Home focus-visible 覆盖不足 | 真实问题但不是“完全无焦点” | Home 页面内只有 `.panel-action:focus-visible`，很多自定义 label/button 依赖浏览器默认 outline 或没有 token ring | P1 |
| Reduced-motion 覆盖不均 | 真实问题 | `signals-inbox` 有 5 个 `@keyframes` 但仅 1 个 guard；`alpha-explorer` 使用通配符压缩所有 transition | P1 |
| Layout property transition | 部分真实 | `height/max-height` 交互动画应优化；数据可视化 `width` 填充动画可保留但必须有 allowlist 和 reduced-motion | P1 |
| 硬编码 motion duration | 真实问题 | `alpha-explorer` 有 `0.12s`，`agent-console-v2` 有多处 `100ms`，多页仍有 `0.3s/0.6s/300ms` | P1 |
| 语义 HTML 与 ARIA polish | 真实但非阻断 | `article/footer/gridcell/dialog/tooltip/sparkline aria-label` 属于可访问性质量补强 | P2 |

### 降级或暂缓

| Audit item | 处理 |
|---|---|
| Gradient/glow 密度 | 先加“用途分类和阈值”审核，不直接删视觉。很多 gradient/glow 是状态或数据可视化，直接降级会损伤信息表达。 |
| Backdrop-filter 层数 | 保留为性能观察项。除非 Playwright 低端模拟或截图证实卡顿/叠层过重，否则不作为本轮主线。 |
| Layout dimension tokenization | 有价值但涉及 Design Token 变更，执行前需要批准。先记录 `--panel-header-height`、`--tab-bar-height`、`--surface-noise-opacity` 候选。 |
| 响应式移动端缺口 | 原型当前以桌面量化工作台为主，已有 1536/1366/1200 断点门禁。本轮只补范围声明，不做移动重构。 |

### 判定为误报或需先修正审核

| Audit item | 校准结果 |
|---|---|
| “旧 agent-console 37 处硬编码颜色”与多页硬编码颜色统计 | 当前 CSS-aware 复核剔除 `url(#id)`、HTML entity 后，未发现这些页面的真实 `#hex/rgba/hsl` 颜色残留。应先修审核脚本，不做 token 迁移。 |
| “Strategy Studio 11 处硬编码颜色” | 复核命中主要来自 `&#10005;` 等 HTML entity，不是颜色。 |
| “Alpha Explorer reduced-motion 是 Performance 问题” | 应归类为 Accessibility/Consistency。它不是性能瓶颈，而是过度全局覆盖造成的可维护性和体验一致性问题。 |

## Scope

Read:

- `docs/designs/specs/audits/2026-05-03-prototype-uiux-audit.md`
- `docs/designs/specs/prototypes/.edition-manifest.json`
- `docs/designs/specs/prototypes/page-alpha-explorer.html`
- `docs/designs/specs/prototypes/page-agent-console-v2.html`
- `docs/designs/specs/prototypes/page-home.html`
- `docs/designs/specs/prototypes/page-signals-inbox.html`
- `docs/designs/specs/prototypes/shared/layout-base.css`
- `docs/designs/specs/prototypes/tokens-style.css`
- `scripts/prototype-interaction-ux-contract.test.ts`
- `scripts/prototype-design-consistency.test.ts`
- `scripts/page-alpha-explorer-prototype.test.ts`
- `scripts/page-agent-console-v2-prototype.test.ts`
- `scripts/run-prototype-gates.ts`

Out of scope:

- React `src/` 实现迁移。
- 新依赖。
- CI/CD 修改。
- 未批准的 Design Token 新增。
- 根据误报进行大面积颜色迁移。

## Definition Of Done

- `bun run check` passes.
- `bun run prototype:interaction` passes.
- `bun test scripts/page-alpha-explorer-prototype.test.ts scripts/page-agent-console-v2-prototype.test.ts` passes.
- `bun run prototype:gates` 覆盖的 active route prototype 数与审核范围一致，或文档明确说明暂未纳入的候选页面。
- 所有 `cursor: pointer` 的核心业务卡片具备键盘路径和可见 focus ring。
- 每个自定义动画都有针对性 `prefers-reduced-motion` fallback。
- 硬编码颜色审核不再把 SVG `url(#id)` 或 HTML entity 当作颜色。

---

### Task 1: Calibrate Active Prototype Scope

**Files:**

- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
- Modify: `scripts/prototype-interaction-ux-contract.test.ts`
- Modify: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/page-alpha-explorer-prototype.test.ts`
- Test: `scripts/page-agent-console-v2-prototype.test.ts`

**Step 1: Decide the active set in code**

Treat `page-alpha-explorer.html` and `page-agent-console-v2.html` as one of:

- active route prototypes, then add them to `.edition-manifest.json` and global prototype gates.
- candidate prototypes, then mark them explicitly outside active route count and keep only targeted page tests.

Recommended: make `alpha-explorer` active because it already has a contract file and page test. Keep `agent-console-v2` as `nextPrototypeRef` until old agent-console replacement is approved.

**Step 2: Add a scope consistency test**

Add a test that fails when page-specific prototype tests exist but the page is neither active nor explicitly marked candidate:

```ts
const explicitlyCandidatePrototypeFiles = new Set(["page-agent-console-v2.html"]);

it("keeps audited prototype pages in manifest scope", () => {
	const testedFiles = ["page-alpha-explorer.html", "page-agent-console-v2.html"];
	const manifestFiles = new Set(activePages().map((page) => page.file));

	const unscoped = testedFiles.filter(
		(file) => !manifestFiles.has(file) && !explicitlyCandidatePrototypeFiles.has(file),
	);

	expect(unscoped).toEqual([]);
});
```

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL until scope is explicit.

**Step 3: Update manifest or candidate allowlist**

If `alpha-explorer` becomes active, add it with `shellFamily: "studio"` and matching landing metadata. Do not switch `agent-console-v2` over the old page in the same task unless product approves the replacement.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/page-alpha-explorer-prototype.test.ts scripts/page-agent-console-v2-prototype.test.ts
```

Expected: PASS.

---

### Task 2: Add Keyboard And Focus Contract Gates

**Files:**

- Modify: `scripts/prototype-interaction-ux-contract.test.ts`
- Modify: `scripts/page-alpha-explorer-prototype.test.ts`
- Read: `docs/designs/specs/prototypes/page-alpha-explorer.html`
- Read: `docs/designs/specs/prototypes/page-home.html`
- Read: `docs/designs/specs/prototypes/shared/layout-base.css`

**Step 1: Write failing tests for pointer-only core controls**

In `scripts/page-alpha-explorer-prototype.test.ts`, assert:

```ts
it("makes alpha candidate and queue cards keyboard reachable", () => {
	const document = loadPage();
	const controls = document.querySelectorAll(".candidate-card, .queue-item");

	expect(controls.length).toBeGreaterThan(0);
	for (const control of controls) {
		expect(control.getAttribute("tabindex")).toBe("0");
		expect(["button", "option"]).toContain(control.getAttribute("role"));
	}
});
```

Run:

```bash
bun test scripts/page-alpha-explorer-prototype.test.ts
```

Expected: FAIL with current cards.

**Step 2: Add a cross-page focus ring contract**

In `scripts/prototype-interaction-ux-contract.test.ts`, assert that active pages do not introduce page-local focus rings using raw `--brand-accent` or `--interaction-selected-*` without `--interaction-focus-ring`, except documented resize separator exceptions.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL on pages with fragmented focus ring definitions.

**Step 3: Add Home explicit focus coverage checks**

For `page-home.html`, require token focus on:

- `.header-utility-btn`
- `.decision-cta`
- `.panel-action`
- `.overlay-btn`
- `.state-empty-cta`
- `.worklist-row[role="row"]` or equivalent selectable worklist controls

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL until Home focus selectors are explicit.

---

### Task 3: Fix Alpha Explorer A11y Gaps

**Files:**

- Modify: `docs/designs/specs/prototypes/page-alpha-explorer.html`
- Test: `scripts/page-alpha-explorer-prototype.test.ts`

**Step 1: Add semantic keyboard affordances**

Update default-view cards:

```html
<article class="candidate-card selected" tabindex="0" role="option" aria-selected="true">
```

For non-selected candidates:

```html
<article class="candidate-card" tabindex="0" role="option" aria-selected="false">
```

For queue items:

```html
<div class="queue-item" tabindex="0" role="button">
```

If queue selection state is later added, use `role="option"` plus `aria-selected` instead of `role="button"`.

**Step 2: Add token-based focus styles**

```css
.candidate-card:focus-visible,
.queue-item:focus-visible,
.node:focus-visible,
.point:focus-visible {
  outline: 2px solid var(--interaction-focus-ring);
  outline-offset: 2px;
}
```

**Step 3: Add non-color status encoding**

Mirror the mature pattern from `agent-console-v2`:

```css
.status-pill.running::before { content: "● "; font-size: var(--font-size-10); }
.status-pill.partial::before { content: "◐ "; font-size: var(--font-size-10); }
.status-pill.blocked::before { content: "✕ "; font-size: var(--font-size-10); }
```

Use token font sizes, not hardcoded `6px/7px/8px`.

Run:

```bash
bun test scripts/page-alpha-explorer-prototype.test.ts
```

Expected: PASS.

---

### Task 4: Normalize Shared Focus Ring Usage

**Files:**

- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: focused page-local selectors in `docs/designs/specs/prototypes/page-*.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add shared utility selectors**

Add a conservative shared baseline for custom controls:

```css
:is(
  .header-utility-btn,
  .header-action-btn,
  .header-btn-badge,
  .decision-cta,
  .panel-action,
  .overlay-btn,
  .state-empty-cta,
  .filter-chip,
  .tab,
  .mode-tab
):focus-visible {
  outline: 2px solid var(--interaction-focus-ring);
  outline-offset: 2px;
}
```

Keep resize separator focus styling separate because it uses a larger hit-area affordance.

**Step 2: Remove page-local conflicting focus rings**

Replace page-local patterns like:

```css
box-shadow: 0 0 0 1.5px var(--brand-accent), 0 0 0 4px var(--interaction-selected-border);
```

with the shared utility or page selector using `--interaction-focus-ring`.

Run:

```bash
bun run prototype:interaction
bun test scripts/prototype-design-consistency.test.ts
```

Expected: PASS.

---

### Task 5: Normalize Reduced Motion And Motion Tokens

**Files:**

- Modify: `docs/designs/specs/prototypes/page-alpha-explorer.html`
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html`
- Modify: `docs/designs/specs/prototypes/page-research.html`
- Modify: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add failing reduced-motion coverage test**

Count `@keyframes` and animation declarations per page, then require a same-page `prefers-reduced-motion` block that references each animated selector or key animation family.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on `signals-inbox` and broad-alpha behavior.

**Step 2: Replace Alpha global wildcard**

Replace:

```css
@media (prefers-reduced-motion: reduce) {
  * {
    transition-duration: 0.01ms !important;
  }
}
```

with targeted selectors for ambient or decorative motion. Keep functional hover/focus transitions intact.

**Step 3: Patch Signals Inbox animations**

Add reduced-motion fallbacks for:

- `row-enter`
- `detail-slide-in`
- `spin`
- `dot-pulse`
- `scope-tab-enter`

**Step 4: Replace hardcoded durations**

Use:

- `var(--motion-duration-fast)` instead of `100ms`, `0.12s`, `0.3s`, `300ms`
- `var(--motion-duration-normal)` instead of `0.6s`
- `var(--motion-easing-standard)` instead of raw `ease` or `cubic-bezier(0.4, 0, 0.2, 1)`

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts scripts/page-alpha-explorer-prototype.test.ts scripts/page-agent-console-v2-prototype.test.ts
```

Expected: PASS.

---

### Task 6: Treat Layout Transitions With An Allowlist

**Files:**

- Modify: `scripts/prototype-design-consistency.test.ts`
- Modify: selected page styles in `docs/designs/specs/prototypes/page-*.html`

**Step 1: Add a layout-transition audit with categories**

Fail on:

- `transition: height`
- `transition: max-height`
- hardcoded layout transition durations

Allow with comment or data class:

- progress/data bars with `transition: width var(--motion-duration-*)`
- chart fills that are disabled in reduced motion
- resizable panel width indicators controlled by shared interaction JS

**Step 2: Replace real layout animation risks**

Prefer `grid-template-rows`, `opacity`, or `transform` for collapsible panels. Keep data bar width transitions where the visual encodes value change.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: PASS.

---

### Task 7: Fix The Hardcoded Color Audit Before Any Color Migration

**Files:**

- Modify: `scripts/audit-tokens.mjs` or create a focused helper under `scripts/`
- Modify: `scripts/prototype-design-consistency.test.ts`
- Read: `docs/designs/specs/prototypes/page-agent-console.html`
- Read: `docs/designs/specs/prototypes/page-strategy-studio.html`

**Step 1: Add scanner exclusions**

The scanner must ignore:

- SVG local references: `url(#chart-gradient)`
- HTML entities: `&#10005;`
- fragment identifiers not inside CSS color declarations

**Step 2: Add regression fixtures**

Test samples:

```ts
expect(findHardcodedColors('fill="url(#dd2-g)"')).toEqual([]);
expect(findHardcodedColors("content: '&#10005;'")).toEqual([]);
expect(findHardcodedColors("color: #fff")).toEqual(["#fff"]);
expect(findHardcodedColors("background: rgba(0,0,0,.2)")).toEqual(["rgba("]);
```

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: PASS and no color migration tasks generated from false positives.

---

### Task 8: Optional Design Token Dimension Pass

**Approval checkpoint:** This task changes Design Token surface area. Ask before implementation.

**Files:**

- Modify: `docs/designs/specs/prototypes/tokens-style.css`
- Modify: `docs/designs/specs/14_ditto_token_naming_layering_spec.md`
- Modify: `docs/designs/specs/15_ditto_token_stabilization_spec.md`
- Modify: `docs/designs/specs/prototypes/page-alpha-explorer.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html`

**Candidate tokens:**

```css
--panel-header-height: 38px;
--tab-bar-height: 42px;
--progress-bar-height: 6px;
--surface-noise-opacity: 0.018;
```

Do not change `--status-bar-height` semantics without checking existing `1.5rem` usage. Replace `var(--status-bar-height, 24px)` fallbacks only after confirming `tokens-style.css` is loaded on every page.

Run:

```bash
bun run build:tokens:check
bun test scripts/prototype-design-consistency.test.ts
```

Expected: PASS.

---

### Task 9: Semantic HTML And ARIA Polish

**Files:**

- Modify: targeted `docs/designs/specs/prototypes/page-*.html`
- Modify: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Add low-risk semantic assertions**

Assert only where role is unambiguous:

- standalone content cards use `<article>` when selected/focused as an object.
- status bar uses `<footer role="status">` only if it is page-level status, not a control strip.
- heatmap matrix cells expose `role="gridcell"` when parent is `role="grid"`.
- sparklines have `aria-label` or `aria-hidden="true"` depending on whether they carry unique information.
- overlay panels have `role="dialog"` and accessible names.

**Step 2: Fix representative pages first**

Start with:

- `page-alpha-explorer.html`
- `page-agent-console-v2.html`
- `page-signals-inbox.html`
- `page-home.html`

Run:

```bash
bun run prototype:interaction
```

Expected: PASS.

---

## Recommended Execution Order

1. Task 1: Scope calibration.
2. Task 2: Failing contract gates.
3. Task 3: Alpha Explorer keyboard and CVD fixes.
4. Task 4: Shared focus normalization.
5. Task 5: Reduced motion and motion token cleanup.
6. Task 6: Layout transition allowlist.
7. Task 7: Hardcoded color audit correction.
8. Task 8: Token dimension pass, only after approval.
9. Task 9: Semantic polish.

## Final Verification

Run:

```bash
bun run check
bun run prototype:interaction
bun test scripts/page-alpha-explorer-prototype.test.ts scripts/page-agent-console-v2-prototype.test.ts
bun run prototype:gates
```

Expected:

- all commands pass.
- active prototype count and audit scope no longer contradict each other.
- no known false positives remain in color hardcode reporting.
