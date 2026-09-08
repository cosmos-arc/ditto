# Prototype Design Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring the active Ditto prototype set back into a single, landing-ready design contract: shell family, overlay registry, gallery structure, typography, color, and manifest status all agree with specs and blueprints.

**Architecture:** Treat 27 active route prototypes as the landing candidate pool, and keep `ai-overview` / `ai-copilot` as archived specimens because IA v2.0 moved AI into a global sidecar and Platform Agent Console. Use page contracts as the machine-readable bridge between blueprints and prototypes, but do not touch React implementation in this plan. Prototype HTML remains the visual source; contracts and manifests describe it accurately.

**Tech Stack:** Bun, Vitest, Playwright, static HTML/CSS prototypes, Ditto page contract JSON, Biome, existing `prototype:gates` tooling.

---

## Execution Rules

- Scope is prototype design only: `prototype/**`, `contracts/pages/**`, design specs, manifest files, prototype tests, and review docs.
- Do not modify `src/features/**`, `src/routes/**`, runtime React components, or API/domain types in this plan.
- Do not add dependencies.
- Do not change design token values unless the step explicitly updates the corresponding spec; prefer documenting the current token truth before changing values.
- Use `bun` commands only.
- Keep `style="..."` attributes at 0 for route prototypes.
- Every task ends with a focused test. Every phase ends with `bun run check`.
- If execution changes `.arch-manifest.json`, confirm scope at execution time because it is a governance artifact.

## Success Criteria

- Active route candidate pool is 27 pages; `ai-overview` and `ai-copilot` are archived specimens, not landing candidates.
- Every active prototype has matching shell family across blueprint, `.edition-manifest.json`, contract JSON, and HTML root shell class.
- Every active prototype overlay id is represented in `contracts/pages/*.contract.json`.
- Every required overlay has a default-view trigger and an overlay-gallery specimen marked with an explicit reference.
- All active pages keep `view-default / view-states / view-overlays` as the only prototype-level zones.
- Overlay classes converge on one grammar: `overlay-backdrop`, `overlay-surface`, `overlay-surface--drawer|sheet|modal|toast`, `overlay-header`, `overlay-body`, `overlay-actions`, `overlay-field`.
- Typography docs agree with current Edition v1 token truth: 9 scale steps, with usage rules for 11 / 18 / 20.
- Negative `letter-spacing` is removed from route prototypes unless a documented exception is added.
- Bare `rgba()` and non-relative `oklch()` are either tokenized or explicitly documented as data-viz local variables.
- `bun run check` passes.

---

## Phase 0: Add Prototype Consistency Guardrails

### Task 0.1: Add Cross-Prototype Consistency Test

**Files:**
- Create: `scripts/prototype-design-consistency.test.ts`

**Step 1: Write the failing test**

Create a Vitest test that reads:

- `.arch-manifest.json`
- `prototype/.edition-manifest.json`
- `contracts/pages/*.contract.json`
- `prototype/page-*.html`

Required assertions:

```ts
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const prototypesDir = join(root, "prototype");
const contractsDir = join(root, "contracts/pages");
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);

function readJson<T>(path: string): T {
	return JSON.parse(readFileSync(path, "utf8")) as T;
}

describe("prototype design consistency", () => {
	it("keeps exactly 27 active route prototypes", () => {
		const manifest = readJson<{
			pages: Array<{ id: string; file: string; status: string }>;
		}>(join(prototypesDir, ".edition-manifest.json"));

		const activePages = manifest.pages.filter(
			(page) =>
				page.file.endsWith(".html") &&
				page.id !== "token-showcase" &&
				!archivedPrototypeIds.has(page.id),
		);

		expect(activePages).toHaveLength(27);
	});

	it("does not mark pages with overlay ids as overlayStatus none", () => {
		const manifest = readJson<{
			pages: Array<{
				id: string;
				file: string;
				landing?: { overlayStatus?: string };
			}>;
		}>(join(prototypesDir, ".edition-manifest.json"));

		const offenders = manifest.pages
			.filter((page) => page.file?.startsWith("page-") && !archivedPrototypeIds.has(page.id))
			.filter((page) => {
				const html = readFileSync(join(prototypesDir, page.file), "utf8");
				return /id="overlay-[^"]+"/.test(html) && page.landing?.overlayStatus === "none";
			})
			.map((page) => page.id);

		expect(offenders).toEqual([]);
	});

	it("registers every active prototype overlay in page contracts", () => {
		const manifest = readJson<{ pages: Array<{ id: string; file: string }> }>(
			join(prototypesDir, ".edition-manifest.json"),
		);

		const contractFiles = readdirSync(contractsDir).filter((file) => file.endsWith(".json"));
		const contractByPrototype = new Map<string, Set<string>>();
		for (const file of contractFiles) {
			const contract = readJson<{
				prototypeRef: string;
				overlays?: Array<{ prototypeSelector: string }>;
			}>(join(contractsDir, file));
			const overlaySelectors = new Set(contract.overlays?.map((overlay) => overlay.prototypeSelector) ?? []);
			contractByPrototype.set(contract.prototypeRef, overlaySelectors);
		}

		const missing: string[] = [];
		for (const page of manifest.pages) {
			if (!page.file?.startsWith("page-") || archivedPrototypeIds.has(page.id)) continue;
			const html = readFileSync(join(prototypesDir, page.file), "utf8");
			const ids = [...new Set([...html.matchAll(/id="(overlay-[^"]+)"/g)].map((match) => match[1]))];
			const selectors = contractByPrototype.get(`prototype/${page.file}`) ?? new Set();
			for (const id of ids) {
				if (!selectors.has(`[data-overlay='${id}']`) && !selectors.has(`[data-overlay="${id}"]`)) {
					missing.push(`${page.id}:${id}`);
				}
			}
		}

		expect(missing).toEqual([]);
	});
});
```

**Step 2: Run the test and confirm it fails**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: FAIL with current shell/overlay registration drift, especially pages that have overlays but `overlayStatus: none`, and overlays absent from contracts.

**Step 3: Keep the failing test**

Do not loosen the assertions. Later tasks make this test pass.

---

## Phase 1: Normalize Candidate Pool And Shell Families

### Task 1.1: Separate Active Route Prototypes From Archived AI Specimens

**Files:**
- Modify: `prototype/.edition-manifest.json`
- Modify: `.arch-manifest.json` only after confirming governance scope at execution time
- Modify: `docs/reviews/2026-04-27-prototype-design-consistency-review.md` if the review needs an addendum

**Step 1: Update AI prototype records**

For `ai-overview` and `ai-copilot` in `.edition-manifest.json`:

- Keep `file`, `score`, and historical review data.
- Set `status` to `archived-specimen`.
- Set `landing.reactRouteStatus` to `deprecated`.
- Set `landing.overlayStatus` to `archived`.
- Set `landing.visualAuditStatus` to `not-applicable`.
- Add a note that these are retained as AI interaction specimens, not route candidates.

**Step 2: Update active count metadata**

If `.arch-manifest.json` is approved for update, add explicit counts:

```json
"prototypeInventory": {
  "activeRoutePrototypeCount": 27,
  "archivedSpecimenCount": 2,
  "auxiliarySpecimenCount": 1,
  "archivedPrototypePages": ["ai-overview", "ai-copilot"],
  "auxiliaryPrototypePages": ["token-showcase"]
}
```

Keep the existing historical `editionPrototypeCount` if it means total HTML prototypes.

**Step 3: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: active route count assertion passes; overlay assertions may still fail.

### Task 1.2: Fix The Three Shell Family Drift Records

**Files:**
- Modify: `prototype/.edition-manifest.json`
- Modify: `contracts/pages/cross-market.contract.json`
- Modify: `contracts/pages/agent-console.contract.json`
- Modify: `contracts/pages/experiment-list.contract.json`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add shell family assertions**

Extend `scripts/prototype-design-consistency.test.ts`:

```ts
const expectedShellFamilies = new Map([
	["cross-market", "radar"],
	["agent-console", "studio"],
	["experiment-list", "catalog"],
]);

it("matches known shell family decisions from blueprints", () => {
	const manifest = readJson<{ pages: Array<{ id: string; shellFamily?: string }> }>(
		join(prototypesDir, ".edition-manifest.json"),
	);

	const contractFiles = readdirSync(contractsDir).filter((file) => file.endsWith(".json"));
	const contractById = new Map(
		contractFiles.map((file) => {
			const contract = readJson<{ id: string; shellFamily: string }>(join(contractsDir, file));
			return [contract.id, contract.shellFamily] as const;
		}),
	);

	for (const [id, shellFamily] of expectedShellFamilies) {
		expect(manifest.pages.find((page) => page.id === id)?.shellFamily).toBe(shellFamily);
		expect(contractById.get(id)).toBe(shellFamily);
	}
});
```

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: FAIL until the three records are corrected.

**Step 2: Correct `/markets` contract**

In `contracts/pages/cross-market.contract.json`:

- Change `shellFamily` to `radar`.
- Keep `pagePattern` as `analytical-overview`.
- Replace old `strip/main/activity/analysis` slots with Radar slots:
  - `context-bar` → `.context-bar`
  - `scope-strip` → `.scope-strip`
  - `main` → `.radar-main`
  - `right-rail` → `.right-rail`
  - `bottom-tab-band` → `.tab-band`

If exact selectors differ, inspect `page-cross-market.html` and use the actual stable selectors. Do not invent selectors.

In `.edition-manifest.json`, set `cross-market.shellFamily` to `radar`.

**Step 3: Correct `/platform/agents` contract**

In `contracts/pages/agent-console.contract.json`:

- Change `shellFamily` to `studio`.
- Change `pagePattern` to `studio-builder`.
- Replace `health/main/detail` ops slots with Studio slots:
  - `header` → `.shell-agent .shell-header`
  - `tabs` → `.shell-agent .agent-tabs`
  - `main` → `[data-contract-slot='main']`
  - `detail` → `[data-contract-slot='detail']`

In `.edition-manifest.json`, set `agent-console.shellFamily` to `studio`.

**Step 4: Correct `/research/experiments` contract**

In `contracts/pages/experiment-list.contract.json`:

- Change `shellFamily` to `catalog`.
- Change `pagePattern` to `catalog-screener`.
- Replace `health/main/detail` ops slots with Catalog slots:
  - `header` → `.filter-toolbar`
  - `main` → `.catalog-table`
  - `detail` → `.catalog-detail`

In `.edition-manifest.json`, set `experiment-list.shellFamily` to `catalog`.

**Step 5: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
bun run check
```

Expected: shell assertions pass; overlay assertions may still fail.

---

## Phase 2: Make Overlay Registry Complete And Machine-Readable

### Task 2.1: Add Explicit Overlay References To Overlay Gallery Cards

**Files:**
- Modify: `prototype/page-*.html` for all active pages with overlays
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add a failing gallery reference test**

Extend the consistency test:

```ts
it("marks overlay gallery specimens with data-overlay-ref", () => {
	const manifest = readJson<{ pages: Array<{ id: string; file: string }> }>(
		join(prototypesDir, ".edition-manifest.json"),
	);

	const missing: string[] = [];
	for (const page of manifest.pages) {
		if (!page.file?.startsWith("page-") || archivedPrototypeIds.has(page.id)) continue;
		const html = readFileSync(join(prototypesDir, page.file), "utf8");
		const overlayIds = [...new Set([...html.matchAll(/id="(overlay-[^"]+)"/g)].map((match) => match[1]))];
		const refs = new Set([...html.matchAll(/data-overlay-ref="([^"]+)"/g)].map((match) => match[1]));
		for (const id of overlayIds) {
			if (!refs.has(id)) missing.push(`${page.id}:${id}`);
		}
	}

	expect(missing).toEqual([]);
});
```

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: FAIL for pages where overlay gallery cards do not explicitly reference the overlay id.

**Step 2: Add `data-overlay-ref`**

For every card in `#overlays-gallery`, add:

```html
<div class="gallery-card" data-overlay-ref="overlay-order-detail">
```

Rules:

- Use the exact CSS checkbox / data-overlay id, for example `overlay-order-detail`.
- Do not add refs to state cards.
- Do not move overlay gallery into the default page.
- Do not remove default-view overlay triggers.

**Step 3: Verify gallery references**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: gallery reference assertion passes.

### Task 2.2: Fill `overlays[]` For All Active Page Contracts

**Files:**
- Modify: all active `contracts/pages/*.contract.json`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Inventory active overlays**

Run:

```bash
node - <<'JS'
const fs = require("node:fs");
const path = require("node:path");
const root = "prototype";
const manifest = JSON.parse(fs.readFileSync(path.join(root, ".edition-manifest.json"), "utf8"));
const archived = new Set(["ai-overview", "ai-copilot"]);
for (const page of manifest.pages) {
  if (!page.file?.startsWith("page-") || archived.has(page.id)) continue;
  const html = fs.readFileSync(path.join(root, page.file), "utf8");
  const ids = [...new Set([...html.matchAll(/id="(overlay-[^"]+)"/g)].map((match) => match[1]))];
  if (ids.length) console.log(`${page.id}\\t${ids.join(",")}`);
}
JS
```

Expected baseline: 27 active pages, 93 active overlay ids.

**Step 2: Add missing contract overlays**

For every overlay id, add a contract entry:

```json
{
  "id": "page.overlay-name",
  "kind": "drawer",
  "blocking": false,
  "requiredInDefaultFlow": true,
  "trigger": {
    "slot": "main",
    "action": "select-row"
  },
  "prototypeSelector": "[data-overlay='overlay-name']",
  "reactComponent": null,
  "closeBehavior": ["escape", "outside-click", "primary-action"]
}
```

Rules:

- `kind` must be one of `drawer`, `sheet`, `modal`, `toast`, `popover`, `command-palette`.
- `modal` only for blocking confirmation or approval.
- `drawer` for details / drill-down / compare.
- `sheet` for configuration or longer forms.
- `toast` for lightweight success/feedback.
- `reactComponent` may stay `null` because this plan is prototype-only.
- `requiredInDefaultFlow` is `true` when the default page has a trigger; otherwise fix the default page trigger rather than hiding the overlay in contract.

**Step 3: Update `overlayStatus`**

In `.edition-manifest.json`:

- `triggerable` for active pages with default-view triggers.
- `none` only for active pages with no overlay ids.
- `archived` only for archived specimens.

Given the current active inventory, expect nearly all active pages with overlay ids to become `triggerable`.

**Step 4: Verify registry completeness**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
bun run generate-contracts
git diff --exit-code src/features/shell/page-contracts.generated.ts scripts/visual-audit.config.generated.mjs
```

Expected:

- Consistency test passes overlay registry assertions.
- Generator is either idempotent or produces only expected generated artifact drift.
- If generated files change, stop and inspect before continuing.

---

## Phase 3: Unify Overlay And Gallery Grammar

### Task 3.1: Add Shared Overlay Surface Grammar

**Files:**
- Modify: `prototype/shared/prototype-toggles.css`
- Modify: active `prototype/page-*.html`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add class grammar test**

Extend consistency test:

```ts
it("does not introduce legacy overlay surface class names in active prototypes", () => {
	const manifest = readJson<{ pages: Array<{ id: string; file: string }> }>(
		join(prototypesDir, ".edition-manifest.json"),
	);

	const legacyHits: string[] = [];
	for (const page of manifest.pages) {
		if (!page.file?.startsWith("page-") || archivedPrototypeIds.has(page.id)) continue;
		const html = readFileSync(join(prototypesDir, page.file), "utf8");
		for (const legacy of ["drawer-sheet", "modal-sheet", "overlay-sheet", "overlay-drawer"]) {
			if (html.includes(legacy)) legacyHits.push(`${page.id}:${legacy}`);
		}
	}

	expect(legacyHits).toEqual([]);
});
```

Expected: FAIL before class migration.

**Step 2: Add shared classes**

In `shared/prototype-toggles.css`, add shared overlay grammar:

```css
.overlay-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 100;
  background: var(--surface-overlay);
}

.overlay-surface {
  border: 1px solid var(--border-default);
  background: var(--surface-modal);
  color: var(--text-secondary);
}

.overlay-surface--drawer {
  margin-left: auto;
  width: var(--shell-drawer-width);
  height: 100%;
}

.overlay-surface--sheet {
  width: min(520px, calc(100vw - var(--space-32)));
  max-height: calc(100vh - var(--space-32));
}

.overlay-surface--modal {
  width: min(440px, calc(100vw - var(--space-32)));
  max-height: calc(100vh - var(--space-32));
}
```

Use existing local visual details where needed, but route them through the shared class names.

**Step 3: Replace page-local surface classes**

For each active page:

- Replace `overlay-sheet` with `overlay-surface overlay-surface--sheet` or `overlay-surface overlay-surface--modal` depending on contract `kind`.
- Replace `overlay-drawer` / `drawer-sheet` with `overlay-surface overlay-surface--drawer`.
- Replace `modal-sheet` with `overlay-surface overlay-surface--modal`.
- Keep page-specific content classes only for content layout, not for overlay shell identity.

**Step 4: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
bun run test:run scripts/page-*-prototype.test.ts
```

Expected: class grammar test passes, and page prototype tests remain green.

### Task 3.2: Keep Gallery Zones Strictly Separated

**Files:**
- Modify: `prototype/shared/prototype-toggles.css`
- Modify: active page prototypes only if tests find violations
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add zone discipline tests**

Assertions:

- Every active page has exactly one `#default-view`, `#states-gallery`, `#overlays-gallery`.
- `#states-gallery` has no `.overlay-surface`.
- `#overlays-gallery` has no product `data-contract-slot`.
- `#default-view` has no `.gallery-card`.

**Step 2: Fix violations**

If a page mixes gallery content into default view:

- Move specimen markup to `#overlays-gallery`.
- Keep only trigger labels/buttons and hidden overlay shells in `#default-view`.

**Step 3: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: all zone discipline tests pass.

---

## Phase 4: Align Typography, Color, And Token Governance

### Task 4.1: Make 9-Step Typography The Documented Edition v1 Truth

**Files:**
- Modify: `design/specs/15_ditto_token_stabilization_spec.md`
- Modify: `design/specs/14_ditto_token_naming_layering_spec.md` only if it contradicts the 9-step truth
- Modify: `DESIGN.md` only if clarification is needed
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add doc consistency assertion**

Add a test that checks `15_ditto_token_stabilization_spec.md` no longer says 11 / 18 / 20 are deprecated for Edition v1.

**Step 2: Update typography section**

Document the current 9-step scale:

| Token | Role |
|---|---|
| `--font-size-10` | tiny labels, metadata |
| `--font-size-11` | tight contexts only |
| `--font-size-12` | compact body, table cells, buttons |
| `--font-size-13` | standard body |
| `--font-size-14` | section heading |
| `--font-size-16` | page / panel emphasis |
| `--font-size-18` | object subheading, rare |
| `--font-size-20` | key metric / object title, rare |
| `--font-size-24` | page title / specimen title |

Remove language that says 11 / 18 / 20 are forbidden in current Edition v1. If the team still wants a 6-step future target, mark it as future simplification, not current gate.

**Step 3: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: doc consistency assertion passes.

### Task 4.2: Remove Negative Letter Spacing From Active Prototypes

**Files:**
- Modify active `prototype/page-*.html`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add failing test**

```ts
it("keeps active route prototypes free of negative letter spacing", () => {
	const manifest = readJson<{ pages: Array<{ id: string; file: string }> }>(
		join(prototypesDir, ".edition-manifest.json"),
	);

	const hits: string[] = [];
	for (const page of manifest.pages) {
		if (!page.file?.startsWith("page-") || archivedPrototypeIds.has(page.id)) continue;
		const html = readFileSync(join(prototypesDir, page.file), "utf8");
		if (/letter-spacing\s*:\s*-/.test(html)) hits.push(page.id);
	}

	expect(hits).toEqual([]);
});
```

Expected: FAIL with current pages.

**Step 2: Replace negative letter spacing**

For each active page:

- Replace `letter-spacing: -0.01em`, `-0.02em`, `-0.03em` with `letter-spacing: 0`.
- If a number appears too wide after the change, keep `font-variant-numeric: tabular-nums slashed-zero` or `font-feature-settings: "tnum" 1`.
- Do not reduce font size as a workaround unless the spec role calls for it.

**Step 3: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
bun run test:run scripts/page-*-prototype.test.ts
```

Expected: no negative letter spacing, no screenshot/layout regressions in prototype tests.

### Task 4.3: Tokenize Bare `rgba()` And Non-Relative `oklch()`

**Files:**
- Modify: `prototype/page-portfolio.html`
- Modify: `prototype/page-platform-settings.html`
- Modify: `prototype/page-a-shares.html`
- Modify: `prototype/page-agent-console.html`
- Modify other active pages only if the audit test identifies them
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add color governance test**

Allow:

- token values in `tokens-*.css`;
- relative token usage: `oklch(from var(--...))`;
- local named custom properties when defined in the same page, for example `--map-cell-surface`.

Fail:

- `rgba(` in active route prototype HTML.
- direct `oklch(` in element data attributes or CSS declarations unless the line defines a named local data-viz variable.

**Step 2: Replace known cases**

- `page-portfolio.html`: replace `rgba(0, 0, 0, ...)` shadows/backdrops with `var(--surface-overlay)`, `var(--overlay-*)`, or `oklch(from var(--neutral-0) l c h / alpha)`.
- `page-platform-settings.html`: replace `rgba()` backdrop/shadow with semantic overlay tokens.
- `page-a-shares.html`: keep treemap colors as named local variables, not scattered direct declarations.
- `page-agent-console.html`: replace donut JSON colors with domain token references if the drawing helper supports CSS variables; otherwise add named local variables and document the exception in a comment.

**Step 3: Verify**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
bun run test:run scripts/page-a-shares-prototype.test.ts scripts/page-agent-console-prototype.test.ts scripts/page-platform-settings-prototype.test.ts
```

Expected: color governance test passes and affected page tests pass.

---

## Phase 5: Edition-Level Verification And Review Update

### Task 5.1: Run Active Prototype Gates

**Files:**
- No source edits unless gates expose failures
- Output: `test-results/ditto-design-cycle-gates/prototype-remediation-2026-04-28/`

**Step 1: Run route prototype tests**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts
```

Expected: PASS.

**Step 2: Run gate loop for active pages**

Run:

```bash
node - <<'JS'
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = "prototype";
const manifest = JSON.parse(fs.readFileSync(path.join(root, ".edition-manifest.json"), "utf8"));
const archived = new Set(["ai-overview", "ai-copilot"]);

for (const page of manifest.pages) {
  if (!page.file?.startsWith("page-") || archived.has(page.id)) continue;
  const outDir = `test-results/ditto-design-cycle-gates/prototype-remediation-2026-04-28/${page.id}`;
  const result = spawnSync("bun", [
    "run",
    "prototype:gates",
    "--",
    "--prototype",
    `${root}/${page.file}`,
    "--out-dir",
    outDir,
  ], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
JS
```

Expected: all 27 active route prototypes pass.

**Step 3: Run full check**

Run:

```bash
bun run check
```

Expected: PASS.

### Task 5.2: Produce Remediation Review Addendum

**Files:**
- Create: `docs/reviews/2026-04-28-prototype-design-remediation-review.md`
- Modify: `prototype/.edition-manifest.json`
- Modify: `.arch-manifest.json` only if governance update is approved

**Step 1: Write review summary**

Include:

- Active route candidate count: 27
- Archived specimens: `ai-overview`, `ai-copilot`
- Overlay registry count before/after
- Shell drift fixed list
- Typography governance decision
- Color governance exceptions, if any
- Gate/test commands and results

**Step 2: Update manifest audit fields**

In `.edition-manifest.json`, add a `crossPageAudit` or update existing audit fields:

```json
"crossPageAudit": {
  "date": "2026-04-28",
  "activeRoutePrototypeCount": 27,
  "archivedSpecimens": ["ai-overview", "ai-copilot"],
  "shellFamilyStatus": "PASS",
  "overlayRegistryStatus": "PASS",
  "galleryDisciplineStatus": "PASS",
  "typographyStatus": "PASS",
  "colorGovernanceStatus": "PASS",
  "verification": [
    "bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts",
    "active prototype:gates loop",
    "bun run check"
  ]
}
```

**Step 3: Verify final docs and checks**

Run:

```bash
bun run check
git diff --check
```

Expected: PASS.

---

## Handoff Notes

- This plan intentionally does not implement React route/component changes.
- If execution discovers a visual regression while replacing overlay classes, stop and preserve the current visual behavior before continuing the class migration.
- If a contract selector is missing because the prototype lacks a stable selector, add a stable `data-contract-slot` or `data-overlay-ref` to the prototype rather than weakening the contract.
- If full `bun run check` fails due to Playwright timing under heavy parallel load, rerun the failing focused test set once before classifying the failure as product regression.
