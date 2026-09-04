# Integrated Product Beta frontend acceptance

Date: 2026-08-30
Scope: local single-operator A-share ETF workstation; paper execution only.

## Verdict

PASS for the frontend scope of P0–P5. The delivery board has 33/33 product routes,
32/32 prototype-backed page contracts, and 79/79 mapped overlays. Core overlays are
real React interactions rather than `prototype-only` placeholders. Unsupported
backend mutations fail closed or are explicitly local-only; no UI action represents
a real broker write.

## Functional and UI evidence

- Shared `PageActionOverlay` and page-specific overlays cover all previously
  prototype-only actions. Watchlist membership and saved screener presets are clearly
  labelled local browser state; exports create CSV/JSON; navigation actions use real
  routes.
- Orders, Risk, Watchlist, Research and the remaining product pages use their frozen
  page-contract geometry and existing design system. The visual gate returns nonzero
  on threshold breaches.
- In the in-app browser, the Watchlist add drawer received initial focus, `Escape`
  closed it, and focus returned to the invoking “批量删除” button. The final browser
  state had no console errors. The behavior is protected by the shared overlay test.

## Visual matrix

| Contract viewport | Result | Evidence |
|---|---:|---|
| 1536×900 primary | 32/32 PASS, 0 final warnings | 29 initial passes plus the 3-page Orders/Risk/Watchlist rerun in `visual-audit-1536-rerun/` |
| 1366×768 compact | 32/32 PASS, 0 warnings | `visual-audit-1366/` |
| 1200×800 declared compact | 22/22 PASS, 0 warnings | `visual-audit-1200-declared-all/` |

The broad exploratory `visual-audit-1200/` directory also contains routes whose
contracts do not declare 1200×800 support. It is diagnostic input, not the acceptance
denominator. Every route that does declare that viewport is included in the clean
22/22 evidence directory above.

## Current gates

`bun run ci` passed after the final UI and focus changes:

- check: 181 test files, 1457 tests; route, prototype freeze, product board,
  architecture and Harness gates passed;
- coverage: 179 test files, 1433 tests; aggregate lines 85.3%;
- prototype suite: 51 files, 710 tests;
- production build: passed; Vite emitted only its non-blocking large-chunk warning.

The page-contract generator and validator also passed with 32/32 contracts, and
`git diff --check` passed. This report does not claim fresh Tushare/FRED data, a real
broker connection, or production deployment.
