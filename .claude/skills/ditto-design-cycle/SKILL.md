---
name: ditto-design-cycle
description: Use when creating or reviewing Ditto HTML prototypes, iterating visual or interaction quality, managing prototype editions, comparing viewports, or synchronizing approved prototype decisions back into product and design specifications.
---

# Ditto Design Cycle

Create and review prototypes against Ditto product criteria while preserving user ownership of product scope.

## Read first

1. Read `PRODUCT.md`, `DESIGN.md` and the relevant `00/01/02/04` design specs.
2. Resolve `.arch-manifest.json`, the target prototype, edition state and any page contract.
3. Load only the needed reference:
   - [create-mode.md](references/create-mode.md) for blueprint-to-prototype work.
   - [review-scoring.md](references/review-scoring.md) and [roles.md](references/roles.md) for critique.
   - [viewport.md](references/viewport.md) for responsive evidence.
   - [iterate.md](references/iterate.md) for bounded iteration.
   - [edition.md](references/edition.md), [sync.md](references/sync.md), or [version-control.md](references/version-control.md) for those modes.

## Invariants

- Use Ditto's five review dimensions: restraint, consistency, refinement, brand direction and information efficiency.
- Prototype shell blocks inside `#default-view` expose the required `data-contract-slot` markers.
- Prototype HTML contains no inline `style` attributes.
- Product changes are labeled for PM/user confirmation; visual proposals cannot silently expand functionality.
- Contract failure blocks strict mode. A prototype is not `done` until required gates pass.

## Workflow

1. Establish version/baseline and affected viewports.
2. For creation, map blueprint modules, states and overlays into the approved shell family.
3. For review, inspect visual hierarchy, interaction, accessibility, copy, information architecture and data visualization.
4. Reconcile conflicts with evidence and present material product choices to the user.
5. Apply the smallest coherent fix set, then rerun viewport and prototype gates.
6. Record durable design decisions and update edition/contract state only after evidence passes.
7. Use [execution-flow.md](references/execution-flow.md) only when the full phase sequence is required.

## Verification

- `bun run prototype:gates`
- Target prototype tests under `scripts/`.
- `bun run audit:tokens` for token/color changes.
- Browser screenshots at the viewports named in the contract or `viewport.md` when visual behavior changes.

Report remaining disagreements, skipped visual evidence and any contract deviation explicitly.
