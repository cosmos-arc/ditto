# Prototype Pixel Replica Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore prototype-backed pages through page-by-page normalized measurement, layout repair, and screenshot verification until each page matches its HTML prototype instead of only passing token and unit checks.

**Architecture:** Treat HTML prototypes as visual contracts, not inspiration. Add a visual audit harness that normalizes prototype tooling, captures bounding rects and screenshots for each route, then fix pages one at a time from shell geometry to section rhythm to micro styles. Keep production components in `src/`; keep audit selectors and generated evidence outside runtime code.

**Tech Stack:** Bun, Vite, React 19, TanStack Router, Tailwind CSS v4 tokens, Vitest/RTL, Playwright, existing HTML prototypes in `prototype`.

---

## Current Diagnosis

The previous recovery plan completed the engineering track, but it did not close the visual track. The key mistake was treating "layout components exist", "tokens are legal", and "`bun run check` passes" as proof of prototype fidelity.

Observed issues from April 11 measurement at `1536x900`:

| Page | Prototype Geometry | Current React Geometry | Impact |
|---|---|---|---|
| `/` Home | normalized shell rows `68 / 32 / 800`, columns `56 / 1160 / 320`; decision banner `1126x147`; queue `1128x191` | global shell rows `68 / 808 / 24`; inner rows `28 / 780`; decision banner `1128x216`; queue `1128x266` | Global status bar and guessed `max-h-[66%]` distort vertical rhythm. |
| `/trading` | rows `68 / 36 / 134 / 638`; banner is its own grid row; decision `1422x100`; main starts at `y=238` | rows `68 / 34 / 554 / 220`; banner lives inside main flow; decision `1148x148` at `y=227`; main starts at `y=102` | Page order and row allocation differ from prototype. |
| `/platform` | rows `68 / 36 / 796`; columns `56 / 1140 / 340` | global shell adds 24px status row; health is `33px` instead of `36px`; main/detail `775px` | Shell family is close, but global AppShell and strip density break pixel alignment. |
| `/ai` | rows `68 / 32 / 752 / 24`; columns `56 / 1160 / 320`; has sidebar and status bar | command-center rows `85 / 723`; no sidebar; pulse is not `[data-slot="pulse-strip"]` | Contract and implementation understate the prototype surface. |
| `/markets` | `shell-radar` is a scroll/workspace prototype; `.shell-body` height `1677`, workspace `1480x1249`, right rail `300px` | fixed inner analytical grid `32 / 556 / 220` inside 808px content | This is a different page model, not a padding problem. |

Two process bugs must be fixed first:

- Prototype default view uses `height: calc(100vh - 35px)` because of `.proto-nav`. Visual audit must inject normalization CSS that hides `.proto-nav` and makes `#default-view` `100vh`, otherwise all measurements are off by 35px.
- `docs/plans/2026-04-10-milestone1-baseline-report.md` is stale: it still says `/trading/signals`, `/trading/orders`, and `/ai/agents` use the wrong layout, while current code already uses `OpsConsoleLayout` and `StudioLayout`.

## Non-Negotiable Rules

- One prototype-backed page at a time: measure, fix, verify, document, then move on.
- No guessed percentages such as `max-h-[66%]` unless the prototype uses that strategy.
- No "looks close" approvals. Each page needs L1 token checks, L2 bounding-rect comparison, and L3 screenshot diff.
- Shared layout changes require explicit review because they can alter every page.
- Do not add dependencies for image diff. If pixel diff automation is needed, implement it with Playwright canvas comparison first.

## Accepted Tiny Tolerance

Tiny error is acceptable only for browser rounding, font antialiasing, and dynamic data that cannot be made deterministic. It is not permission for visible layout drift.

| Layer | Gate |
|---|---|
| L2 structural geometry | Shell, header, strip, main/sidebar/detail, and major named regions must be within `2px` for `x/y/w/h`. No percentage-based pass for these regions. |
| L2 content-driven panels | Panel heights may differ by up to `4px` only when caused by text/font rendering or synchronized data limits; every exception must be recorded in the page audit report. |
| Spacing / typography | Padding, gap, font-size, line-height, radius, and border width should match exactly in computed CSS. A `1px` exception is allowed only for subpixel rounding. |
| Color / surface | Token-backed colors should resolve to the same computed value. Any intentional token substitution must be called out in the report. |
| L3 screenshot diff | Target similarity is `>= 99%`; hard floor is `>= 98.5%` after masking dynamic clocks, cursor/caret, animated glows, and live counters. Any contiguous visible mismatch larger than `8x8px` requires review even if total similarity passes. |

## Task 1: Build Visual Audit Harness

**Files:**
- Create: `scripts/visual-audit.config.mjs`
- Create: `scripts/visual-audit.mjs`
- Modify: `package.json`
- Output: `docs/review/visual-audit/`

**Step 1: Write the route config**

Create a config containing every prototype-backed route, its React route, HTML file, and initial selectors. Keep this outside `src` so audit selectors do not become runtime API.

```js
export const PROTOTYPE_NORMALIZE_CSS = `
  .proto-nav { display: none !important; }
  #default-view {
    height: 100vh !important;
    min-height: 100vh !important;
    overflow: hidden !important;
  }
  #default-view > [class*="shell"],
  #default-view > .ai-shell,
  #default-view > .intel-shell,
  #default-view > .risk-shell {
    height: 100vh !important;
    min-height: 0 !important;
    flex: 0 0 auto !important;
  }
  #default-view > .status-bar {
    height: 24px !important;
    flex: 0 0 auto !important;
  }
`;

export const VISUAL_AUDIT_PAGES = [
  {
    route: "/",
    name: "home",
    prototype: "page-home.html",
    prototypeTargets: {
      shell: ".shell-home",
      strip: ".shell-pulse",
      main: ".shell-main",
      sidebar: ".shell-sidebar",
      decision: ".decision-banner",
      queue: ".panel-grow",
      secondary: ".shell-secondary",
    },
    reactTargets: {
      shell: "#root > div",
      layout: "#root > div > div:nth-child(3) > div",
      strip: "[data-slot='pulse-strip']",
      sidebar: "[data-slot='sidebar-rail']",
      decision: "[data-slot='decision-banner']",
      queue: "[data-slot='panel']",
    },
  },
  // Add the remaining 15 prototype-backed routes before using this for gating.
];
```

**Step 2: Implement metric capture**

In `scripts/visual-audit.mjs`, use Playwright to open `--prototype-base` and `--react-base`, inject normalization CSS into prototype pages, and write one JSON file per route:

```bash
bun scripts/visual-audit.mjs --route / --react-base http://127.0.0.1:5176 --prototype-base http://127.0.0.1:8766
```

Expected output:

```text
docs/review/visual-audit/home/metrics.json
docs/review/visual-audit/home/prototype.png
docs/review/visual-audit/home/react.png
docs/review/visual-audit/home/report.md
```

**Step 3: Add the package script**

Add:

```json
"visual:audit": "bun scripts/visual-audit.mjs"
```

**Step 4: Verify**

Run:

```bash
bun run visual:audit -- --route / --react-base http://127.0.0.1:5176 --prototype-base http://127.0.0.1:8766
bun run check
```

Expected: audit artifacts are written, and `bun run check` passes.

**Step 5: Commit**

```bash
git add package.json scripts/visual-audit.config.mjs scripts/visual-audit.mjs docs/review/visual-audit/home
git commit -m "test: add prototype visual audit harness"
```

## Task 2: Fix the Visual Contract Data

**Files:**
- Modify: `src/features/shell/page-contracts.ts`
- Modify: `src/features/shell/page-contracts.test.ts`
- Modify: `docs/plans/2026-04-10-milestone1-baseline-report.md`

**Step 1: Update contract facts**

Fix `/ai` to include the prototype sidebar if the team confirms that `page-ai-overview.html` remains the fidelity target:

```ts
{
  route: "/ai",
  pagePattern: "global-command-center",
  shellFamily: "command-center",
  prototypeSource: "prototype-backed",
  prototypeRef: "prototype/page-ai-overview.html",
  requiredSlots: ["pulse", "main", "sidebar"],
  requiredStates: [...UNIVERSAL_STATES, "no-agents", "has-pending"],
}
```

**Step 2: Add a stale-report correction**

Update the milestone report so it no longer says `/trading/signals`, `/trading/orders`, and `/ai/agents` currently use the wrong layout. Mark them as "corrected structurally, pending pixel audit".

**Step 3: Verify**

Run:

```bash
bun run test:run -- src/features/shell/page-contracts.test.ts
bun run check
```

Expected: page contract tests and full checks pass.

**Step 4: Commit**

```bash
git add src/features/shell/page-contracts.ts src/features/shell/page-contracts.test.ts docs/plans/2026-04-10-milestone1-baseline-report.md
git commit -m "docs: align page contracts with current prototype targets"
```

## Task 3: Decide and Repair Global AppShell Status Bar

**Files:**
- Modify: `src/features/shell/components/app-shell.tsx`
- Modify: `src/features/shell/components/app-shell.test.tsx`
- Modify: `src/features/shell/layouts/*.tsx` as needed
- Modify: page components only after the shared decision is approved

**Decision needed before implementation:** pixel-perfect matching requires removing the unconditional global `StatusBar` from `AppShell`, or making it page-family controlled. Home, Trading, Platform, and Markets prototypes do not have the same global status row that React currently adds. AI Overview does have a status row in the prototype.

Recommended option: make `AppShell` a two-row global shell (`rail + header + content`) and let page layouts opt into a `status` slot when their prototype has it.

**Step 1: Write the failing test**

Update `app-shell.test.tsx` so the default shell no longer requires `StatusBar`:

```ts
it("does not reserve a global status row by default", () => {
  const { container } = render(<AppShell>content</AppShell>);
  const shell = container.firstElementChild;
  expect(shell?.className).toContain("grid-rows-[var(--height-header)_1fr]");
  expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
});
```

**Step 2: Implement the minimal shell change**

Remove the default `<StatusBar />` from `AppShell`, and remove the third global row.

**Step 3: Add page-owned status only where prototype-backed pages need it**

Start with `/ai` because `page-ai-overview.html` includes a `.status-bar`. Do not add it back globally.

**Step 4: Verify**

Run:

```bash
bun run test:run -- src/features/shell/components/app-shell.test.tsx src/features/shell/layouts/shell-layouts.test.tsx
bun run visual:audit -- --route /
bun run visual:audit -- --route /ai
bun run check
```

Expected: Home no longer loses 24px to a global status bar; AI still has a status area matching prototype.

**Step 5: Commit**

```bash
git add src/features/shell/components src/features/shell/layouts src/features/ai/components
git commit -m "fix(shell): make status bar page-owned for prototype fidelity"
```

## Task 4: Page 1 — Home Pixel Repair

**Files:**
- Modify: `src/features/home/components/home-page.tsx`
- Modify: `src/features/home/components/banner-section.tsx`
- Modify: `src/features/home/components/priority-queue-section.tsx`
- Modify: `src/features/home/components/pulse-section.tsx`
- Test: `src/features/home/components/home-components.test.tsx`

**Target geometry at `1536x900`:**

```text
shell-home:      1536x900
shell-pulse:     x=56 y=68  w=1480 h=32
shell-main:      x=56 y=100 w=1160 h=800 padding=16 gap=24
shell-sidebar:   x=1216 y=100 w=320 h=800
decision-banner: x=73 y=117 w=1126 h=147
panel-grow:      x=72 y=277 w=1128 h=191
shell-secondary: x=72 y=647 w=1128 h=237
```

**Step 1: Write the failing visual audit**

Run:

```bash
bun run visual:audit -- --route /
```

Expected before fix: `decision-banner` height is about `216px`, queue panel height about `266px`, pulse strip `28px`.

**Step 2: Remove guessed height strategy**

Replace `max-h-[66%]` in `home-page.tsx` with a layout strategy derived from prototype measurements. The prototype is content-driven for banner, then flex-grow queue, then flex-grow secondary, with explicit main gap `24px` and inner primary gap `12px`.

**Step 3: Restore pulse strip height**

Make Home pulse use `32px`, not `calc(var(--density-strip-height) - 4px)`, unless density mode has an explicit prototype variant.

**Step 4: Trim DecisionBanner content to prototype rhythm**

Home's judgment text and metric count must fit the prototype's `147px` banner. Move long explanatory copy out of the banner or shorten to the prototype structure.

**Step 5: Verify**

Run:

```bash
bun run test:run -- src/features/home/components/home-components.test.tsx
bun run visual:audit -- --route /
bun run check
```

Expected: L2 width/height deltas for Home structural targets are within `2px`; content-driven panel height exceptions, if any, are within `4px` and recorded.

**Step 6: Commit**

```bash
git add src/features/home docs/review/visual-audit/home
git commit -m "fix(home): align command center with prototype geometry"
```

## Task 5: Page 2 — AI Overview Pixel Repair

**Files:**
- Modify: `src/features/ai/components/ai-page.tsx`
- Modify: `src/features/ai/components/ai-pulse-strip.tsx`
- Modify: `src/features/ai/components/agent-quick-view.tsx`
- Modify: `src/features/ai/components/copilot-quick-view.tsx`
- Test: `src/features/ai/components/ai-components.test.tsx`

**Target geometry at `1536x900`:**

```text
ai-shell:      columns 56 / 1160 / 320; rows 68 / 32 / 752 / 24
ai-pulse:      x=56 y=68  w=1480 h=32
ai-main:       x=56 y=100 w=1160 h=752 padding=16
shell-sidebar: x=1216 y=100 w=320 h=752
status-bar:    x=56 y=852 w=1480 h=24
```

**Step 1: Write failing slot test**

Ensure `/ai` renders pulse, main, sidebar, and status equivalents.

**Step 2: Add the missing sidebar**

Populate the sidebar with AI status, active model/resource indicators, pending approvals, and recent outputs from the prototype.

**Step 3: Fix pulse height**

Ensure the AI pulse strip is a 32px strip with `[data-slot="pulse-strip"]` or an audit target that maps to its prototype selector.

**Step 4: Verify**

Run:

```bash
bun run test:run -- src/features/ai/components/ai-components.test.tsx
bun run visual:audit -- --route /ai
bun run check
```

Expected: `/ai` no longer has an 85px pulse row, and sidebar exists.

**Step 5: Commit**

```bash
git add src/features/ai src/features/shell/page-contracts.ts docs/review/visual-audit/ai
git commit -m "fix(ai): restore overview sidebar and status layout"
```

## Task 6: Page 3 — Trading Pixel Repair

**Files:**
- Modify: `src/features/shell/layouts/analytical.layout.tsx` or create a page-specific trading variant
- Modify: `src/features/trading/components/trading-page.tsx`
- Modify: `src/features/trading/components/trading-session-strip.tsx`
- Test: `src/features/trading/components/trading-components.test.tsx`

**Target geometry at `1536x900`:**

```text
trading shell rows: 68 / 36 / 134 / 638
trading banner:     x=56 y=104 w=1480 h=134
decision-banner:    x=85 y=113 w=1422 h=100
main-content:       x=56 y=238 w=1180 h=638 padding=16
activity-stack:     x=1236 y=238 w=300 h=638
```

**Step 1: Write failing layout test**

Test that Trading has a dedicated banner slot, not a banner inside main flow.

**Step 2: Add `banner` support**

Preferred: extend `AnalyticalLayout` with an optional `banner` slot only if other analytical pages do not regress. If this creates ambiguity, create `TradingAnalyticalLayout`.

**Step 3: Move `DecisionBanner` into the banner slot**

Keep `EquityPnlBlock`, `PositionsSummary`, and `OrdersPanel` in the main content with prototype flex ratios.

**Step 4: Verify**

Run:

```bash
bun run test:run -- src/features/trading/components/trading-components.test.tsx src/features/shell/layouts/shell-layouts.test.tsx
bun run visual:audit -- --route /trading
bun run check
```

Expected: Trading decision banner height is about `100px`, and main content begins at `y=238`.

**Step 5: Commit**

```bash
git add src/features/trading src/features/shell/layouts docs/review/visual-audit/trading
git commit -m "fix(trading): restore prototype banner row"
```

## Task 7: Page 4 — Platform Pixel Repair

**Files:**
- Modify: `src/features/platform/components/platform-page.tsx`
- Modify: `src/features/platform/components/health-strip.tsx`
- Test: `src/features/platform/components/platform-components.test.tsx`

**Target geometry at `1536x900`:**

```text
shell-ops:  columns 56 / 1140 / 340; rows 68 / 36 / 796
ops-health: x=56 y=68  w=1480 h=36 padding=6px 16px
ops-main:   x=56 y=104 w=1140 h=796
ops-detail: x=1196 y=104 w=340 h=796
```

**Step 1: Audit current Platform**

Run:

```bash
bun run visual:audit -- --route /platform
```

Expected before fix: health strip is about `33px`, and global status bar still affects content if Task 3 is incomplete.

**Step 2: Match health strip density**

Set Platform health strip to the prototype's 36px height and 6px/16px padding.

**Step 3: Verify**

Run:

```bash
bun run test:run -- src/features/platform/components/platform-components.test.tsx
bun run visual:audit -- --route /platform
bun run check
```

Expected: L2 structural geometry is within `2px`; any content-driven exception is within `4px` and recorded.

**Step 4: Commit**

```bash
git add src/features/platform docs/review/visual-audit/platform
git commit -m "fix(platform): align ops console strip and detail geometry"
```

## Task 8: Page 5 — Markets Radar Repair

**Files:**
- Modify: `src/features/markets/components/markets-page.tsx`
- Modify or create: `src/features/shell/layouts/radar.layout.tsx`
- Modify: `src/features/shell/layouts/shell-layouts.test.tsx`
- Test: `src/features/markets/components/markets-page.test.tsx`

**Target geometry at `1536x900`:**

```text
shell-radar:     1536x900 flex shell
shell-body:      x=56 y=0 w=1480 h=1677 padding-bottom=24
context-bar:     x=56 y=68 w=1480 h=25
shell-workspace: x=56 y=130 w=1480 h=1249 grid cols roughly 1320.55 / 300
right-rail:      x=1377 y=130 w=300 h=691
tab-band:        starts at y=1380
```

**Step 1: Confirm page model**

Markets is a scrolling radar prototype, not the current fixed analytical grid. Confirm whether `/markets` should follow `page-cross-market.html` exactly. If yes, do not keep it in the generic `AnalyticalLayout`.

**Step 2: Add a Radar layout variant**

Create a page-specific layout that supports `shell-body`, `context-bar`, `shell-workspace`, `right-rail`, and `tab-band` geometry.

**Step 3: Move current panels into prototype zones**

Map MarketCardGrid, MacroDriversBar, CapitalRotationTable, CrossMarketMatrix, and right rail sections to the prototype zones rather than the generic `main/activity/analysis` split.

**Step 4: Verify**

Run:

```bash
bun run test:run -- src/features/markets/components/markets-page.test.tsx src/features/shell/layouts/shell-layouts.test.tsx
bun run visual:audit -- --route /markets
bun run check
```

Expected: `/markets` is allowed to be taller than viewport like the prototype; do not force it into the 808px inner grid.

**Step 5: Commit**

```bash
git add src/features/markets src/features/shell/layouts docs/review/visual-audit/markets
git commit -m "fix(markets): restore radar workspace layout"
```

## Task 9: Continue Prototype-Backed Pages One by One

Run the same loop for the remaining prototype-backed pages in this order:

| Order | Route | Prototype | Primary Risk |
|---:|---|---|---|
| 6 | `/research` | `page-research.html` | Analysis band and factor table density. |
| 7 | `/trading/signals` | `page-signals-inbox.html` | Ops health/detail geometry and selected row state. |
| 8 | `/trading/orders` | `page-orders-ledger.html` | Ledger tab strip, order active state, detail panel. |
| 9 | `/trading/risk` | `page-risk-center.html` | Analytical risk layout and threshold visualizations. |
| 10 | `/markets/screener` | `page-markets-screener.html` | Catalog toolbar/detail and table density. |
| 11 | `/markets/intelligence` | `page-markets-intelligence.html` | Missing strip/activity slots in current implementation. |
| 12 | `/research/regime` | `page-regime-monitor.html` | Current implementation is main-only; prototype requires analytical zones. |
| 13 | `/research/strategy-studio` | `page-strategy-studio.html` | Studio grid and inspector/log area. |
| 14 | `/ai/copilot` | `page-ai-copilot.html` | Studio grid differs from prototype's session/conversation/context shell. |
| 15 | `/ai/agents` | `page-agent-console.html` | Studio shell exists, but main centered inspector is not prototype composition. |
| 16 | `/instruments/$id` | `page-instrument-hub.html` | Object hub meta/tabs/bottom and dense data panels. |

For each page:

1. Add route selectors to `scripts/visual-audit.config.mjs`.
2. Run `bun run visual:audit -- --route <route>`.
3. Record prototype target metrics in the generated `report.md`.
4. Write or update focused component tests for required slots/states.
5. Fix the page without touching unrelated pages.
6. Re-run visual audit until L2 structural deltas are within `2px` and content-driven exceptions are within `4px`.
7. Run `bun run check`.
8. Commit that page only.

## Task 10: Spec-Only Family Consistency Pass

**Files:**
- Modify page files only after all prototype-backed pages are stable:
  - `src/features/markets/components/a-shares-page.tsx`
  - `src/features/markets/components/calendar-page.tsx`
  - `src/features/backtest/components/backtest-page.tsx`
  - `src/features/research/components/factor-page.tsx`
  - `src/features/strategy/components/strategy-detail-page.tsx`

**Step 1: Choose family references**

Use:

- `/markets/a-shares` → `/markets`
- `/markets/calendar` → `/markets/screener`
- `/research/backtest/$id`, `/research/factors/$id`, `/strategies/$id` → `/instruments/$id`

**Step 2: Audit against family, not non-existent HTML**

Do not invent pixel targets. Use family geometry and component grammar from the finished prototype-backed pages.

**Step 3: Verify**

Run:

```bash
bun run check
```

Expected: no spec-only page is main-only unless its family reference proves it should be.

## Final Gate

Run:

```bash
bun run check
bun run visual:audit -- --all
```

Completion criteria:

- `bun run check` passes.
- All 16 prototype-backed routes have metrics, screenshots, and reports under `docs/review/visual-audit/`.
- Every L2 structural bounding-rect target is within `2px` after prototype normalization; content-driven panel exceptions are within `4px` and documented.
- L3 screenshot similarity is at least `98.5%` for each page, with `99%+` as the working target.
- `docs/plans/2026-04-10-milestone1-baseline-report.md` and any completion docs no longer claim obsolete states.

## Execution Notes

- Start React dev server with `bun run dev --host 127.0.0.1`; use the printed port.
- Start prototype server from `prototype` with `python3 -m http.server 8766 --bind 127.0.0.1`.
- Keep generated visual artifacts in `docs/review/visual-audit/`.
- If a page needs a shared layout change, stop and review blast radius before touching the layout.
- The first real implementation decision is whether to remove or page-scope the global `StatusBar`; without that, Home and Platform cannot be pixel-perfect.
