# Data Products React-only implementation feedback

- React route: `/platform/data-products`
- Verification: 2026-08-30
- This route was introduced after the frozen prototype edition and is intentionally recorded in `reactOnlyRoutes`; no unrelated prototype is claimed as its visual source.
- The Catalog workspace exposes 19 R2 hard-scope products and six keyboard-accessible views: overview, coverage, quality, runs/repair, evidence/license, and operations governance.
- Production and mock modes use the same `/api/v1/data-products/*` and `/api/v1/ingestion/catalog/*` paths. Loading, empty, error, selected-product, coverage-gap, DQ/PIT evidence, remediation, fallback, promotion, expired-authority, and exact-confirmation behavior are covered by the referenced React tests.
- Operations bind dataset identity and an operator-visible trade date before requesting projections. Approval and lifecycle actions show the exact backend payload, authority hash, expiry, actor, and typed confirmation phrase; no client-side shortcut executes a write.
- Manual in-app browser verification covered the catalog and Operations views at the desktop compact layout with no missing content or horizontal obstruction. The catalog preserves a scrollable main table and a fixed evidence panel; narrower layouts reflow the Catalog shell instead of compressing evidence text.
- No new data-product service, client-side certification calculation, implicit latest scope, or duplicate governance command was introduced.
