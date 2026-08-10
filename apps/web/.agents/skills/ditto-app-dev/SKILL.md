---
name: ditto-app-dev
description: Use for implementing or materially changing Ditto React pages, shared UI, interactions, responsive layouts, design-token consumption, page-contract integration, or prototype-to-production visual verification.
---

# Ditto App Development

Implement approved product and page contracts as tested React behavior.

## Read first

1. Read `AGENTS.md`, `PRODUCT.md`, `DESIGN.md`, the route, owning feature, public exports and closest tests.
2. For a contract-driven page, read its JSON in `docs/contracts/pages/` and the referenced blueprint/prototype.
3. Load phase details only as needed:
   - [architect.md](references/architect.md) for component/state placement.
   - [implement.md](references/implement.md) for TDD and layout implementation.
   - [polish.md](references/polish.md) for interaction and visual refinement.
   - [verify.md](references/verify.md) for token/layout/pixel evidence.
   - [ship.md](references/ship.md) for final evidence and manifest updates.
   - [iteration-protocol.md](references/iteration-protocol.md) for bounded repeat work.

## Workflow

1. **Measure** — resolve contract metrics, states, selectors, responsive behavior and existing implementation evidence.
2. **Architect** — identify capability owner, consumers, component boundaries, server/client/local state and public exports.
3. **RED** — add the smallest user-visible, accessibility or contract test that fails for the intended reason.
4. **GREEN** — implement the smallest coherent React/TypeScript change and rerun the target test.
5. **Refactor** — reduce duplication and expose only justified public APIs while keeping focused tests green.
6. **Polish** — align tokens, typography, density, interaction feedback, focus, motion and responsive behavior.
7. **Verify** — run engineering gates plus browser evidence when layout/visual behavior changed.

## Implementation rules

- Keep API access typed and behind feature adapters/hooks; do not copy backend schemas.
- Use TanStack Query for server state, Zustand for cross-page client preferences and local state for local interaction.
- Cover loading, empty, error and stale states. Destructive actions require explicit confirmation.
- Prefer public feature barrels. `components/ui` and `lib` never depend on feature code.
- Consume values from `src/styles/design-tokens/`. Inline style is limited to data-driven geometry, never static brand styling.
- Treat prototype literals as evidence, below `DESIGN.md` and token sources. Record justified prototype deviations.

## Verification

- Focused test while iterating: `bunx vitest run <test-file>`.
- Standard source gate: `bun run check`.
- Token/style work: `bun run audit:tokens && bun run build:tokens:check`.
- Visual/contract work: target Playwright/prototype checks and screenshots at contract viewports.
- Release candidate: `bun run ci`.

Report RED/GREEN evidence, affected contract, visual evidence, skipped gates and remaining risks.
