# Ditto Consistency Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring Ditto's specs, edition prototypes, page contracts, React routes, overlay behavior, and core UI primitives back into one coherent implementation path.

**Architecture:** Treat IA v2.0 + page blueprints as product truth, page contracts as machine-readable implementation truth, and React routes/components as downstream consumers. Stabilize the TypeScript/check gate first, then generate complete contracts, migrate route/domain ownership, and finally make overlay/token behavior registry-driven instead of page-local.

**Tech Stack:** Bun, TypeScript strict, TanStack Router, React 19, Tailwind CSS v4, Radix Dialog/Sheet, Vitest + React Testing Library, Biome, existing Ditto page-contract generator.

---

## Execution Rules

- Use `bun` only.
- Do not start Phase 2 until Phase 0 makes `bun run check` pass.
- Do not edit `.arch-manifest.json`, `tsconfig*.json`, or route topology without explicit approval at execution time, because those are project/config/governance boundaries.
- Keep legacy behavior only when it is explicitly marked as deprecated redirect/dev-only; do not let legacy routes remain in IA coverage.
- Every phase ends with `bun run check`.
- Commit after each phase, not after every tiny edit, unless the executing developer prefers smaller commits.

---

## Phase 0: Restore The Verification Gate

Current `bun run check` stops at `tsc -b`, so later route/contract work cannot be trusted until this is fixed.

### Task 0.1: Add Test Runtime Types To App TS Config

**Files:**
- Modify: `tsconfig.app.json`

**Step 1: Confirm current failure**

Run:

```bash
bun run check
```

Expected: FAIL in `tsc -b` with globals like `beforeEach`, `afterEach`, `beforeAll`, `afterAll`, `vi`, and Node types such as `node:path`.

**Step 2: Update test type availability**

In `tsconfig.app.json`, change:

```json
"types": ["vite/client"]
```

to:

```json
"types": ["vite/client", "vitest/globals", "node"]
```

**Step 3: Run focused type check**

Run:

```bash
bunx tsc -b
```

Expected: the global test function errors disappear. Other type errors may remain.

### Task 0.2: Replace TanStack Router `handle` With Supported Static Data

**Files:**
- Modify all route files under `src/routes/**/*.tsx` currently containing `handle: { title: ... }`
- Modify: `src/features/shell/components/header.tsx`
- Modify: `src/features/shell/components/header.test.tsx`

**Step 1: Write/update the failing header test**

In `src/features/shell/components/header.test.tsx`, update mocked route metadata from:

```ts
mockRoutesById["/markets"] = { options: { handle: { title: "市场" } } };
```

to:

```ts
mockRoutesById["/markets"] = { options: { staticData: { title: "市场" } } };
```

Run:

```bash
bun run test:run src/features/shell/components/header.test.tsx
```

Expected: FAIL if `header.tsx` still reads `handle`.

**Step 2: Change route metadata**

Replace every route option:

```ts
handle: { title: "..." },
```

with:

```ts
staticData: { title: "..." },
```

Affected files include:

- `src/routes/index.tsx`
- `src/routes/instruments.tsx`
- `src/routes/instruments/$id.tsx`
- `src/routes/markets.tsx`
- `src/routes/markets/index.tsx`
- `src/routes/markets/a-shares.tsx`
- `src/routes/markets/calendar.tsx`
- `src/routes/markets/intelligence.tsx`
- `src/routes/markets/screener.tsx`
- `src/routes/research.tsx`
- `src/routes/research/index.tsx`
- `src/routes/research/backtest.$id.tsx`
- `src/routes/research/factors.$id.tsx`
- `src/routes/research/regime.tsx`
- `src/routes/research/strategy-studio.tsx`
- `src/routes/trading.tsx`
- `src/routes/trading/index.tsx`
- `src/routes/trading/orders.tsx`
- `src/routes/trading/risk.tsx`
- `src/routes/trading/signals.tsx`
- `src/routes/platform.tsx`
- `src/routes/platform/index.tsx`
- `src/routes/showcase.tsx`
- legacy AI/strategy route files until removed in Phase 2

**Step 3: Update shell header metadata lookup**

In `src/features/shell/components/header.tsx`, read route title from `route.options.staticData?.title`.

**Step 4: Verify**

Run:

```bash
bun run test:run src/features/shell/components/header.test.tsx
bunx tsc -b
```

Expected: route `handle` type errors disappear.

### Task 0.3: Fix API Type Export Drift

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/features/trading/hooks/use-orders-summary.ts`
- Modify: `src/features/trading/hooks/use-signals-queue.ts`
- Modify: `src/mocks/fixtures/trading.ts`
- Inspect/modify as needed: `src/types/trading.ts`, `src/types/research.ts`, `src/types/ai.ts`, `src/types/home.ts`

**Step 1: Identify intended canonical names**

Use request/response naming from the source domain files:

- `src/types/trading.ts`: `GetOrdersSummaryResponse`, `GetSignalsQueueResponse`
- `src/types/research.ts`: `ResearchPulseResponse` or add `GetResearchPulseResponse`
- `src/types/ai.ts` vs `src/types/home.ts`: avoid duplicate `AgentFinding` / `GetAgentFindingsResponse` exports

**Step 2: Write a barrel export type check**

Create or update:

- Test: `src/types/index.test.ts`

Example:

```ts
import type {
	GetOrdersSummaryResponse,
	GetSignalsQueueResponse,
	ResearchPulseResponse,
} from "@/types";

type AssertExported = [
	GetOrdersSummaryResponse,
	GetSignalsQueueResponse,
	ResearchPulseResponse,
];

it("exports canonical API response types", () => {
	expect(true satisfies boolean).toBe(true);
});
```

**Step 3: Run failing type check**

Run:

```bash
bunx tsc -b
```

Expected: FAIL until exports/imports are aligned.

**Step 4: Fix exports/imports**

Rules:

- Prefer generated/OpenAPI-style `Get*Response` names for API hooks.
- Alias domain-colliding types in `src/types/index.ts`, for example `AgentFinding as HomeAgentFinding`.
- Do not introduce `any`.
- Do not use `@ts-ignore` or `@ts-expect-error`.

**Step 5: Verify**

Run:

```bash
bunx tsc -b
```

Expected: API export errors disappear.

### Task 0.4: Fix DataTable And DittoGrid Test Generics

**Files:**
- Modify: `src/components/data/data-table/data-table.tsx`
- Modify: `src/components/data/data-table/data-table.test.tsx`
- Modify: `src/components/data/dittogrid/ditto-grid.tsx`
- Modify: `src/components/data/dittogrid/ditto-grid.test.tsx`

**Step 1: Add/confirm generic component signatures**

`DataTable` should accept generic row data:

```ts
export interface DataTableProps<TRow extends object> {
	readonly columns: readonly ColumnDef<TRow>[];
	readonly data: readonly TRow[];
	readonly onRowClick?: (row: TRow) => void;
}
```

**Step 2: Update tests to use the generic naturally**

Example:

```tsx
render(<DataTable<TestRow> columns={columns} data={rows} />);
```

**Step 3: Fix AG Grid column field typing**

Use `ColDef<Row>["field"]` compatible string literals, not broad `string`.

**Step 4: Verify**

Run:

```bash
bun run test:run src/components/data/data-table/data-table.test.tsx
bun run test:run src/components/data/dittogrid/ditto-grid.test.tsx
bunx tsc -b
```

Expected: table/grid generic errors disappear.

### Task 0.5: Clear Remaining Strict Type Errors

**Files:**
- Modify files reported by `bunx tsc -b`

Known categories:

- Unused imports/locals: remove them or use intentionally.
- `ApiError` parameter property under `erasableSyntaxOnly`: rewrite constructor without parameter properties.
- mock fixture shape mismatches: update fixtures to actual response types.
- `RunStatus` missing import in `src/types/ai.ts`: import from `./common`.
- `JSX` namespace in `src/providers/query-provider.tsx`: return `React.ReactNode` / `React.ReactElement` or import the correct React type.

**Step 1: Run type check**

```bash
bunx tsc -b
```

**Step 2: Fix one error group at a time**

Do not silence errors. Prefer correct types or fixture shapes.

**Step 3: Full verification**

```bash
bun run check
```

Expected: PASS. This is the gate before Phase 1.

**Phase 0 commit:**

```bash
git add tsconfig.app.json src
git commit -m "fix: restore TypeScript verification gate"
```

---

## Phase 1: Contract And Governance Truth Source

This phase makes IA/prototype/contract coverage machine-checkable before route migration.

### Task 1.1: Add Route Coverage Audit Script

**Files:**
- Create: `scripts/audit-route-coverage.mjs`
- Modify: `package.json`

**Step 1: Write the expected IA route list**

In `scripts/audit-route-coverage.mjs`, define:

```js
const IA_ROUTES = [
  "/",
  "/markets",
  "/markets/a-shares",
  "/markets/screener",
  "/markets/watchlist",
  "/markets/intelligence",
  "/markets/calendar",
  "/instruments/$id",
  "/research",
  "/research/factors",
  "/research/factors/$id",
  "/research/strategies",
  "/research/strategies/$id",
  "/research/strategies/$id/studio",
  "/research/backtest",
  "/research/backtest/$id",
  "/research/experiments",
  "/research/regime",
  "/research/universes",
  "/trading",
  "/trading/signals",
  "/trading/orders",
  "/trading/portfolio",
  "/trading/risk",
  "/platform",
  "/platform/settings",
  "/platform/agents",
];
```

**Step 2: Parse actual routes**

Read `src/routes/**/*.tsx`, extract `createFileRoute("...")`, normalize trailing slash and dynamic params.

**Step 3: Fail on missing or unexpected product routes**

Allowlist dev-only routes:

```js
const DEV_ONLY_ROUTES = ["/showcase"];
```

Do not allow `/ai`, `/ai/copilot`, `/ai/agents`, `/strategies`, `/strategies/$id`, `/research/strategy-studio` after Phase 2.

**Step 4: Add npm script**

In `package.json`:

```json
"audit:routes": "bun scripts/audit-route-coverage.mjs"
```

**Step 5: Verify current red state**

Run:

```bash
bun run audit:routes
```

Expected before Phase 2: FAIL with the same missing/legacy route drift listed in the review.

### Task 1.2: Extend Contract Schema For Landing And Overlay Registry

**Files:**
- Modify: `.claude/skills/ditto-page-contract/scripts/schema/contract.schema.json`
- Modify: `.claude/skills/ditto-page-contract/scripts/validators/contract-validator.mjs`
- Modify: `.claude/skills/ditto-page-contract/scripts/generate.mjs`
- Modify: `docs/contracts/pages/home.contract.json`

**Step 1: Add optional `landing` schema**

Add:

```json
"landing": {
  "type": "object",
  "required": ["reactRouteStatus", "featureModule", "contractStatus", "overlayStatus", "visualAuditStatus"],
  "properties": {
    "reactRouteStatus": { "type": "string", "enum": ["missing", "scaffolded", "implemented"] },
    "featureModule": { "type": "string" },
    "contractStatus": { "type": "string", "enum": ["missing", "draft", "generated", "verified"] },
    "overlayStatus": { "type": "string", "enum": ["none", "gallery-only", "triggerable", "implemented"] },
    "visualAuditStatus": { "type": "string", "enum": ["missing", "baseline", "pass"] }
  }
}
```

**Step 2: Add optional `overlays` schema**

Add overlay entries:

```json
{
  "id": "string",
  "kind": "drawer | sheet | modal | alert-dialog | toast | inline",
  "blocking": true,
  "requiredInDefaultFlow": true,
  "trigger": { "slot": "string", "action": "string" },
  "prototypeSelector": "string",
  "reactComponent": "string",
  "closeBehavior": ["escape", "outside-click", "primary-action"]
}
```

**Step 3: Validator checks**

Add WARN/BLOCK checks:

- BLOCK: required overlay has `prototypeSelector`.
- BLOCK: `kind` is known.
- WARN: `requiredInDefaultFlow` overlay has no `reactComponent` while `landing.reactRouteStatus === "implemented"`.

**Step 4: Generator output**

Extend `PageContract` interface with:

```ts
overlays?: readonly PageOverlayContract[];
landing?: PageLandingStatus;
```

Emit overlay/landing fields into `page-contracts.generated.ts`.

**Step 5: Verify**

Run:

```bash
bun run generate-contracts
node --check scripts/visual-audit.config.generated.mjs
bunx tsc -b
```

Expected: generated files remain syntactically valid.

### Task 1.3: Create Contracts For All Reviewed Route Pages

**Files:**
- Create: `docs/contracts/pages/*.contract.json`
- Modify generated: `src/features/shell/page-contracts.generated.ts`
- Modify generated: `scripts/visual-audit.config.generated.mjs`

**Step 1: Use Home contract as template**

Copy from:

```bash
docs/contracts/pages/home.contract.json
```

**Step 2: Create contracts in batches**

Batch A, existing React pages:

- `cross-market.contract.json` → `/markets`
- `a-shares.contract.json` → `/markets/a-shares`
- `markets-screener.contract.json` → `/markets/screener`
- `markets-intelligence.contract.json` → `/markets/intelligence`
- `markets-calendar.contract.json` → `/markets/calendar`
- `research.contract.json` → `/research`
- `regime-monitor.contract.json` → `/research/regime`
- `factor-analysis.contract.json` → `/research/factors/$id`
- `backtest-result.contract.json` → `/research/backtest/$id`
- `trading-overview.contract.json` → `/trading`
- `signals-inbox.contract.json` → `/trading/signals`
- `orders-ledger.contract.json` → `/trading/orders`
- `risk-center.contract.json` → `/trading/risk`
- `instrument-hub.contract.json` → `/instruments/$id`
- `platform.contract.json` → `/platform`

Batch B, target pages currently missing/scaffold-only:

- `watchlist.contract.json` → `/markets/watchlist`
- `factor-list.contract.json` → `/research/factors`
- `strategy-list.contract.json` → `/research/strategies`
- `strategies-detail.contract.json` → `/research/strategies/$id`
- `strategy-studio.contract.json` → `/research/strategies/$id/studio`
- `backtest-list.contract.json` → `/research/backtest`
- `experiment-list.contract.json` → `/research/experiments`
- `universe-list.contract.json` → `/research/universes`
- `portfolio.contract.json` → `/trading/portfolio`
- `platform-settings.contract.json` → `/platform/settings`
- `agent-console.contract.json` → `/platform/agents`

Batch C, global component:

- `copilot-sidecar.contract.json` if the schema supports global components; otherwise keep it out of page contracts and track in docs only.

**Step 3: Mark deprecated prototypes**

For `page-ai-overview.html` and `page-ai-copilot.html`, do not create product route contracts. Record them as deprecated/prototype archive candidates in `.edition-manifest.json` or a migration note.

**Step 4: Generate**

Run:

```bash
bun run generate-contracts
```

Expected:

- `src/features/shell/page-contracts.generated.ts` contains all product page contracts.
- `scripts/visual-audit.config.generated.mjs` contains all visual audit pages.

**Step 5: Verify**

Run:

```bash
node --check scripts/visual-audit.config.generated.mjs
bunx tsc -b
```

Expected: PASS.

### Task 1.4: Replace Legacy Contract Tests With Generated Coverage Tests

**Files:**
- Modify: `src/features/shell/page-contracts.test.ts`
- Modify: `src/features/shell/index.ts`

**Step 1: Remove legacy route coverage expectations**

Delete the hard-coded 21-route legacy coverage list.

**Step 2: Add generated coverage test**

Use:

```ts
import { PAGE_CONTRACTS } from "./page-contracts.generated";

const IA_ROUTES = [
	"/",
	"/markets",
	// ...
	"/platform/agents",
] as const;

it("generated contracts cover every IA route", () => {
	const covered = new Set(PAGE_CONTRACTS.map((contract) => contract.route));
	for (const route of IA_ROUTES) {
		expect(covered.has(route), `Missing contract for ${route}`).toBe(true);
	}
});
```

**Step 3: Stop exporting legacy as a first-class API**

In `src/features/shell/index.ts`, keep only generated exports as default. If legacy remains, export it behind a clearly named migration alias:

```ts
export { PAGE_CONTRACTS } from "./page-contracts.generated";
```

**Step 4: Verify**

Run:

```bash
bun run test:run src/features/shell/page-contracts.test.ts
bun run check
```

Expected: PASS.

**Phase 1 commit:**

```bash
git add package.json scripts docs/contracts .claude/skills/ditto-page-contract src/features/shell
git commit -m "feat: restore page contract truth source"
```

---

## Phase 2: Route And Domain Migration

This phase aligns React route topology with IA v2.0.

### Task 2.1: Remove AI From Product Navigation Domain

**Files:**
- Modify: `src/features/navigation/types.ts`
- Modify: `src/features/navigation/components/domain-icon.tsx`
- Modify: `src/features/navigation/components/domain-icon.test.tsx`
- Modify: `src/features/shell/hooks/use-active-domain.ts`
- Modify: `src/features/shell/components/rail.tsx`
- Modify: `DESIGN.md`

**Step 1: Update tests first**

In `domain-icon.test.tsx`, remove `"ai"` from `ALL_DOMAIN_IDS`.

**Step 2: Update domain model**

In `src/features/navigation/types.ts`, remove:

```ts
| "ai"
```

and remove:

```ts
{ id: "ai", label: "AI", path: "/ai" }
```

**Step 3: Keep AI as capability tokens**

Do not remove agent/copilot business tokens from CSS. The product change is navigation/domain ownership, not deleting AI functionality.

**Step 4: Verify**

Run:

```bash
bun run test:run src/features/navigation/components/domain-icon.test.tsx
bunx tsc -b
```

Expected: PASS.

### Task 2.2: Move Agent Console Route To Platform

**Files:**
- Create: `src/routes/platform/agents.tsx`
- Create/modify: `src/features/platform/components/agents-page.tsx`
- Create/modify: `src/features/platform/components/agent-findings-list.tsx`
- Create/modify: `src/features/platform/components/agent-inspector-panel.tsx`
- Modify: `src/features/platform/components/index.ts`
- Delete after migration: `src/routes/ai/agents.tsx`

**Step 1: Write route test expectation**

In the route audit test/script from Phase 1, assert `/platform/agents` exists and `/ai/agents` does not.

**Step 2: Move page ownership**

Prefer moving Agent Console components from `src/features/ai/components` into `src/features/platform/components` if they are Platform-owned. If too large for one commit, create a temporary `PlatformAgentsPage` wrapper in Platform and move child components in the next commit.

**Step 3: Add route**

```ts
import { createFileRoute } from "@tanstack/react-router";
import { PlatformAgentsPage } from "@/features/platform";

export const Route = createFileRoute("/platform/agents")({
	component: PlatformAgentsPage,
	staticData: { title: "Agent Console" },
});
```

**Step 4: Delete legacy route file**

Delete `src/routes/ai/agents.tsx`.

**Step 5: Verify**

Run:

```bash
bun run audit:routes
bun run test:run src/features/ai/components/agent-components.test.tsx
bun run check
```

Expected: route audit moves one step closer; no `/ai/agents`.

### Task 2.3: Convert Copilot To Global Sidecar

**Files:**
- Create: `src/features/copilot/components/copilot-sidecar.tsx`
- Create: `src/features/copilot/components/copilot-sidecar.test.tsx`
- Create: `src/features/copilot/index.ts`
- Modify: `src/features/shell/components/header.tsx`
- Modify: `src/features/shell/components/app-shell.tsx`
- Delete after migration: `src/routes/ai/copilot.tsx`

**Step 1: Write open/close test**

Test should assert:

- Header command opens sidecar.
- ESC or close button closes sidecar.
- Sidecar has `role="dialog"` and accessible label.

**Step 2: Implement sidecar with existing Copilot internals**

Reuse:

- `src/features/ai/components/copilot-session-list.tsx`
- `src/features/ai/components/copilot-chat-view.tsx`
- `src/features/ai/components/copilot-context-panel.tsx`

Then move them into `src/features/copilot` in a follow-up cleanup.

**Step 3: Wire in AppShell**

Render sidecar once at shell level, not per page.

**Step 4: Delete route**

Delete `src/routes/ai/copilot.tsx`.

**Step 5: Verify**

Run:

```bash
bun run test:run src/features/copilot/components/copilot-sidecar.test.tsx
bun run audit:routes
bun run check
```

Expected: `/ai/copilot` is gone; Copilot remains usable globally.

### Task 2.4: Remove AI Overview Route

**Files:**
- Delete: `src/routes/ai.tsx`
- Delete: `src/routes/ai/index.tsx`
- Inspect/remove if empty: `src/routes/ai/`
- Keep or archive: `src/features/ai/components/ai-page.tsx`

**Step 1: Ensure Home and Platform carry AI summary**

Before deleting the route, confirm Home has Agent Findings and Platform Agents exists.

**Step 2: Delete route files**

Delete `src/routes/ai.tsx` and `src/routes/ai/index.tsx`.

**Step 3: Verify**

Run:

```bash
bun run audit:routes
bun run check
```

Expected: `/ai` is not present in actual product routes.

### Task 2.5: Move Strategy Routes Into Research

**Files:**
- Create: `src/routes/research/strategies.tsx`
- Create: `src/routes/research/strategies/$id.tsx`
- Create: `src/routes/research/strategies/$id/studio.tsx`
- Delete: `src/routes/strategies.tsx`
- Delete: `src/routes/strategies/$id.tsx`
- Delete: `src/routes/research/strategy-studio.tsx`
- Modify: `src/features/strategy/components/strategy-page.tsx`

**Step 1: Add new routes**

Use existing pages:

- `/research/strategies/$id` → `StrategyDetailPage`
- `/research/strategies/$id/studio` → `StrategyPage`

For `/research/strategies`, create a scaffold list page if no implementation exists.

**Step 2: Parameterize Strategy Studio**

Update `StrategyPage` to read `id` from `useParams` instead of hard-coded `strat-001`.

**Step 3: Delete legacy routes**

Remove old route files.

**Step 4: Verify active domain**

Add a test for `useActiveDomain` or Shell behavior proving `/research/strategies/strat-001` maps to `research`, not `home`.

**Step 5: Verify**

Run:

```bash
bun run audit:routes
bun run test:run src/features/strategy/components/strategy-detail-components.test.tsx
bun run check
```

Expected: Strategy routes align with Research domain.

### Task 2.6: Add Missing IA Route Scaffolds

**Files:**
- Create: `src/routes/markets/watchlist.tsx`
- Create: `src/routes/research/factors.tsx`
- Create: `src/routes/research/backtest.tsx`
- Create: `src/routes/research/experiments.tsx`
- Create: `src/routes/research/universes.tsx`
- Create: `src/routes/trading/portfolio.tsx`
- Create: `src/routes/platform/settings.tsx`
- Create minimal page components in the corresponding feature folders

**Step 1: Write route coverage red/green**

Run:

```bash
bun run audit:routes
```

Expected before scaffolds: FAIL for missing routes.

**Step 2: Add scaffold pages**

Each scaffold should:

- Use the correct Shell family from the contract.
- Include stable `data-slot` selectors named in the contract.
- Avoid fake marketing pages.
- Use existing feature patterns.

**Step 3: Verify**

Run:

```bash
bun run audit:routes
bun run check
```

Expected: route audit PASS.

**Phase 2 commit:**

```bash
git add src/routes src/features src/styles DESIGN.md
git commit -m "feat: align routes and domains with IA v2"
```

---

## Phase 3: Overlay Registry And Consistent Runtime Behavior

### Task 3.1: Add Overlay Contract Types

**Files:**
- Create: `src/features/shell/overlay-contracts.ts`
- Modify: `src/features/shell/index.ts`

**Step 1: Define runtime types**

```ts
export type OverlayKind =
	| "drawer"
	| "sheet"
	| "modal"
	| "alert-dialog"
	| "toast"
	| "inline";

export interface OverlayContract {
	readonly id: string;
	readonly kind: OverlayKind;
	readonly blocking: boolean;
	readonly requiredInDefaultFlow: boolean;
	readonly trigger: {
		readonly slot: string;
		readonly action: string;
	};
	readonly prototypeSelector: string;
	readonly reactComponent: string;
	readonly closeBehavior: readonly string[];
}
```

**Step 2: Export from shell**

```ts
export type { OverlayContract, OverlayKind } from "./overlay-contracts";
```

**Step 3: Verify**

Run:

```bash
bunx tsc -b
```

Expected: PASS.

### Task 3.2: Build Unified Dialog/Drawer Primitives

**Files:**
- Modify: `src/components/ui/dialog.tsx`
- Modify: `src/components/ui/sheet.tsx`
- Modify: `src/components/indicator/overlay/drawer.tsx`
- Create/modify tests under `src/components/ui/*.test.tsx` and `src/components/indicator/overlay/drawer.test.tsx`

**Step 1: Write primitive tests**

Assert:

- overlay surface uses Ditto overlay/modal tokens, not `bg-black/50`
- close control has accessible label
- close control is an icon button or semantic close button
- drawer width uses `--width-drawer`

**Step 2: Replace raw overlay styles**

Replace `bg-black/50` with a Ditto tokenized overlay class, for example:

```tsx
"fixed inset-0 z-50 bg-(--color-surface-app)/75"
```

or introduce a proper overlay token if Tailwind opacity does not support the CSS variable shape.

**Step 3: Replace `&times;`**

Use an icon component already available in the project, or add a small internal close glyph component without introducing a new dependency.

**Step 4: Verify**

Run:

```bash
bun run test:run src/components/indicator/overlay/drawer.test.tsx
bun run check
```

Expected: PASS.

### Task 3.3: Make Required Prototype Overlays Triggerable In Default Flow

**Files:**
- Modify: `docs/designs/specs/prototypes/page-*.html`
- Modify: `scripts/page-*-prototype.test.ts`
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`

**Step 1: Choose first target batch**

Start with pages already implemented in React:

- `page-orders-ledger.html`
- `page-risk-center.html`
- `page-signals-inbox.html`
- `page-platform.html`

**Step 2: Update prototype tests**

For each required overlay, test that default view has a trigger:

```ts
await expect(page.locator("#default-view label[for='overlay-order-detail']")).toHaveCount(1);
```

**Step 3: Add default triggers**

Wire row actions / buttons / cards to existing CSS-only overlay ids.

**Step 4: Run prototype gates**

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-orders-ledger.html --out-dir test-results/ditto-design-cycle-gates/orders-ledger-overlay-default-flow
```

Expected: PASS.

**Step 5: Repeat in batches**

Batch 2: Watchlist, Strategy List, Factor List, Backtest List.  
Batch 3: Home, Research, Markets, Instrument Hub.  
Batch 4: remaining route pages.

### Task 3.4: Implement Overlay Registry Consumption In React Pages

**Files:**
- Create: `src/features/shell/components/overlay-provider.tsx`
- Create: `src/features/shell/components/overlay-provider.test.tsx`
- Modify pages with required overlays, starting with:
  - `src/features/trading/components/orders-page.tsx`
  - `src/features/trading/components/risk-page.tsx`
  - `src/features/trading/components/signals-page.tsx`

**Step 1: Build provider API**

```ts
const { openOverlay, closeOverlay, activeOverlayId } = useOverlayController();
```

**Step 2: Keep existing Drawer behavior green**

Orders and Risk already use Drawer; adapt them first without changing UX.

**Step 3: Add tests**

For each page:

- default state does not show overlay
- click row/action opens overlay
- close returns to full page

**Step 4: Verify**

Run:

```bash
bun run test:run src/features/trading/components/orders-components.test.tsx
bun run test:run src/features/trading/components/risk-components.test.tsx
bun run check
```

Expected: PASS.

**Phase 3 commit:**

```bash
git add docs/designs/specs/prototypes scripts src/components src/features/shell src/features/trading
git commit -m "feat: unify overlay registry and runtime behavior"
```

---

## Phase 4: Core UI Token Convergence

### Task 4.1: Migrate `Button` To Ditto Tokens

**Files:**
- Modify: `src/components/ui/button.tsx`
- Create/modify: `src/components/ui/button.test.tsx`

**Step 1: Write token leakage test**

```ts
import { buttonVariants } from "./button";

it("does not use shadcn default token names", () => {
	const classes = buttonVariants();
	expect(classes).not.toContain("bg-primary");
	expect(classes).not.toContain("ring-ring");
	expect(classes).not.toContain("border-border");
});
```

**Step 2: Replace tokens**

Use Ditto tokens:

- `bg-primary` → `bg-(--color-accent)`
- `text-primary-foreground` → `text-(--color-accent-fg)`
- `border-border` → `border-(--color-border-default)`
- `ring-ring` → `ring-(--color-focus-ring)`
- `bg-muted` → `bg-(--color-surface-muted)` or interaction token

**Step 3: Verify**

```bash
bun run test:run src/components/ui/button.test.tsx
bun run check
```

Expected: PASS.

### Task 4.2: Migrate Badge/Tabs/Dialog/Sheet Token Usage

**Files:**
- Modify: `src/components/ui/badge.tsx`
- Modify: `src/components/ui/tabs.tsx`
- Modify: `src/components/ui/dialog.tsx`
- Modify: `src/components/ui/sheet.tsx`
- Create/modify tests under `src/components/ui`

**Step 1: Add leakage tests**

For each primitive, assert no `bg-primary`, `text-primary`, `text-muted-foreground`, `ring-ring`, `bg-background`, or `bg-muted` remains unless explicitly bridged in `globals.css`.

**Step 2: Replace tokens**

Map to Ditto semantic/component tokens.

**Step 3: Verify**

```bash
bun run test:run src/components/ui
bun run check
```

Expected: PASS.

### Task 4.3: Define Inline Style Exception Boundary

**Files:**
- Modify: `src/features/shell/design-system-compliance.test.ts`
- Modify components using dynamic inline styles:
  - `src/components/data/flow-bar.tsx`
  - `src/components/chart/line-chart.tsx`
  - `src/components/chart/area-chart.tsx`
  - `src/components/indicator/confidence-bar/confidence-bar.tsx`
  - `src/features/research/components/factor-table.tsx`
  - `src/features/platform/components/platform-page.tsx`

**Step 1: Decide policy**

Recommended policy:

- Feature pages must not use inline styles.
- Design-system primitives may use inline CSS variables only for dynamic dimensions, with a test allowlist.

**Step 2: Move feature-level inline styles into primitives**

Example: replace local platform progress bars with a shared `ProgressBar` / `FlowBar` variant.

**Step 3: Add compliance test**

Scan `src/features/**/*.tsx` for `style={{`.

Expected:

- FAIL if feature files use inline styles.
- PASS for allowlisted primitive files.

**Step 4: Verify**

```bash
bun run test:run src/features/shell/design-system-compliance.test.ts
bun run check
```

Expected: PASS.

**Phase 4 commit:**

```bash
git add src/components src/features src/styles
git commit -m "refactor: align core UI primitives with Ditto tokens"
```

---

## Phase 5: Final Governance Update

### Task 5.1: Sync Manifests And Design Docs

**Files:**
- Modify: `.arch-manifest.json`
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
- Modify: `DESIGN.md`
- Modify: `docs/reviews/2026-04-27-project-consistency-architecture-review.md`

**Step 1: Update `.arch-manifest.json`**

Record:

- route coverage status
- generated contract count
- overlay registry status
- last audit date `2026-04-27`

**Step 2: Complete edition metadata**

For all route pages, fill:

- `shellFamily`
- `blueprintId`
- `landing`

**Step 3: Update `DESIGN.md`**

Replace six-domain language with five-domain product language. Keep AI as embedded intelligence / global sidecar capability.

**Step 4: Update review report**

Add a “Remediation Completed” appendix only after all checks pass.

### Task 5.2: Final Full Verification

Run:

```bash
bun run check
bun run audit:routes
bun run generate-contracts
git diff --exit-code src/features/shell/page-contracts.generated.ts scripts/visual-audit.config.generated.mjs
```

Expected:

- `bun run check`: PASS
- `audit:routes`: PASS
- generated artifacts are up to date
- no unexpected generated diff

**Phase 5 commit:**

```bash
git add .arch-manifest.json docs DESIGN.md src scripts package.json
git commit -m "chore: sync governance after consistency remediation"
```

---

## Recommended Execution Order

1. Phase 0 is mandatory first. It restores trust in the test gate.
2. Phase 1 should land before route migration so contracts can prove drift.
3. Phase 2 changes IA-facing behavior and should be reviewed carefully.
4. Phase 3 and Phase 4 can proceed independently after Phase 2, but do not run them in parallel on the same files.
5. Phase 5 is only documentation/governance sync after checks are green.

## Rollback Strategy

- Phase 0 rollback: revert type/test-only fixes if a better TS config strategy is chosen.
- Phase 1 rollback: keep new contract JSONs but do not export them until generator is stable.
- Phase 2 rollback: re-add deleted route files only if product owner decides to keep deprecated routes as redirects.
- Phase 3 rollback: keep primitive Dialog/Sheet improvements even if Overlay Registry rollout is delayed.
- Phase 4 rollback: token migration can be reverted primitive by primitive.

## Definition Of Done

- `bun run check` passes.
- `bun run audit:routes` passes.
- Generated page contracts cover all IA v2.0 product routes.
- Legacy AI/Strategy routes no longer appear as product routes.
- `/platform/agents`, `/platform/settings`, `/trading/portfolio`, and Research list/detail/studio routes exist.
- Required overlays are represented in contract JSON and have default-flow triggers.
- Core UI primitives no longer depend on shadcn default token names unless explicitly bridged.
- `.arch-manifest.json`, `.edition-manifest.json`, and `DESIGN.md` all agree on 5 product domains.
