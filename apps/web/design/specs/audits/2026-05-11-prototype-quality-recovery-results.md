# Prototype Quality Recovery Results

## Scope

- Active route prototypes: 28
- Root superseded specimens: 0
- Removed specimens: 1
- Archive specimens: 2
- Token showcase: 1

## Fixed Risks

- High-risk trading and approval confirmations now include impact, before/after, evidence, audit, recovery, cancel, and confirm controls.
- Every active route has one dominant primary answer region.
- Dense pages use explicit action tiers and cap primary actions.
- Decorative visual noise was reduced without lowering information density.
- Final polish contract now blocks thick colored side borders, root superseded console specimens, and low-chroma A-share heatmap regressions.
- A-share heatmap uses explicit OKLCH red-up / green-down stepped colors while preserving direction symbols and accessible labels.
- `page-agent-console.html` was removed from the root release surface; `page-agent-console-v2.html` is the canonical `/platform/agents` prototype.
- Viewport obstruction coverage now verifies visible interactive targets, fixed/sticky clipping, and dense data text fit across release gate viewports.
- Strategy Studio header actions, Agent Console v2 panel scrolling, Cross Market right rail clipping, Markets Intelligence stale state variants, and dense table readability were stabilized.

## Verification

- `bun run prototype:gates`: pass for every active route prototype.
- `bunx vitest run scripts/prototype-high-risk-confirmation-contract.test.ts scripts/prototype-primary-answer-contract.test.ts scripts/prototype-action-tier-contract.test.ts`: pass, 3 test files, 8 tests.
- `bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts --testTimeout=180000 --hookTimeout=180000`: pass, 3 test files, 116 tests.
- `bun run check`: pass, 150 test files, 1803 tests.
- `bunx vitest run scripts/prototype-final-polish-contract.test.ts scripts/prototype-viewport-obstruction-contract.test.ts --testTimeout=180000 --hookTimeout=180000`: pass, 2 test files, 6 tests.
- `bun run prototype:gates -- --prototype prototype/page-a-shares.html --viewport VP-COMPACT=1366x768 --out-dir test-results/ditto-design-cycle-gates/a-shares-red-green-check`: pass.
- `bun run prototype:gates -- --prototype prototype/page-portfolio.html --viewport VP-COMPACT=1366x768 --out-dir test-results/ditto-design-cycle-gates/portfolio-fit-check`: pass.
- `bun run prototype:gates -- --prototype prototype/page-factor-list.html --viewport VP-NARROW=1200x800 --out-dir test-results/ditto-design-cycle-gates/factor-list-fit-check`: pass.
- `bun run prototype:gates -- --prototype prototype/page-watchlist.html --viewport VP-NARROW=1200x800 --out-dir test-results/ditto-design-cycle-gates/watchlist-fit-check`: pass.

## Release UX Score Expectation

Expected Nielsen score after remediation: 29 to 32 out of 40.

Remaining non-blockers:

- Some pages remain intentionally desktop-only.
- Superseded `page-agent-console.html` is intentionally removed rather than archived, per 2026-05-12 release decision.
- Token showcase is not part of route release UX.
