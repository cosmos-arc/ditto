# Prototype Design Remediation Review — 2026-04-28

## Summary

The Edition v1 prototype set now has one landing-ready contract boundary:

- Active route candidates: 27
- Archived specimens: `ai-overview`, `ai-copilot`
- Auxiliary specimen: `token-showcase`
- Active overlay registry: 93 prototype overlays / 93 contract overlays

The remediation is prototype-design scoped. Runtime React implementation was not manually changed; generated contract artifacts were refreshed from the page contracts.

## Candidate Pool

`ai-overview` and `ai-copilot` are retained as AI interaction specimens and are no longer active route candidates. Their manifest entries are marked `archived-specimen`, with deprecated route status, archived overlay status, and not-applicable visual audit status.

`.arch-manifest.json` now records the explicit prototype inventory:

- 27 active route prototypes
- 2 archived specimens
- 1 auxiliary token specimen

## Shell Drift

Fixed shell-family drift across manifest and contracts:

- `cross-market`: `analytical` -> `radar`
- `agent-console`: `ops-console` -> `studio`
- `experiment-list`: `ops-console` -> `catalog`

The affected contracts now use selectors that match their actual prototype shell structure.

## Overlay Registry

Baseline consistency test showed 93 active overlay ids and 87 missing contract registrations, meaning only 6 were registered before this remediation. After the contract pass, all 93 active overlay ids are represented in `docs/contracts/pages/*.contract.json`.

Every active overlay gallery specimen now carries an explicit `data-overlay-ref`, and all active pages keep `overlayStatus: "triggerable"` because every active route prototype has at least one default-flow overlay trigger.

## Overlay Grammar

Active prototypes now use the shared overlay grammar:

- `overlay-backdrop`
- `overlay-surface`
- `overlay-surface--drawer`
- `overlay-surface--sheet`
- `overlay-surface--modal`
- `overlay-header`
- `overlay-body`
- `overlay-actions`
- `overlay-field`

Legacy surface classes (`overlay-sheet`, `overlay-drawer`, `drawer-sheet`, `modal-sheet`) were removed from active route prototypes. Archived AI specimens were also migrated to keep their focused prototype tests green.

## Typography And Color

Typography governance now treats the current Edition v1 scale as a 9-step truth:

`10 / 11 / 12 / 13 / 14 / 16 / 18 / 20 / 24`

The consistency guard rejects current-edition language that marks `11`, `18`, or `20` as forbidden/deprecated. Negative letter spacing was removed from active route prototypes.

Color governance now rejects bare `rgba()` and direct non-relative `oklch()` in active prototype HTML. Data-viz local variables remain allowed when named custom properties define the palette. No unresolved color exceptions remain.

## Generated Artifacts

`bun run generate-contracts` refreshed:

- `src/features/shell/page-contracts.generated.ts`
- `scripts/visual-audit.config.generated.mjs`

The generated diff is expected because the contract registry now exposes all 27 active contracts and 93 active overlays, where the previous generated baseline was stale.

## Verification

- `bun run test:run scripts/prototype-design-consistency.test.ts`: 10 tests passed
- `bun run test:run scripts/page-*-prototype.test.ts`: 21 files / 126 tests passed
- `bun run test:run scripts/prototype-design-consistency.test.ts scripts/page-*-prototype.test.ts`: 22 files / 136 tests passed
- Active prototype gate loop: 27 / 27 PASS, output in `test-results/ditto-design-cycle-gates/prototype-remediation-2026-04-28/`
- `bun run generate-contracts`: completed; generated artifact drift inspected
- `git diff --exit-code src/features/shell/page-contracts.generated.ts scripts/visual-audit.config.generated.mjs`: exit 1 expected because generated artifacts changed from stale baseline
- `bun run check`: Biome passed, TypeScript passed, Vitest 133 files / 1483 tests passed
