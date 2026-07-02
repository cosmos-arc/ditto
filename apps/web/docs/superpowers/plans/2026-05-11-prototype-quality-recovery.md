# Prototype Quality Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore final-review confidence for every prototype page by fixing the UX risks that lowered the release-grade critique score, while making the scoring and verification pipeline stable enough that future improvements do not look like regressions.

**Architecture:** Treat this as two coupled systems: the evaluation system and the prototype design system. First stabilize the gates and score contract so the team compares like with like, then ship targeted prototype improvements through shared contracts instead of one-off page polish.

**Tech Stack:** Static HTML prototypes, shared CSS modules under `docs/designs/specs/prototypes/shared`, Vitest, Playwright, JSDOM, Bun, Biome.

---

## Why the Score Dropped

The old `9.x` numbers in `.edition-manifest.json` are not the same kind of score as the latest final critique.

- The manifest score mostly measured prototype completeness, token compliance, layout gates, visual pass count, and route coverage.
- The final critique score measured release-grade UX risk: can a trader make a safe decision in 5 seconds, can a high-risk action be reversed or audited, does the interface reduce cognitive load instead of merely displaying more state.
- Recent iterations improved coverage and visual fidelity, but also added more visible controls, overlays, badges, right rails, proof text, animation, and state variants. That raises gate scores while lowering cognitive-load and minimalist-design scores.
- `bun run check` failed because three prototype-heavy tests timed out under full-suite concurrency. Targeted rerun with a higher timeout passed, so this is a verification stability issue, not a known design assertion failure.

Do not try to recover the score by hiding information or deleting useful density. Recover it by making the primary decision stronger, making dangerous actions harder to misread, and moving secondary complexity behind stable progressive disclosure.

## File Structure

Modify these files only in the listed tasks:

- `docs/designs/specs/audits/2026-05-11-prototype-quality-score-contract.md`: new documentation that defines the two score families and prevents future false comparisons.
- `scripts/prototype-design-consistency.test.ts`: stabilize timeout for a known JSDOM-heavy naming test.
- `scripts/prototype-final-review-remediation.test.ts`: stabilize timeout for a known JSDOM-heavy visible text test.
- `scripts/prototype-full-directory-visual-audit.test.ts`: keep all pages in scope, raise the full-directory timeout, and document why.
- `scripts/prototype-high-risk-confirmation-contract.test.ts`: new contract test for high-risk confirmation content.
- `scripts/prototype-primary-answer-contract.test.ts`: new contract test for first-screen decision hierarchy.
- `scripts/prototype-action-tier-contract.test.ts`: new contract test for visible action tiering and action-count caps.
- `docs/designs/specs/prototypes/shared/layout-components.css`: shared classes for high-risk confirmation, primary answer hierarchy, action tiering, and reduced visual noise.
- `docs/designs/specs/prototypes/page-home.html`: harden order confirmation and reduce primary decision competition.
- `docs/designs/specs/prototypes/page-trading-overview.html`: harden pause trading and order/signals path.
- `docs/designs/specs/prototypes/page-risk-center.html`: harden stress test and rule editor confirmations.
- `docs/designs/specs/prototypes/page-agent-console-v2.html`: harden Agent approval and rerun confirmations.
- `docs/designs/specs/prototypes/page-backtest-result.html`: harden enable-signal confirmation.
- `docs/designs/specs/prototypes/page-signals-inbox.html`: harden signal adoption/rejection.
- `docs/designs/specs/prototypes/page-orders-ledger.html`: harden cancel/retry order actions.
- `docs/designs/specs/prototypes/page-strategy-list.html`: harden bulk delete and strategy deletion.
- `docs/designs/specs/prototypes/page-platform-settings.html`: harden settings reset and credential changes.
- `docs/designs/specs/prototypes/page-universe-list.html`: harden universe deletion.
- `docs/designs/specs/prototypes/page-markets-screener.html`: reduce action noise on the densest page.
- `docs/designs/specs/prototypes/page-strategy-studio.html`: reduce action noise and make the submit-backtest decision dominant.
- `docs/designs/specs/prototypes/page-a-shares.html`: reduce competing visual emphasis in market overview.
- `docs/designs/specs/prototypes/page-cross-market.html`: reduce competing visual emphasis in macro/radar view.
- `docs/designs/specs/prototypes/page-instrument-hub.html`: reduce overlay/action clutter in object hub.
- `docs/designs/specs/prototypes/page-portfolio.html`: reduce right-rail and chart decoration noise.
- `docs/designs/specs/prototypes/page-research.html`: replace placeholder-looking chart labels with production-grade static chart names.
- `docs/designs/specs/prototypes/.edition-manifest.json`: update notes only after gates pass, do not inflate numeric scores manually.

Do not edit archived specimens under `docs/designs/specs/prototypes/archive/2026-04-30/` for release scoring. They remain historical references.

---

### Task 1: Stabilize The Scoring Contract

**Files:**
- Create: `docs/designs/specs/audits/2026-05-11-prototype-quality-score-contract.md`
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`

- [ ] **Step 1: Write the score contract document**

Create `docs/designs/specs/audits/2026-05-11-prototype-quality-score-contract.md` with this exact content:

```markdown
# Prototype Quality Score Contract

## Purpose

This document prevents false regressions caused by comparing different score families.

## Score Families

### Gate Score

Gate score answers: does the prototype satisfy implementation readiness gates?

Inputs:

- token usage
- viewport gates at 1536, 1366, and 1200 px
- route coverage
- overlay coverage
- state coverage
- visual consistency tests
- runtime errors

Gate score can improve when a page has more states, overlays, contract slots, and verification coverage.

### Release UX Score

Release UX score answers: would a professional quant trader trust this interface for real work?

Inputs:

- five-second state comprehension
- high-risk action safety
- cognitive load
- primary decision clarity
- recovery and auditability
- keyboard and assistive technology confidence
- long-session visual fatigue

Release UX score can drop when a page adds more visible options, more proof text, more panels, more motion, or more competing status indicators.

## Current Baseline

As of 2026-05-11:

- Active route prototype gates: pass for all active routes.
- Static browser sweep: pass for all prototype HTML pages.
- Fast impeccable detector: 0 findings for every HTML page.
- Release UX critique: 23/40, acceptable but not release-grade.
- Main release blockers: high-risk confirmations, primary answer dilution, visible action overload, visual noise, component semantics.

## Rule

Do not raise manifest numeric scores after cosmetic changes. Raise release confidence only after:

1. high-risk confirmation contract passes,
2. primary answer contract passes,
3. action tier contract passes,
4. `bun run prototype:gates` passes,
5. targeted final-review tests pass,
6. `bun run check` passes.
```

- [ ] **Step 2: Update manifest with a non-numeric note**

In `docs/designs/specs/prototypes/.edition-manifest.json`, add this top-level field after `freezePolish`:

```json
"releaseUxReview": {
  "reviewedAt": "2026-05-11",
  "status": "requires-remediation",
  "scoreFamily": "release-ux",
  "score": "23/40",
  "note": "Gate score and release UX score are separate. Do not compare manifest near-10 scores with release UX heuristic score."
}
```

Keep JSON valid by adding a comma after the previous object.

- [ ] **Step 3: Verify JSON parses**

Run:

```bash
node -e "JSON.parse(require('node:fs').readFileSync('docs/designs/specs/prototypes/.edition-manifest.json','utf8')); console.log('manifest ok')"
```

Expected:

```text
manifest ok
```

- [ ] **Step 4: Commit**

```bash
git add docs/designs/specs/audits/2026-05-11-prototype-quality-score-contract.md docs/designs/specs/prototypes/.edition-manifest.json
git commit -m "docs: define prototype quality score contract"
```

---

### Task 2: Make Prototype Verification Stable Under Full Check

**Files:**
- Modify: `scripts/prototype-design-consistency.test.ts`
- Modify: `scripts/prototype-final-review-remediation.test.ts`
- Modify: `scripts/prototype-full-directory-visual-audit.test.ts`

- [ ] **Step 1: Update the icon-only trigger test timeout**

In `scripts/prototype-design-consistency.test.ts`, replace the current test:

```ts
it("keeps icon-only overlay triggers explicitly named beyond title attributes", () => {
```

with:

```ts
it("keeps icon-only overlay triggers explicitly named beyond title attributes", () => {
```

Then replace the closing test call:

```ts
	expect(violations).toEqual([]);
});
```

for that test only with:

```ts
	expect(violations).toEqual([]);
}, 20_000);
```

- [ ] **Step 2: Update the visible `占位` test timeout**

In `scripts/prototype-final-review-remediation.test.ts`, replace the closing test call for `does not ship visible text or aria labels containing 占位 in active route prototypes`:

```ts
	expect(failures).toEqual([]);
});
```

with:

```ts
	expect(failures).toEqual([]);
}, 20_000);
```

- [ ] **Step 3: Increase the full-directory visual audit budget**

In `scripts/prototype-full-directory-visual-audit.test.ts`, replace:

```ts
const auditTimeoutMs = 90_000;
```

with:

```ts
const auditTimeoutMs = 180_000;
```

Add this comment directly above it:

```ts
// This test intentionally scans every prototype HTML file across three desktop review widths.
// Under the full Vitest suite it shares CPU with other Playwright and JSDOM tests, so the
// timeout must cover worst-case full-suite scheduling, not only isolated execution time.
```

- [ ] **Step 4: Run the three stabilized tests**

Run:

```bash
bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts --testTimeout=180000 --hookTimeout=180000
```

Expected:

```text
Test Files  3 passed (3)
Tests  115 passed (115)
```

- [ ] **Step 5: Run full check**

Run:

```bash
bun run check
```

Expected:

```text
biome check . && tsc -b && vitest run
Test Files  147 passed
Tests  1794 passed
```

- [ ] **Step 6: Commit**

```bash
git add scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts
git commit -m "test: stabilize full prototype verification"
```

---

### Task 3: Add A High-Risk Confirmation Contract

**Files:**
- Create: `scripts/prototype-high-risk-confirmation-contract.test.ts`
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css`

- [ ] **Step 1: Write the failing high-risk confirmation test**

Create `scripts/prototype-high-risk-confirmation-contract.test.ts`:

```ts
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");

const highRiskPages = [
	"page-home.html",
	"page-trading-overview.html",
	"page-risk-center.html",
	"page-agent-console-v2.html",
	"page-backtest-result.html",
	"page-signals-inbox.html",
	"page-orders-ledger.html",
	"page-strategy-list.html",
	"page-platform-settings.html",
	"page-universe-list.html",
] as const;

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

function overlayName(element: Element): string {
	return element.getAttribute("aria-label") ?? element.id ?? element.textContent?.replace(/\s+/g, " ").trim().slice(0, 80) ?? "unknown";
}

describe("prototype high-risk confirmation contract", () => {
	it("keeps every declared high-risk confirmation auditable and recoverable", () => {
		const failures: string[] = [];

		for (const file of highRiskPages) {
			const document = loadDocument(file);
			const confirmations = [...document.querySelectorAll<HTMLElement>("[data-high-risk-confirmation]")];

			if (confirmations.length === 0) {
				failures.push(`${file}: missing [data-high-risk-confirmation]`);
				continue;
			}

			for (const confirmation of confirmations) {
				const name = overlayName(confirmation);
				const requiredSelectors = [
					"[data-impact-summary]",
					"[data-before-after]",
					"[data-evidence-chain]",
					"[data-audit-record]",
					"[data-recovery-path]",
					"[data-cancel-control]",
					"[data-confirm-control]",
				];

				for (const selector of requiredSelectors) {
					if (!confirmation.querySelector(selector)) {
						failures.push(`${file}:${name}: missing ${selector}`);
					}
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("does not leave superseded root Agent Console in active high-risk scope", () => {
		const rootFiles = readdirSync(prototypesDir).filter((file) => /^page-.*\.html$/.test(file));
		const failures = rootFiles.filter((file) => file === "page-agent-console.html");

		expect(failures).toEqual(["page-agent-console.html"]);
	});
});
```

The second test intentionally documents the current superseded file. It should pass with the exact array above until the old file is moved out of the root directory in a separate cleanup.

- [ ] **Step 2: Run the test to verify it fails on missing confirmation details**

Run:

```bash
bunx vitest run scripts/prototype-high-risk-confirmation-contract.test.ts
```

Expected:

```text
FAIL  scripts/prototype-high-risk-confirmation-contract.test.ts
missing [data-high-risk-confirmation]
missing [data-impact-summary]
missing [data-before-after]
missing [data-evidence-chain]
missing [data-audit-record]
missing [data-recovery-path]
```

- [ ] **Step 3: Add shared confirmation classes**

Append this to `docs/designs/specs/prototypes/shared/layout-components.css`:

```css
/* Final-review high-risk confirmation contract */
.risk-confirmation-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(12rem, 0.7fr);
  gap: var(--space-10);
}

.risk-confirmation-block {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-6);
  background: color-mix(in oklch, var(--risk-critical-fg) 4%, var(--surface-panel-base));
  padding: var(--space-8);
}

.risk-confirmation-title {
  font-size: var(--font-size-12);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.risk-confirmation-copy {
  margin-top: var(--space-4);
  color: var(--text-secondary);
  font-size: var(--font-size-12);
  line-height: var(--line-height-compact);
}

.risk-confirmation-list {
  display: grid;
  gap: var(--space-4);
  margin-top: var(--space-6);
}

.risk-confirmation-item {
  display: flex;
  justify-content: space-between;
  gap: var(--space-8);
  color: var(--text-secondary);
  font-size: var(--font-size-12);
}

.risk-confirmation-value {
  color: var(--text-primary);
  font-family: var(--font-family-numeric);
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 4: Run Biome on the CSS and test file**

Run:

```bash
bunx biome check scripts/prototype-high-risk-confirmation-contract.test.ts docs/designs/specs/prototypes/shared/layout-components.css
```

Expected:

```text
No fixes applied.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/prototype-high-risk-confirmation-contract.test.ts docs/designs/specs/prototypes/shared/layout-components.css
git commit -m "test: require auditable high-risk confirmations"
```

---

### Task 4: Harden The Highest-Risk Confirmation Overlays

**Files:**
- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-risk-center.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html`
- Modify: `docs/designs/specs/prototypes/page-backtest-result.html`

- [ ] **Step 1: Replace Home order confirmation body with the contract structure**

In `page-home.html`, locate `aria-label="确认订单"` and make the dialog surface include `data-high-risk-confirmation`.

Use this body structure inside that dialog:

```html
<div class="overlay-body">
  <div class="risk-confirmation-grid">
    <div class="risk-confirmation-block" data-impact-summary>
      <div class="risk-confirmation-title">影响范围</div>
      <p class="risk-confirmation-copy">确认后将提交 600519 贵州茅台卖出市价单 200 股。订单进入券商通道后不可在 Ditto 内直接撤销，只能走订单撤单流程。</p>
    </div>
    <div class="risk-confirmation-block" data-before-after>
      <div class="risk-confirmation-title">交易前后</div>
      <div class="risk-confirmation-list">
        <div class="risk-confirmation-item"><span>持仓</span><span class="risk-confirmation-value">200 股 → 0 股</span></div>
        <div class="risk-confirmation-item"><span>集中度</span><span class="risk-confirmation-value">37.2% → 34.8%</span></div>
        <div class="risk-confirmation-item"><span>预计冲击成本</span><span class="risk-confirmation-value">¥5.9K</span></div>
      </div>
    </div>
    <div class="risk-confirmation-block" data-evidence-chain>
      <div class="risk-confirmation-title">证据链</div>
      <p class="risk-confirmation-copy">Alpha v3 卖出信号 87%，RSI 背离与放量确认，风险预算从 27% 回落至 21%。</p>
    </div>
    <div class="risk-confirmation-block" data-audit-record>
      <div class="risk-confirmation-title">审计记录</div>
      <p class="risk-confirmation-copy">将记录操作者、信号来源、订单参数、风险校验快照和确认时间。</p>
    </div>
    <div class="risk-confirmation-block" data-recovery-path>
      <div class="risk-confirmation-title">恢复路径</div>
      <p class="risk-confirmation-copy">提交后可在订单台账查看状态；未成交部分可从 Orders Ledger 发起撤单。</p>
    </div>
  </div>
  <div class="overlay-actions">
    <label for="overlay-order-confirm" class="overlay-btn overlay-btn-secondary cursor-pointer" data-cancel-control>取消，返回复核</label>
    <label for="overlay-order-confirm" class="overlay-btn overlay-btn-danger cursor-pointer" data-confirm-control data-danger-action>确认提交订单</label>
  </div>
</div>
```

- [ ] **Step 2: Harden Trading pause confirmation**

In `page-trading-overview.html`, locate `aria-label="暂停交易确认"` and ensure the dialog body contains:

```html
<div class="risk-confirmation-grid">
  <div class="risk-confirmation-block" data-impact-summary>
    <div class="risk-confirmation-title">影响范围</div>
    <p class="risk-confirmation-copy">暂停后阻止所有新订单提交，已提交订单继续接收券商回报。当前 3 笔待成交订单不自动撤销。</p>
  </div>
  <div class="risk-confirmation-block" data-before-after>
    <div class="risk-confirmation-title">交易前后</div>
    <div class="risk-confirmation-list">
      <div class="risk-confirmation-item"><span>新订单</span><span class="risk-confirmation-value">允许 → 阻止</span></div>
      <div class="risk-confirmation-item"><span>待成交</span><span class="risk-confirmation-value">3 笔保持</span></div>
      <div class="risk-confirmation-item"><span>恢复方式</span><span class="risk-confirmation-value">手动恢复</span></div>
    </div>
  </div>
  <div class="risk-confirmation-block" data-evidence-chain>
    <div class="risk-confirmation-title">触发证据</div>
    <p class="risk-confirmation-copy">风险预算 52.9%，券商连接正常，暂停原因将写入交易审计流。</p>
  </div>
  <div class="risk-confirmation-block" data-audit-record>
    <div class="risk-confirmation-title">审计记录</div>
    <p class="risk-confirmation-copy">记录操作者、账户、交易模式、待成交订单数和暂停时间。</p>
  </div>
  <div class="risk-confirmation-block" data-recovery-path>
    <div class="risk-confirmation-title">恢复路径</div>
    <p class="risk-confirmation-copy">从交易上下文栏恢复交易；恢复前仍需重新确认风险预算。</p>
  </div>
</div>
```

Keep existing cancel and danger buttons, but add `data-cancel-control` to the cancel label and `data-confirm-control` to the confirm label.

- [ ] **Step 3: Harden Risk stress test and rule editor**

In `page-risk-center.html`, add `data-high-risk-confirmation` to both `aria-label="压力测试配置"` and `aria-label="规则编辑"` dialog surfaces.

For stress test, include:

```html
<div class="risk-confirmation-block" data-impact-summary>
  <div class="risk-confirmation-title">影响范围</div>
  <p class="risk-confirmation-copy">运行压力测试会生成新的风险快照，不会改变实盘订单或风险阈值。</p>
</div>
<div class="risk-confirmation-block" data-before-after>
  <div class="risk-confirmation-title">测试前后</div>
  <p class="risk-confirmation-copy">当前场景为标准风控，测试后新增一条压力测试记录并刷新 Breaches 面板。</p>
</div>
<div class="risk-confirmation-block" data-evidence-chain>
  <div class="risk-confirmation-title">输入证据</div>
  <p class="risk-confirmation-copy">组合、场景、VaR、最大回撤和行业集中度使用当前风险快照。</p>
</div>
<div class="risk-confirmation-block" data-audit-record>
  <div class="risk-confirmation-title">审计记录</div>
  <p class="risk-confirmation-copy">记录测试参数、操作者、运行时间和结果摘要。</p>
</div>
<div class="risk-confirmation-block" data-recovery-path>
  <div class="risk-confirmation-title">恢复路径</div>
  <p class="risk-confirmation-copy">测试记录可归档，规则和交易状态不受影响。</p>
</div>
```

For rule editor, use the same selectors but copy:

```html
<div class="risk-confirmation-block" data-impact-summary>
  <div class="risk-confirmation-title">影响范围</div>
  <p class="risk-confirmation-copy">保存后会改变后续风险告警阈值，不会回写历史事件。</p>
</div>
<div class="risk-confirmation-block" data-before-after>
  <div class="risk-confirmation-title">规则前后</div>
  <p class="risk-confirmation-copy">行业集中度阈值 40% → 新阈值；所有新告警按新规则计算。</p>
</div>
<div class="risk-confirmation-block" data-evidence-chain>
  <div class="risk-confirmation-title">证据链</div>
  <p class="risk-confirmation-copy">最近 6 次压力测试和当前行业暴露用于解释本次调整。</p>
</div>
<div class="risk-confirmation-block" data-audit-record>
  <div class="risk-confirmation-title">审计记录</div>
  <p class="risk-confirmation-copy">记录旧阈值、新阈值、原因、操作者和审批时间。</p>
</div>
<div class="risk-confirmation-block" data-recovery-path>
  <div class="risk-confirmation-title">恢复路径</div>
  <p class="risk-confirmation-copy">可从规则历史恢复上一版阈值，恢复操作同样写入审计。</p>
</div>
```

- [ ] **Step 4: Harden Agent approval**

In `page-agent-console-v2.html`, locate approval confirmation preview and live overlay content for `overlay-approval-confirm`. The approval dialog must include `data-high-risk-confirmation` and the selectors from Task 3.

Use this copy:

```html
<div class="risk-confirmation-block" data-impact-summary>
  <div class="risk-confirmation-title">影响范围</div>
  <p class="risk-confirmation-copy">通过后自动生成信号至待复核队列，不直接下单。信号会绑定候选因子、证据快照和审批人。</p>
</div>
<div class="risk-confirmation-block" data-before-after>
  <div class="risk-confirmation-title">审批前后</div>
  <p class="risk-confirmation-copy">候选发现 → 待复核信号；交易员仍需在 Signals Inbox 二次确认。</p>
</div>
<div class="risk-confirmation-block" data-evidence-chain>
  <div class="risk-confirmation-title">证据链</div>
  <p class="risk-confirmation-copy">IC 0.047、证据 91.2、内部模型来源、工具输出 af-4421。</p>
</div>
<div class="risk-confirmation-block" data-audit-record>
  <div class="risk-confirmation-title">审计记录</div>
  <p class="risk-confirmation-copy">记录审批人、run id、工具调用、模型版本、信号草案和审批时间。</p>
</div>
<div class="risk-confirmation-block" data-recovery-path>
  <div class="risk-confirmation-title">恢复路径</div>
  <p class="risk-confirmation-copy">可在 Signals Inbox 驳回信号，或在 Agent Console 撤回本次产物。</p>
</div>
```

- [ ] **Step 5: Harden Backtest enable-signal confirmation**

In `page-backtest-result.html`, locate `aria-label="确认启用信号"` and add the same contract selectors.

Use this impact copy:

```html
<p class="risk-confirmation-copy">启用后该回测结果可进入 Signals Inbox 作为候选信号来源，不会自动下单。</p>
```

Use this recovery copy:

```html
<p class="risk-confirmation-copy">可从策略详情停用信号源；已生成待复核信号保留审计记录。</p>
```

- [ ] **Step 6: Run high-risk confirmation contract**

Run:

```bash
bunx vitest run scripts/prototype-high-risk-confirmation-contract.test.ts
```

Expected:

```text
PASS  scripts/prototype-high-risk-confirmation-contract.test.ts
```

- [ ] **Step 7: Run active route gates**

Run:

```bash
bun run prototype:gates
```

Expected:

```text
prototype:gates passed for every active route prototype.
```

- [ ] **Step 8: Commit**

```bash
git add docs/designs/specs/prototypes/page-home.html docs/designs/specs/prototypes/page-trading-overview.html docs/designs/specs/prototypes/page-risk-center.html docs/designs/specs/prototypes/page-agent-console-v2.html docs/designs/specs/prototypes/page-backtest-result.html
git commit -m "feat: harden critical prototype confirmations"
```

---

### Task 5: Complete High-Risk Coverage On List And Settings Pages

**Files:**
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`
- Modify: `docs/designs/specs/prototypes/page-orders-ledger.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Modify: `docs/designs/specs/prototypes/page-platform-settings.html`
- Modify: `docs/designs/specs/prototypes/page-universe-list.html`

- [ ] **Step 1: Add the same contract selectors to Signals Inbox**

In `page-signals-inbox.html`, every dialog or sheet that accepts, rejects, or routes a signal must include:

```html
data-high-risk-confirmation
```

and these blocks:

```html
<div data-impact-summary class="risk-confirmation-block">
  <div class="risk-confirmation-title">影响范围</div>
  <p class="risk-confirmation-copy">本次操作只改变信号复核状态，不直接提交订单。</p>
</div>
<div data-before-after class="risk-confirmation-block">
  <div class="risk-confirmation-title">操作前后</div>
  <p class="risk-confirmation-copy">待复核信号 → 已采纳或已驳回；后续订单仍需交易确认。</p>
</div>
<div data-evidence-chain class="risk-confirmation-block">
  <div class="risk-confirmation-title">证据链</div>
  <p class="risk-confirmation-copy">保留信号来源、模型置信度、风控摘要和复核备注。</p>
</div>
<div data-audit-record class="risk-confirmation-block">
  <div class="risk-confirmation-title">审计记录</div>
  <p class="risk-confirmation-copy">记录复核人、动作、信号 id、证据快照和时间。</p>
</div>
<div data-recovery-path class="risk-confirmation-block">
  <div class="risk-confirmation-title">恢复路径</div>
  <p class="risk-confirmation-copy">已采纳信号可在订单前撤回；已驳回信号可从审计历史恢复为待复核。</p>
</div>
```

- [ ] **Step 2: Add the contract to Orders Ledger**

In `page-orders-ledger.html`, harden cancel/retry/order correction overlays with this specific impact copy:

```html
<p class="risk-confirmation-copy">撤单请求提交到券商通道后结果取决于成交状态；已成交部分不可撤回。</p>
```

Use this recovery copy:

```html
<p class="risk-confirmation-copy">撤单结果会回写订单台账；失败时保留原订单状态并提示下一步处理。</p>
```

- [ ] **Step 3: Add the contract to Strategy List**

In `page-strategy-list.html`, harden strategy delete and bulk delete overlays with:

```html
<p class="risk-confirmation-copy">删除会移除策略草稿和本地配置，不删除历史回测、订单、审计记录。</p>
```

and:

```html
<p class="risk-confirmation-copy">可从策略归档恢复最近一次版本；恢复操作会创建新的策略版本。</p>
```

- [ ] **Step 4: Add the contract to Platform Settings**

In `page-platform-settings.html`, harden reset and credential/channel changes with:

```html
<p class="risk-confirmation-copy">保存后会影响数据源、交易通道或 Agent 运行环境，正在运行任务不会自动重启。</p>
```

and:

```html
<p class="risk-confirmation-copy">可从设置变更历史回滚上一版配置；密钥类字段只显示指纹，不回显明文。</p>
```

- [ ] **Step 5: Add the contract to Universe List**

In `page-universe-list.html`, harden universe delete/edit overlays with:

```html
<p class="risk-confirmation-copy">修改股票池会影响引用它的策略、回测和筛选预设，不会自动重跑历史结果。</p>
```

and:

```html
<p class="risk-confirmation-copy">可从股票池版本历史恢复上一版成分；引用策略会收到版本变更提示。</p>
```

- [ ] **Step 6: Verify high-risk coverage**

Run:

```bash
bunx vitest run scripts/prototype-high-risk-confirmation-contract.test.ts
```

Expected:

```text
PASS  scripts/prototype-high-risk-confirmation-contract.test.ts
```

- [ ] **Step 7: Commit**

```bash
git add docs/designs/specs/prototypes/page-signals-inbox.html docs/designs/specs/prototypes/page-orders-ledger.html docs/designs/specs/prototypes/page-strategy-list.html docs/designs/specs/prototypes/page-platform-settings.html docs/designs/specs/prototypes/page-universe-list.html
git commit -m "feat: extend high-risk confirmation coverage"
```

---

### Task 6: Add Primary Answer Hierarchy Contract

**Files:**
- Create: `scripts/prototype-primary-answer-contract.test.ts`
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css`

- [ ] **Step 1: Write the failing contract test**

Create `scripts/prototype-primary-answer-contract.test.ts`:

```ts
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");

const activePrototypeFiles = readdirSync(prototypesDir).filter((file) => /^page-.*\.html$/.test(file) && file !== "page-agent-console.html");

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

describe("prototype primary answer contract", () => {
	it("gives every active route exactly one dominant primary answer region", () => {
		const failures: string[] = [];

		for (const file of activePrototypeFiles) {
			const document = loadDocument(file);
			const primaryRegions = [...document.querySelectorAll("[data-primary-answer-equivalent], [data-primary-answer]")];
			const dominantRegions = primaryRegions.filter((element) => element.getAttribute("data-primary-weight") === "dominant");

			if (dominantRegions.length !== 1) {
				failures.push(`${file}: expected 1 dominant primary answer, got ${dominantRegions.length}`);
			}
		}

		expect(failures).toEqual([]);
	});

	it("marks secondary context regions so visual hierarchy can be audited", () => {
		const failures: string[] = [];

		for (const file of activePrototypeFiles) {
			const document = loadDocument(file);
			const primaryRegions = [...document.querySelectorAll("[data-primary-weight='dominant']")];
			const secondaryRegions = [...document.querySelectorAll("[data-secondary-context]")];

			if (primaryRegions.length === 1 && secondaryRegions.length === 0) {
				failures.push(`${file}: missing [data-secondary-context]`);
			}
		}

		expect(failures).toEqual([]);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
bunx vitest run scripts/prototype-primary-answer-contract.test.ts
```

Expected:

```text
FAIL  scripts/prototype-primary-answer-contract.test.ts
expected 1 dominant primary answer
missing [data-secondary-context]
```

- [ ] **Step 3: Add shared hierarchy classes**

Append to `docs/designs/specs/prototypes/shared/layout-components.css`:

```css
/* Final-review primary answer hierarchy */
[data-primary-weight="dominant"] {
  border-color: color-mix(in oklch, var(--brand-signature-fg) 28%, var(--border-subtle));
  background: color-mix(in oklch, var(--brand-signature-fg) 3%, var(--surface-panel-base));
}

[data-secondary-context] {
  opacity: 0.84;
}

[data-secondary-context] :is(.panel-title, .section-title, .card-title) {
  color: var(--text-secondary);
}

[data-tertiary-context] {
  opacity: 0.72;
}
```

- [ ] **Step 4: Commit**

```bash
git add scripts/prototype-primary-answer-contract.test.ts docs/designs/specs/prototypes/shared/layout-components.css
git commit -m "test: require explicit primary answer hierarchy"
```

---

### Task 7: Apply Primary Answer Hierarchy To Highest-Load Pages

**Files:**
- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-risk-center.html`
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`

- [ ] **Step 1: Mark Home decision card as dominant**

In `page-home.html`, find the main decision card that contains `优先复核贵州茅台卖出信号`. Add:

```html
data-primary-weight="dominant"
```

to that card. Add:

```html
data-secondary-context
```

to the right rail, global warnings, and secondary lists.

- [ ] **Step 2: Mark Trading decision banner as dominant**

In `page-trading-overview.html`, find `.decision-banner`. Add:

```html
data-primary-weight="dominant"
```

Add `data-secondary-context` to the PnL chart panel, positions panel, right risk monitor, and signal queue.

- [ ] **Step 3: Mark Risk top risk strip as dominant**

In `page-risk-center.html`, add `data-primary-weight="dominant"` to the risk strip or top risk summary containing VaR, drawdown, and exposure. Add `data-secondary-context` to chart panels and incident timeline.

- [ ] **Step 4: Mark Screener result path as dominant**

In `page-markets-screener.html`, add `data-primary-weight="dominant"` to the filter execution result block that states matched symbols and destination. Add `data-secondary-context` to comparison basket, multi-factor score, and low-frequency preset controls.

- [ ] **Step 5: Mark Strategy Studio submit-readiness as dominant**

In `page-strategy-studio.html`, add `data-primary-weight="dominant"` to the header/status area that states saved, validation, warnings, and submit-backtest readiness. Add `data-secondary-context` to logs, inspector summary, and optional assistant suggestions.

- [ ] **Step 6: Mark Signals Inbox review queue as dominant**

In `page-signals-inbox.html`, add `data-primary-weight="dominant"` to the current selected signal review row/detail. Add `data-secondary-context` to filters, right rail, and historical feed.

- [ ] **Step 7: Run the contract**

Run:

```bash
bunx vitest run scripts/prototype-primary-answer-contract.test.ts
```

Expected:

```text
PASS  scripts/prototype-primary-answer-contract.test.ts
```

- [ ] **Step 8: Run visual gates**

Run:

```bash
bun run prototype:gates
```

Expected:

```text
prototype:gates passed for every active route prototype.
```

- [ ] **Step 9: Commit**

```bash
git add docs/designs/specs/prototypes/page-home.html docs/designs/specs/prototypes/page-trading-overview.html docs/designs/specs/prototypes/page-risk-center.html docs/designs/specs/prototypes/page-markets-screener.html docs/designs/specs/prototypes/page-strategy-studio.html docs/designs/specs/prototypes/page-signals-inbox.html
git commit -m "feat: clarify primary answer hierarchy"
```

---

### Task 8: Add Action Tier Contract For High-Density Pages

**Files:**
- Create: `scripts/prototype-action-tier-contract.test.ts`
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css`

- [ ] **Step 1: Write the action tier test**

Create `scripts/prototype-action-tier-contract.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");

const highDensityPages = [
	"page-markets-screener.html",
	"page-strategy-studio.html",
	"page-signals-inbox.html",
	"page-strategy-list.html",
	"page-a-shares.html",
	"page-cross-market.html",
	"page-instrument-hub.html",
	"page-orders-ledger.html",
] as const;

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

describe("prototype action tier contract", () => {
	it("marks visible decision actions with an explicit action tier", () => {
		const failures: string[] = [];

		for (const file of highDensityPages) {
			const document = loadDocument(file);
			const actions = [...document.querySelectorAll<HTMLElement>("[data-decision-option], [data-answer-action], .btn-primary, .header-action-btn, .studio-action, .row-action")];

			for (const action of actions) {
				const text = action.textContent?.replace(/\s+/g, " ").trim() || action.getAttribute("aria-label") || "unnamed";
				if (!action.hasAttribute("data-action-tier")) {
					failures.push(`${file}: missing data-action-tier on "${text}"`);
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("keeps primary visible actions capped at three per high-density page", () => {
		const failures: string[] = [];

		for (const file of highDensityPages) {
			const document = loadDocument(file);
			const primaryActions = [...document.querySelectorAll("[data-action-tier='primary']")];

			if (primaryActions.length > 3) {
				failures.push(`${file}: ${primaryActions.length} primary actions`);
			}
		}

		expect(failures).toEqual([]);
	});
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
bunx vitest run scripts/prototype-action-tier-contract.test.ts
```

Expected:

```text
FAIL  scripts/prototype-action-tier-contract.test.ts
missing data-action-tier
```

- [ ] **Step 3: Add shared tier classes**

Append to `docs/designs/specs/prototypes/shared/layout-components.css`:

```css
/* Final-review action tiering */
[data-action-tier="primary"] {
  color: var(--brand-accent-fg);
  background: var(--brand-accent);
  border-color: var(--brand-accent);
}

[data-action-tier="context"] {
  color: var(--text-secondary);
}

[data-action-tier="overflow"] {
  color: var(--text-tertiary);
}

[data-action-tier="command"] {
  color: var(--text-tertiary);
  font-family: var(--font-family-code);
}
```

- [ ] **Step 4: Commit**

```bash
git add scripts/prototype-action-tier-contract.test.ts docs/designs/specs/prototypes/shared/layout-components.css
git commit -m "test: require action tiers on dense prototypes"
```

---

### Task 9: Reduce Action Noise On Dense Pages

**Files:**
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
- Modify: `docs/designs/specs/prototypes/page-cross-market.html`
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html`
- Modify: `docs/designs/specs/prototypes/page-orders-ledger.html`

- [ ] **Step 1: Apply action tiers to Markets Screener**

In `page-markets-screener.html`:

- `执行筛选` gets `data-action-tier="primary"`.
- `加入标的池` gets `data-action-tier="primary"`.
- `开始对比` gets `data-action-tier="primary"`.
- `保存视图`, `重置`, `导出`, row `+ 对比`, and preset actions get `data-action-tier="context"` or `data-action-tier="overflow"`.

- [ ] **Step 2: Apply action tiers to Strategy Studio**

In `page-strategy-studio.html`:

- `提交回测` gets `data-action-tier="primary"`.
- `保存` and `校验` get `data-action-tier="context"`.
- `Dry Run` and `...` get `data-action-tier="overflow"`.
- Header command search keeps `data-action-tier="command"`.

- [ ] **Step 3: Apply action tiers to Signals Inbox**

In `page-signals-inbox.html`:

- Current signal accept/reject/review decision actions get no more than three `data-action-tier="primary"` actions.
- Filter chips and historical actions get `data-action-tier="context"`.
- More-menu or secondary row actions get `data-action-tier="overflow"`.

- [ ] **Step 4: Apply action tiers to Strategy List**

In `page-strategy-list.html`:

- `新建策略` gets `data-action-tier="primary"`.
- `运行回测` in the selected detail panel gets `data-action-tier="primary"`.
- Row details and filters get `data-action-tier="context"`.
- Bulk delete gets `data-action-tier="overflow"` until selected, then the confirmation dialog uses `data-action-tier="primary"` only for final confirmation.

- [ ] **Step 5: Apply tiers to A-Shares and Cross-Market**

In `page-a-shares.html` and `page-cross-market.html`:

- One page-level action gets `data-action-tier="primary"`.
- Filter, AI analysis, pin viewpoint, and detail actions get `data-action-tier="context"`.
- Utility icon actions get `data-action-tier="overflow"` or `data-action-tier="command"`.

- [ ] **Step 6: Apply tiers to Instrument Hub and Orders Ledger**

In `page-instrument-hub.html`:

- Object-level primary action gets `data-action-tier="primary"`.
- Watchlist, send research, news detail, and announcement detail get `data-action-tier="context"`.

In `page-orders-ledger.html`:

- Current order resolution action gets `data-action-tier="primary"`.
- Filters and pagination get `data-action-tier="context"`.
- Retry/cancel dangerous row actions get `data-action-tier="overflow"` until opened in confirmation.

- [ ] **Step 7: Run action tier contract**

Run:

```bash
bunx vitest run scripts/prototype-action-tier-contract.test.ts
```

Expected:

```text
PASS  scripts/prototype-action-tier-contract.test.ts
```

- [ ] **Step 8: Run visual gates**

Run:

```bash
bun run prototype:gates
```

Expected:

```text
prototype:gates passed for every active route prototype.
```

- [ ] **Step 9: Commit**

```bash
git add docs/designs/specs/prototypes/page-markets-screener.html docs/designs/specs/prototypes/page-strategy-studio.html docs/designs/specs/prototypes/page-signals-inbox.html docs/designs/specs/prototypes/page-strategy-list.html docs/designs/specs/prototypes/page-a-shares.html docs/designs/specs/prototypes/page-cross-market.html docs/designs/specs/prototypes/page-instrument-hub.html docs/designs/specs/prototypes/page-orders-ledger.html
git commit -m "feat: tier dense prototype actions"
```

---

### Task 10: Quiet Visual Noise Without Reducing Information Density

**Files:**
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css`
- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-risk-center.html`
- Modify: `docs/designs/specs/prototypes/page-platform.html`
- Modify: `docs/designs/specs/prototypes/page-portfolio.html`
- Modify: `docs/designs/specs/prototypes/page-research.html`

- [ ] **Step 1: Add quieting utilities**

Append to `docs/designs/specs/prototypes/shared/layout-components.css`:

```css
/* Final-review quieting utilities */
.visual-noise-muted {
  opacity: 0.72;
}

.motion-state-only {
  animation-duration: var(--motion-duration-normal);
}

@media (prefers-reduced-motion: reduce) {
  .motion-state-only {
    animation: none !important;
  }
}

.chart-static-frame {
  border: 1px solid var(--border-subtle);
  background: var(--surface-muted);
}
```

- [ ] **Step 2: Remove decorative breathing from Home decision edge**

In `page-home.html`, find `.decision-card::before`.

Replace:

```css
width: 3px;
background: color-mix(in oklch, var(--brand-signature-fg) 62%, transparent);
animation: border-breathe 3s ease-in-out infinite;
```

with:

```css
width: 1px;
background: color-mix(in oklch, var(--brand-signature-fg) 36%, var(--border-subtle));
```

- [ ] **Step 3: Restrict Trading pulse animations to state-only**

In `page-trading-overview.html`, add `motion-state-only` to elements using `dot-pulse`, `dot-critical-pulse`, and `flow-pulse`. Do not animate layout properties.

- [ ] **Step 4: Reduce Risk gradient fills**

In `page-risk-center.html`, keep semantic gradient bars for risk scales only. Replace decorative header title gradient with:

```css
.header-title {
  border-bottom: 1px solid color-mix(in oklch, var(--brand-accent) 28%, var(--border-subtle));
  padding-bottom: 2px;
}
```

- [ ] **Step 5: Reduce Platform and Portfolio decorative chart emphasis**

In `page-platform.html` and `page-portfolio.html`, add `visual-noise-muted` to secondary decorative charts, not to primary status or risk indicators.

- [ ] **Step 6: Rename placeholder-looking chart labels in Research**

In `page-research.html`, replace visible labels that include “placeholder” in class usage only if the visible text looks unfinished.

Use these visible labels:

```html
<span class="chart-placeholder-label">近 60 日 IC 稳定性</span>
<span class="chart-placeholder-label">因子贡献宽度</span>
<span class="chart-placeholder-label">因子相关性热区</span>
```

Keep class names unchanged unless the class itself appears in visible UI. The test already confirms visible `占位` is absent.

- [ ] **Step 7: Run consistency and visual audit tests**

Run:

```bash
bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts --testTimeout=180000 --hookTimeout=180000
```

Expected:

```text
Test Files  3 passed (3)
Tests  115 passed (115)
```

- [ ] **Step 8: Commit**

```bash
git add docs/designs/specs/prototypes/shared/layout-components.css docs/designs/specs/prototypes/page-home.html docs/designs/specs/prototypes/page-trading-overview.html docs/designs/specs/prototypes/page-risk-center.html docs/designs/specs/prototypes/page-platform.html docs/designs/specs/prototypes/page-portfolio.html docs/designs/specs/prototypes/page-research.html
git commit -m "style: quiet prototype visual noise"
```

---

### Task 11: Run Full Per-Page Verification And Record The New Baseline

**Files:**
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
- Create: `docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md`

- [ ] **Step 1: Run active route gates**

Run:

```bash
bun run prototype:gates
```

Expected:

```text
prototype:gates passed for every active route prototype.
```

- [ ] **Step 2: Run high-risk, hierarchy, and action contracts**

Run:

```bash
bunx vitest run scripts/prototype-high-risk-confirmation-contract.test.ts scripts/prototype-primary-answer-contract.test.ts scripts/prototype-action-tier-contract.test.ts
```

Expected:

```text
Test Files  3 passed (3)
```

- [ ] **Step 3: Run final review tests**

Run:

```bash
bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts --testTimeout=180000 --hookTimeout=180000
```

Expected:

```text
Test Files  3 passed (3)
Tests  115 passed (115)
```

- [ ] **Step 4: Run full check**

Run:

```bash
bun run check
```

Expected:

```text
bun run check exits with code 0.
No failed tests, type errors, Biome violations, browser audit timeouts, or unhandled runtime errors are present in the final output.
```

Record the exact final test-file and test counts in the recovery results document created in the next step.

- [ ] **Step 5: Create results document**

Create `docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md`:

```markdown
# Prototype Quality Recovery Results

## Scope

- Active route prototypes: 28
- Root superseded specimens: 1
- Archive specimens: 2
- Token showcase: 1

## Fixed Risks

- High-risk trading and approval confirmations now include impact, before/after, evidence, audit, recovery, cancel, and confirm controls.
- Every active route has one dominant primary answer region.
- Dense pages use explicit action tiers and cap primary actions.
- Decorative visual noise was reduced without lowering information density.

## Verification

- `bun run prototype:gates`: pass
- `bunx vitest run scripts/prototype-high-risk-confirmation-contract.test.ts scripts/prototype-primary-answer-contract.test.ts scripts/prototype-action-tier-contract.test.ts`: pass
- `bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts --testTimeout=180000 --hookTimeout=180000`: pass
- `bun run check`: pass

## Release UX Score Expectation

Expected Nielsen score after remediation: 29 to 32 out of 40.

Remaining non-blockers:

- Some pages remain intentionally desktop-only.
- Superseded `page-agent-console.html` remains in root until archive cleanup.
- Token showcase is not part of route release UX.
```

- [ ] **Step 6: Update manifest release UX status**

In `.edition-manifest.json`, change:

```json
"status": "requires-remediation"
```

to:

```json
"status": "remediated-pending-critique-rerun"
```

Add:

```json
"resultRecord": "docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md"
```

inside `releaseUxReview`.

- [ ] **Step 7: Commit**

```bash
git add docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md docs/designs/specs/prototypes/.edition-manifest.json
git commit -m "docs: record prototype quality recovery results"
```

---

## Self-Review

Spec coverage:

- Explains why the score dropped: Task 1.
- Stabilizes the failing verification pipeline: Task 2.
- Fixes high-risk approval and trading gates: Tasks 3, 4, 5.
- Fixes primary answer dilution: Tasks 6, 7.
- Fixes visible action overload: Tasks 8, 9.
- Fixes visual noise without removing density: Task 10.
- Runs all-page verification and records the result: Task 11.

Placeholder scan:

- No unresolved placeholder language remains in action steps.
- Every code-changing task includes exact files, code snippets, commands, and expected output.

Type consistency:

- Test names, file paths, attributes, and CSS class names are defined before use.
- New data attributes are consistent: `data-high-risk-confirmation`, `data-impact-summary`, `data-before-after`, `data-evidence-chain`, `data-audit-record`, `data-recovery-path`, `data-cancel-control`, `data-confirm-control`, `data-primary-weight`, `data-secondary-context`, `data-action-tier`.
