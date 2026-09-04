---
name: ditto-product-arch
description: Use for Ditto information architecture, page blueprints, user flows, page and shell taxonomy, interaction state models, product architecture audits, or changes that must connect discovery artifacts to prototype and page-contract work.
---

# Ditto Product Architecture

Produce product specifications, not application code.

## Read first

1. Read `.arch-manifest.json`, `.discovery-manifest.json`, `docs/brief/constitution.md` and high-risk assumptions.
2. Read `docs/designs/specs/00_ditto_product_criteria.md`, `01_product_information_architecture.md`, `02_core_page_blueprints.md` and `04_interaction_state_spec.md` as applicable.
3. Load references only for the active decision:
   - [enums.md](references/enums.md) for shell/page/state vocabulary.
   - [output-structure.md](references/output-structure.md) before writing specs.
   - [validation-rules.md](references/validation-rules.md) for audit and consistency gates.
   - [roles.md](references/roles.md) when multiple product perspectives materially help.

## Invariants

- Organize around user workflows, not backend modules.
- Preserve selected-asset context and efficient search/navigation paths.
- Each page blueprint defines content sections, overlay registry, component × state matrix and page-contract mapping.
- Data surfaces cover loading, empty, error and stale states.
- Destructive operations declare a confirmation interaction.
- `shellFamily`, `pagePattern`, slots and state names use the project enums.
- Product scope changes remain user decisions; label unresolved choices and assumptions.

## Workflow

1. **Context** — resolve upstream artifacts, current manifest state, scope and consumers.
2. **Research** — identify workflow/domain constraints and comparable interaction models.
3. **Design** — propose IA, page taxonomy, blueprints, flows and state coverage; expose meaningful conflicts.
4. **Synthesis** — choose a coherent structure, record rationale and escalate scope decisions.
5. **Document** — update the relevant `00/01/02/04` specs and architecture decisions without duplicating facts.
6. **Validate** — run cross-document rules, state coverage, contract mapping and constitution checks; update `.arch-manifest.json`.

Use host-native parallel read-only analysis only when perspectives are genuinely independent. Do not hard-code a model, agent count, or orchestration protocol into the deliverable.

## Completion

- Routes, shell families, page patterns and terminology are consistent across specs.
- Each affected page has states, overlays, responsive intent and contract mapping.
- Manifest digests and recovery state match written artifacts.
- Handoff identifies consumers: `ditto-design-cycle`, `ditto-page-contract`, or application implementation.
