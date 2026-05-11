# Shell Chrome Contract Standardization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize Ditto's global rail, header, search, view-preference, and account chrome so prototypes and React share one professional workstation grammar.

**Architecture:** Treat `Shell Chrome Contract` as the source of truth above individual shell families. Rail becomes top-level domain navigation only; Header becomes page identity plus fixed global utilities; workspace/table actions move into local toolbars. Prototype HTML, page contracts, React shell components, and guardrail tests must converge on the same `data-*` semantics.

**Tech Stack:** Bun, TypeScript strict, React 19, TanStack Router, Zustand, Tailwind CSS v4, static HTML/CSS prototypes, Vitest + React Testing Library, Biome.

---

## Execution Rules

- Use `bun` only.
- Do not add dependencies.
- Do not change design token values in this plan; only use existing semantic tokens.
- Do not change route topology without explicit approval.
- Keep prototype route pages at `style="..."` count 0.
- Keep AI Overview / AI Copilot archived; do not reintroduce AI as a product domain.
- Every implementation phase ends with focused tests. Final phase ends with `bun run check`.
- Commit after each phase only when the user confirms commit workflow for the current branch.

## Target Contract

### Rail

Rail is only for five top-level product domains:

- Home
- Markets
- Research
- Trading
- Platform

Rail must not contain theme, density, user, settings, notifications, or page actions.

### Header

Header has stable left-to-right responsibility:

1. Page identity: title, optional subtitle, domain/scope/session metadata.
2. Spacer/context: optional lightweight context, never a filter workbench.
3. Global utilities: command search, Copilot, notifications, help, account.

Header must not contain table filtering, export, refresh, column configuration, or per-workspace execution actions unless a shell family explicitly documents the action as global.

### Search

Search has three levels:

- Global command: `data-shell-utility="command"` in Header.
- Workspace search/filter: `data-workspace-action="filter"` or local toolbar.
- Table search: `data-table-toolbar="search"` inside the table/data surface.

The same visual component may be reused, but the scope must be explicit.

### View Preferences

Theme and density are view preferences. They live under Account / View Preferences, not as permanent header segments and not in the rail.

Prototype and React naming:

```html
<button data-shell-utility="account">...</button>
<div data-view-preferences-menu>
  <button data-set-density="dense">...</button>
  <button data-set-theme="light">...</button>
</div>
```

React equivalent:

```tsx
<HeaderUtilityBar>
  <GlobalCommandButton />
  <CopilotButton />
  <NotificationsButton />
  <HelpButton />
  <ViewPreferencesMenu />
</HeaderUtilityBar>
```

## Phase 0: Add Guardrails First

### Task 0.1: Add Prototype Shell Chrome Consistency Tests

**Files:**
- Modify: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add helper utilities**

Add helpers near the existing HTML helper functions:

```ts
function getFirstElementBody(html: string, selectorPattern: RegExp): string {
	const openTag = selectorPattern.exec(html);
	if (!openTag?.index) return "";

	const fullOpenTag = openTag[0];
	const tagName = /<([a-z]+)/i.exec(fullOpenTag)?.[1];
	if (!tagName) return "";

	const bodyStart = openTag.index + fullOpenTag.length;
	const closeMatch = new RegExp(`</${tagName}>`, "i").exec(html.slice(bodyStart));
	return closeMatch ? html.slice(bodyStart, bodyStart + closeMatch.index) : "";
}

function getHeaderHtml(html: string): string {
	return getFirstElementBody(html, /<header\b[^>]*class="[^"]*shell-header[^"]*"[^>]*>/i);
}

function getRailHtml(html: string): string {
	return getFirstElementBody(html, /<nav\b[^>]*class="[^"]*shell-rail[^"]*"[^>]*>/i);
}
```

**Step 2: Write failing active-domain test**

Add:

```ts
it("keeps active route prototypes on the five IA domains", () => {
	const violations = readManifest()
		.pages.filter(isActiveRoutePrototype)
		.flatMap((page) => {
			const domain = /data-domain="([^"]+)"/.exec(readPrototypeHtml(page))?.[1];
			return domain && !["home", "markets", "research", "trading", "platform"].includes(domain)
				? [`${page.id}:${domain}`]
				: [];
		});

	expect(violations).toEqual([]);
});
```

Expected current failure: `agent-console:ai`.

**Step 3: Write failing rail purity test**

Add:

```ts
it("keeps rail limited to top-level product navigation", () => {
	const violations: string[] = [];

	for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
		const rail = getRailHtml(readPrototypeHtml(page));
		if (/id="density-toggle"|id="theme-toggle"|aria-label="设置"|aria-label="用户"/.test(rail)) {
			violations.push(page.id);
		}
	}

	expect(violations).toEqual([]);
});
```

Expected current failure: at least `home`, plus pages with settings/user rail controls.

**Step 4: Write failing header utility contract test**

Add:

```ts
const requiredHeaderUtilities = ["command", "copilot", "notifications", "help", "account"] as const;

it("exposes the same global header utilities in active route prototypes", () => {
	const violations: string[] = [];

	for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
		const header = getHeaderHtml(readPrototypeHtml(page));
		for (const utility of requiredHeaderUtilities) {
			if (!header.includes(`data-shell-utility="${utility}"`)) {
				violations.push(`${page.id}:${utility}`);
			}
		}
	}

	expect(violations).toEqual([]);
});
```

Expected current failure: most pages.

**Step 5: Write failing view-preference placement test**

Add:

```ts
it("keeps theme and density controls inside view preferences menus", () => {
	const violations: string[] = [];

	for (const page of readManifest().pages.filter(isActiveRoutePrototype)) {
		const html = readPrototypeHtml(page);
		const header = getHeaderHtml(html);
		const rail = getRailHtml(html);
		const hasLooseControls =
			/(data-set-density|data-set-theme)/.test(header.replace(/<div[^>]*data-view-preferences-menu[\s\S]*?<\/div>/g, "")) ||
			/(data-set-density|data-set-theme|id="density-toggle"|id="theme-toggle")/.test(rail);

		if (hasLooseControls) violations.push(page.id);
	}

	expect(violations).toEqual([]);
});
```

Expected current failure: most pages.

**Step 6: Run the test and keep it failing**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: FAIL with chrome contract violations.

### Task 0.2: Add React Shell Chrome Tests

**Files:**
- Modify: `src/features/shell/components/header.test.tsx`
- Modify: `src/features/shell/components/rail.test.tsx`
- Create: `src/features/shell/components/view-preferences-menu.test.tsx`
- Modify: `src/features/shell/hooks/use-ui-preferences.test.ts`

**Step 1: Update header tests for fixed utilities**

In `header.test.tsx`, add:

```tsx
it("renders the fixed global utility bar", () => {
	render(<ShellHeader />);

	expect(screen.getByRole("button", { name: "打开全局命令" })).toHaveAttribute(
		"data-shell-utility",
		"command",
	);
	expect(screen.getByRole("button", { name: "打开 Copilot" })).toHaveAttribute(
		"data-shell-utility",
		"copilot",
	);
	expect(screen.getByRole("button", { name: "通知" })).toHaveAttribute(
		"data-shell-utility",
		"notifications",
	);
	expect(screen.getByRole("button", { name: "帮助" })).toHaveAttribute(
		"data-shell-utility",
		"help",
	);
	expect(screen.getByRole("button", { name: "账户与视图偏好" })).toHaveAttribute(
		"data-shell-utility",
		"account",
	);
});

it("does not render permanent density or theme segmented controls in the header", () => {
	render(<ShellHeader />);

	expect(screen.queryByRole("button", { name: "紧凑" })).not.toBeInTheDocument();
	expect(screen.queryByRole("button", { name: "亮色" })).not.toBeInTheDocument();
});
```

Expected current failure: utility attributes missing; inline theme/density controls still render.

**Step 2: Update rail tests**

Replace the existing bottom placeholder test in `rail.test.tsx` with:

```tsx
it("does not render settings, user, theme, or density controls in the rail", () => {
	render(<Rail />);

	expect(screen.queryByLabelText("设置")).not.toBeInTheDocument();
	expect(screen.queryByLabelText("用户")).not.toBeInTheDocument();
	expect(screen.queryByLabelText("密度切换")).not.toBeInTheDocument();
	expect(screen.queryByLabelText("主题切换")).not.toBeInTheDocument();
});
```

Expected current failure: settings and user buttons still render.

**Step 3: Add view preferences menu tests**

Create `src/features/shell/components/view-preferences-menu.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useUIPreferences } from "../hooks/use-ui-preferences";
import { ViewPreferencesMenu } from "./view-preferences-menu";

describe("ViewPreferencesMenu", () => {
	beforeEach(() => {
		useUIPreferences.setState({ theme: "dark", density: "default", sidebarCollapsed: false });
		document.documentElement.removeAttribute("data-theme");
		document.documentElement.removeAttribute("data-density");
	});

	it("opens account and view preferences from one utility trigger", async () => {
		const user = userEvent.setup();
		render(<ViewPreferencesMenu />);

		await user.click(screen.getByRole("button", { name: "账户与视图偏好" }));

		expect(screen.getByRole("menu", { name: "账户与视图偏好" })).toBeInTheDocument();
		expect(screen.getByRole("menuitemradio", { name: "紧凑" })).toBeInTheDocument();
		expect(screen.getByRole("menuitemradio", { name: "亮色" })).toBeInTheDocument();
	});

	it("updates density and theme DOM attributes immediately", async () => {
		const user = userEvent.setup();
		render(<ViewPreferencesMenu />);

		await user.click(screen.getByRole("button", { name: "账户与视图偏好" }));
		await user.click(screen.getByRole("menuitemradio", { name: "紧凑" }));
		await user.click(screen.getByRole("menuitemradio", { name: "亮色" }));

		expect(document.documentElement).toHaveAttribute("data-density", "dense");
		expect(document.documentElement).toHaveAttribute("data-theme", "light");
	});
});
```

**Step 4: Add store action tests**

In `use-ui-preferences.test.ts`, add tests that call the final actions directly:

```ts
it("setTheme syncs the DOM without a separate stale apply call", () => {
	useUIPreferences.getState().setTheme("light");
	expect(document.documentElement).toHaveAttribute("data-theme", "light");
});

it("setDensity syncs the DOM without a separate stale apply call", () => {
	useUIPreferences.getState().setDensity("dense");
	expect(document.documentElement).toHaveAttribute("data-density", "dense");
});
```

Expected current failure: setters update store but do not sync DOM.

**Step 5: Run focused failing tests**

Run:

```bash
bun run test:run \
  src/features/shell/components/header.test.tsx \
  src/features/shell/components/rail.test.tsx \
  src/features/shell/components/view-preferences-menu.test.tsx \
  src/features/shell/hooks/use-ui-preferences.test.ts
```

Expected: FAIL.

## Phase 1: Document The Shell Chrome Contract

### Task 1.1: Add The Contract Spec

**Files:**
- Create: `docs/designs/specs/19_ditto_shell_chrome_contract.md`
- Modify: `docs/designs/specs/10_ditto_shell_family_spec.md`
- Modify: `docs/designs/specs/13_ditto_component_spec.md`
- Modify: `DESIGN.md`

**Step 1: Create `19_ditto_shell_chrome_contract.md`**

Document:

- Rail responsibilities and non-responsibilities.
- Header left/middle/right zones.
- Global utility bar slots.
- Search scope taxonomy.
- View preference placement.
- Workspace/DataToolbar separation.
- Required prototype `data-*` attributes.
- React component mapping.

Minimum contract table:

```markdown
| Slot | Required Attribute | Owner | Notes |
|---|---|---|---|
| Rail domain link | `data-rail-domain="{domain}"` | Rail | Five IA domains only |
| Global command | `data-shell-utility="command"` | Header | Opens global command/search |
| Copilot | `data-shell-utility="copilot"` | Header | Opens global sidecar |
| Notifications | `data-shell-utility="notifications"` | Header | Global alerts only |
| Help | `data-shell-utility="help"` | Header | Product help |
| Account/preferences | `data-shell-utility="account"` | Header | Account + view prefs |
| View preferences menu | `data-view-preferences-menu` | Account menu | Theme/density only here |
| Workspace toolbar | `data-workspace-toolbar` | Page shell | Page-level actions |
| Table toolbar | `data-table-toolbar` | Data surface | Search/filter/bulk/columns |
```

**Step 2: Link the spec from Shell Family**

In `10_ditto_shell_family_spec.md`, add `19_ditto_shell_chrome_contract.md` to downstream references and add a short section:

```markdown
## Shell Chrome Contract

All shell families inherit the global chrome contract from `19_ditto_shell_chrome_contract.md`.
Shell family differences start below the global rail/header utility layer.
```

**Step 3: Link component roles**

In `13_ditto_component_spec.md`, add `Header Utility Bar`, `View Preferences Menu`, `Global Command Button`, and `Data Toolbar` under Shell / Workspace / Data components.

**Step 4: Update `DESIGN.md` prose**

Add a compact "Shell Chrome" subsection:

- Rail is domain navigation only.
- Header utilities are fixed and global.
- View preferences are account-menu contents.
- Local filter/search belongs to the workspace or data toolbar.

Do not change token YAML values.

**Step 5: Verify docs lint/format**

Run:

```bash
bunx biome check docs/designs/specs/19_ditto_shell_chrome_contract.md docs/designs/specs/10_ditto_shell_family_spec.md docs/designs/specs/13_ditto_component_spec.md DESIGN.md
```

Expected: PASS or Markdown ignored by Biome. If Biome reports formatting issues, fix only the reported files.

## Phase 2: Standardize React Shell Chrome

### Task 2.1: Fix UI Preference DOM Sync

**Files:**
- Modify: `src/features/shell/hooks/use-ui-preferences.ts`
- Test: `src/features/shell/hooks/use-ui-preferences.test.ts`

**Step 1: Make setters sync DOM**

Update `setTheme`, `setDensity`, and `toggleSidebarCollapsed` to compute the next full preference state and call `applyAttributesToDom` immediately.

Implementation shape:

```ts
setTheme: (theme: Theme) => {
	const { density, sidebarCollapsed } = get();
	set({ theme });
	applyAttributesToDom(theme, density, sidebarCollapsed);
},

setDensity: (density: Density) => {
	const { theme, sidebarCollapsed } = get();
	set({ density });
	applyAttributesToDom(theme, density, sidebarCollapsed);
},
```

Keep `applyThemeToDom` for backwards compatibility during this phase.

**Step 2: Run focused store test**

Run:

```bash
bun run test:run src/features/shell/hooks/use-ui-preferences.test.ts
```

Expected: PASS.

### Task 2.2: Create Header Utility Components

**Files:**
- Create: `src/features/shell/components/global-command-button.tsx`
- Create: `src/features/shell/components/header-utility-bar.tsx`
- Create: `src/features/shell/components/page-title-block.tsx`
- Create: `src/features/shell/components/view-preferences-menu.tsx`
- Create: `src/features/shell/components/view-preferences-menu.test.tsx`
- Modify: `src/features/shell/index.ts`

**Step 1: Implement `PageTitleBlock`**

Props:

```ts
interface PageTitleBlockProps {
	readonly title?: string;
	readonly subtitle?: string;
}
```

Behavior:

- Render nothing if no title.
- Render `h1` with title.
- Render subtitle only when provided.
- Use existing semantic color/radius/spacing tokens.

**Step 2: Implement `GlobalCommandButton`**

Props:

```ts
interface GlobalCommandButtonProps {
	readonly onOpenCommand?: () => void;
}
```

Required attributes:

```tsx
data-shell-utility="command"
aria-label="打开全局命令"
data-search-scope="global"
```

**Step 3: Implement `ViewPreferencesMenu`**

Use local React state. No new Popover dependency.

Required:

- Trigger button has `data-shell-utility="account"` and `aria-label="账户与视图偏好"`.
- Menu has `role="menu"` and `data-view-preferences-menu`.
- Density/theme choices use `role="menuitemradio"`.
- Click outside behavior may be deferred if tests cover trigger open and selection.

**Step 4: Implement `HeaderUtilityBar`**

Props:

```ts
interface HeaderUtilityBarProps {
	readonly onOpenCommand?: () => void;
	readonly onOpenCopilot?: () => void;
}
```

Render utilities in this exact order:

1. `GlobalCommandButton`
2. Copilot button with `data-shell-utility="copilot"`
3. Notifications button with `data-shell-utility="notifications"`
4. Help button with `data-shell-utility="help"`
5. `ViewPreferencesMenu`

**Step 5: Export new components**

Update `src/features/shell/index.ts`:

```ts
export { GlobalCommandButton } from "./components/global-command-button";
export { HeaderUtilityBar } from "./components/header-utility-bar";
export { PageTitleBlock } from "./components/page-title-block";
export { ViewPreferencesMenu } from "./components/view-preferences-menu";
```

**Step 6: Run component tests**

Run:

```bash
bun run test:run src/features/shell/components/view-preferences-menu.test.tsx
```

Expected: PASS.

### Task 2.3: Replace Header Inline Controls

**Files:**
- Modify: `src/features/shell/components/header.tsx`
- Modify: `src/features/shell/components/header.test.tsx`
- Modify: `src/features/shell/components/theme-switcher.tsx`
- Modify: `src/features/shell/components/theme-switcher.test.tsx`

**Step 1: Update `ShellHeader` imports**

Remove `ThemeSwitcher` import. Import:

```ts
import { HeaderUtilityBar } from "./header-utility-bar";
import { PageTitleBlock } from "./page-title-block";
```

**Step 2: Use `PageTitleBlock`**

Replace inline title markup with:

```tsx
<PageTitleBlock title={title} />
```

Do not introduce route metadata schema changes in this task.

**Step 3: Use `HeaderUtilityBar`**

Replace the current action controls block with:

```tsx
<HeaderUtilityBar onOpenCopilot={onOpenCopilot} />
```

**Step 4: Retire `ThemeSwitcher` safely**

Either:

- Remove exports and tests if no imports remain, or
- Keep it as a thin wrapper around `ViewPreferencesMenu` only if another module imports it.

Before deleting, run:

```bash
rg -n "ThemeSwitcher" src
```

Expected after cleanup: no production imports other than optional export/test references.

**Step 5: Run focused header tests**

Run:

```bash
bun run test:run src/features/shell/components/header.test.tsx src/features/shell/components/view-preferences-menu.test.tsx
```

Expected: PASS.

### Task 2.4: Make Rail Domain-Only

**Files:**
- Modify: `src/features/shell/components/rail.tsx`
- Modify: `src/features/shell/components/rail.test.tsx`

**Step 1: Remove bottom settings/user controls**

Delete `SettingsIcon`, `UserIcon`, and the bottom action block.

**Step 2: Add stable domain attributes**

Each domain link should include:

```tsx
data-rail-domain={domain.id}
```

**Step 3: Keep active behavior unchanged**

Do not change `DOMAINS` or active-domain logic.

**Step 4: Run rail tests**

Run:

```bash
bun run test:run src/features/shell/components/rail.test.tsx src/features/shell/components/app-shell.test.tsx
```

Expected: PASS.

## Phase 3: Normalize Prototype Shell Chrome

### Task 3.1: Update Shared Prototype CSS/JS For Utilities

**Files:**
- Modify: `docs/designs/specs/prototypes/shared/layout-base.css`
- Modify: `docs/designs/specs/prototypes/shared/prototype-toggles.css`
- Modify: `docs/designs/specs/prototypes/shared/theme-switcher.js`

**Step 1: Add shared header utility classes**

In `layout-base.css`, add stable classes:

```css
.header-utility-bar {
  display: flex;
  align-items: center;
  gap: var(--space-8);
}

.header-utility-btn {
  width: var(--header-btn-size);
  height: var(--header-btn-size);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-6);
  color: var(--icon-secondary);
  cursor: pointer;
}

.header-utility-btn:hover {
  background: var(--interaction-hover-subtle-bg);
  color: var(--icon-primary);
}
```

Use existing selectors where possible; do not duplicate if equivalent styles already exist.

**Step 2: Add view preferences menu styles**

In `prototype-toggles.css`, add:

```css
.view-preferences {
  position: relative;
}

.view-preferences-menu {
  display: none;
  position: absolute;
  top: calc(100% + var(--space-6));
  right: 0;
  min-width: 180px;
  padding: var(--space-8);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-8);
  background: var(--surface-overlay);
  z-index: 40;
}

.view-preferences[data-open="true"] .view-preferences-menu {
  display: block;
}
```

**Step 3: Add menu toggle behavior**

In `theme-switcher.js`, keep existing `data-set-density` / `data-set-theme` support and add:

```js
var prefsBtn = e.target.closest('[data-view-preferences-trigger]');
if (prefsBtn) {
  var root = prefsBtn.closest('.view-preferences');
  if (root) root.setAttribute('data-open', root.getAttribute('data-open') === 'true' ? 'false' : 'true');
  return;
}
```

**Step 4: Run prototype consistency test**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: still FAIL until page HTML is normalized.

### Task 3.2: Normalize Active Prototype Headers

**Files:**
- Modify active route prototypes under `docs/designs/specs/prototypes/page-*.html`
- Do not modify archived `page-ai-overview.html` or `page-ai-copilot.html` unless their focused tests require it.

**Active page inventory:**

- `page-home.html`
- `page-cross-market.html`
- `page-a-shares.html`
- `page-markets-screener.html`
- `page-watchlist.html`
- `page-markets-intelligence.html`
- `page-markets-calendar.html`
- `page-instrument-hub.html`
- `page-research.html`
- `page-factor-list.html`
- `page-factor-analysis.html`
- `page-strategy-list.html`
- `page-strategies-detail.html`
- `page-strategy-studio.html`
- `page-backtest-list.html`
- `page-backtest-result.html`
- `page-experiment-list.html`
- `page-universe-list.html`
- `page-trading-overview.html`
- `page-portfolio.html`
- `page-signals-inbox.html`
- `page-orders-ledger.html`
- `page-risk-center.html`
- `page-platform.html`
- `page-platform-settings.html`
- `page-agent-console.html`
- any remaining active page listed by `.edition-manifest.json`

**Step 1: Change Agent Console domain**

In `page-agent-console.html`, change:

```html
data-domain="ai"
```

to:

```html
data-domain="platform"
```

**Step 2: Remove rail utility controls**

For every active page, rail may contain only logo and five domain links. Remove:

- settings rail buttons
- user rail buttons
- `id="density-toggle"`
- `id="theme-toggle"`

**Step 3: Replace permanent header switchers**

Replace every header-level `switcher-group` density/theme cluster with this account menu pattern:

```html
<div class="view-preferences" data-open="false">
  <button class="header-utility-btn header-avatar" data-shell-utility="account" data-view-preferences-trigger aria-label="账户与视图偏好">
    C
  </button>
  <div class="view-preferences-menu" data-view-preferences-menu role="menu" aria-label="账户与视图偏好">
    <div class="view-preferences-section">
      <span class="view-preferences-label">密度</span>
      <button class="switcher-btn" data-set-density="dense" role="menuitemradio" aria-checked="false">紧</button>
      <button class="switcher-btn" data-set-density="compact" role="menuitemradio" aria-checked="true">标</button>
      <button class="switcher-btn" data-set-density="comfortable" role="menuitemradio" aria-checked="false">松</button>
    </div>
    <div class="view-preferences-section">
      <span class="view-preferences-label">主题</span>
      <button class="switcher-btn" data-set-theme="dark" role="menuitemradio" aria-checked="true">暗</button>
      <button class="switcher-btn" data-set-theme="light" role="menuitemradio" aria-checked="false">亮</button>
    </div>
  </div>
</div>
```

**Step 4: Add fixed utility attributes**

Every active prototype header should include:

```html
data-shell-utility="command"
data-shell-utility="copilot"
data-shell-utility="notifications"
data-shell-utility="help"
data-shell-utility="account"
```

If a page currently has no search, add a compact icon-only global command button rather than a large search field.

**Step 5: Mark search scopes**

Header command/search:

```html
data-shell-utility="command" data-search-scope="global"
```

Local filter search:

```html
data-table-toolbar="search"
```

or:

```html
data-workspace-action="filter"
```

**Step 6: Run consistency test**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: PASS after all active pages are normalized.

### Task 3.3: Run Representative Prototype Page Tests

**Files:**
- Existing prototype tests under `scripts/page-*-prototype.test.ts`

Run a representative shell-family set first:

```bash
bun run test:run \
  scripts/page-home-prototype.test.ts \
  scripts/page-markets-screener-prototype.test.ts \
  scripts/page-strategies-detail-prototype.test.ts \
  scripts/page-strategy-studio-prototype.test.ts \
  scripts/page-orders-ledger-prototype.test.ts \
  scripts/page-platform-settings-prototype.test.ts \
  scripts/page-agent-console-prototype.test.ts
```

Expected: PASS.

Then run all prototype tests:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts
```

Expected: PASS.

## Phase 4: Move Local Actions Into Workspace/Data Toolbars

### Task 4.1: Add Data Toolbar Primitive

**Files:**
- Create: `src/components/data/data-toolbar.tsx`
- Create: `src/components/data/data-toolbar.test.tsx`
- Modify: `src/components/data/index.ts`

**Step 1: Write failing tests**

Create tests for:

- `data-table-toolbar` attribute on root.
- Search input/button uses `data-table-toolbar="search"`.
- Filter button uses `data-table-toolbar="filter"`.
- Bulk actions appear only when `selectedCount > 0`.
- Column config/export actions are local toolbar actions, not shell utilities.

Test shape:

```tsx
render(
	<DataToolbar
		searchLabel="搜索标的"
		selectedCount={3}
		onSearch={() => undefined}
		onFilter={() => undefined}
		onExport={() => undefined}
	/>,
);

expect(screen.getByRole("toolbar", { name: "数据表工具栏" })).toHaveAttribute(
	"data-table-toolbar",
	"root",
);
expect(screen.getByRole("button", { name: "筛选" })).toHaveAttribute(
	"data-table-toolbar",
	"filter",
);
expect(screen.getByText("已选 3 项")).toBeInTheDocument();
```

**Step 2: Implement minimal primitive**

Props:

```ts
interface DataToolbarProps {
	readonly searchLabel?: string;
	readonly selectedCount?: number;
	readonly onSearch?: () => void;
	readonly onFilter?: () => void;
	readonly onColumns?: () => void;
	readonly onExport?: () => void;
}
```

Keep styling restrained and token-based.

**Step 3: Export component**

Update `src/components/data/index.ts`:

```ts
export { DataToolbar } from "./data-toolbar";
```

**Step 4: Run tests**

Run:

```bash
bun run test:run src/components/data/data-toolbar.test.tsx
```

Expected: PASS.

### Task 4.2: Document Page Action Placement Rules

**Files:**
- Modify: `docs/designs/specs/11_ditto_page_pattern_library.md`
- Modify: `docs/designs/specs/12_ditto_data_views_spec.md`
- Modify: `docs/designs/specs/19_ditto_shell_chrome_contract.md`

**Step 1: Add placement matrix**

Add:

```markdown
| Action | Placement |
|---|---|
| Global command/search | Header utility |
| Copilot | Header utility |
| Notifications | Header utility |
| Help | Header utility |
| Account/view preferences | Header utility |
| Export table | Data toolbar |
| Refresh table | Data toolbar or workspace toolbar |
| Filter table/list | Data toolbar |
| Column configuration | Data toolbar |
| Run backtest / execute screening | Workspace toolbar |
| Save/publish strategy | Studio header or workspace toolbar |
| Settings/config validation | Config workspace toolbar |
```

**Step 2: Run docs check**

Run:

```bash
bunx biome check docs/designs/specs/11_ditto_page_pattern_library.md docs/designs/specs/12_ditto_data_views_spec.md docs/designs/specs/19_ditto_shell_chrome_contract.md
```

Expected: PASS or Markdown ignored by Biome.

## Phase 5: Contract And Regression Verification

### Task 5.1: Run Focused React Checks

Run:

```bash
bun run test:run \
  src/features/shell/components/header.test.tsx \
  src/features/shell/components/rail.test.tsx \
  src/features/shell/components/view-preferences-menu.test.tsx \
  src/features/shell/hooks/use-ui-preferences.test.ts \
  src/components/data/data-toolbar.test.tsx
```

Expected: PASS.

### Task 5.2: Run Prototype Checks

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts
```

Expected: PASS.

### Task 5.3: Run Contract Generation

Run:

```bash
bun run generate-contracts
```

Expected: completes. Inspect generated drift:

```bash
git diff -- src/features/shell/page-contracts.generated.ts scripts/visual-audit.config.generated.mjs
```

Expected: no unexpected route/count changes from shell chrome normalization.

### Task 5.4: Run Full Gate

Run:

```bash
bun run check
```

Expected: PASS.

If it fails, classify:

- New shell/prototype failures: fix before completion.
- Pre-existing unrelated failures: document exact failing files and commands, but do not revert unrelated user work.

## Suggested Phase Checkpoints

Checkpoint 1:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Commit message:

```bash
test: add shell chrome consistency guardrails
```

Checkpoint 2:

```bash
bun run test:run src/features/shell/components/header.test.tsx src/features/shell/components/rail.test.tsx src/features/shell/hooks/use-ui-preferences.test.ts
```

Commit message:

```bash
feat: standardize react shell chrome
```

Checkpoint 3:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts
```

Commit message:

```bash
fix: align prototype shell chrome
```

Checkpoint 4:

```bash
bun run check
```

Commit message:

```bash
docs: define shell chrome contract
```

## Acceptance Criteria

- Active prototypes use only five IA domains.
- `page-agent-console.html` is Platform domain, not AI domain.
- Active prototype rails contain only five product domain links.
- Active prototype headers expose fixed utility attributes for command, Copilot, notifications, help, and account.
- Theme/density controls exist only inside `data-view-preferences-menu`.
- React `Rail` has no settings/user/theme/density controls.
- React `ShellHeader` uses `HeaderUtilityBar` and no permanent `ThemeSwitcher` segmented controls.
- `useUIPreferences` setters sync DOM attributes immediately.
- Local search/filter/export/columns actions are represented by workspace or data toolbar semantics, not shell utilities.
- Focused React tests pass.
- Prototype consistency and page prototype tests pass.
- `bun run check` passes before declaring implementation complete.
