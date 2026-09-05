---
name: ditto-page-contract
description: Use for creating, validating, promoting, updating, or refreshing Ditto page contracts, contract metrics, selectors, responsive behavior, generated contract artifacts, or prototype-to-React acceptance criteria.
---

# Ditto Page Contract

Define what it means for an approved blueprint/prototype to be faithfully implemented in React.

## Read first

1. Read the target file in `docs/contracts/pages/`, `.arch-manifest.json`, its blueprint and prototype.
2. Read [contract-cli.md](references/contract-cli.md) before running a subcommand.
3. Read [contract-create-phases.md](references/contract-create-phases.md) only for creation/metric refresh.
4. Read [contract-error-recovery.md](references/contract-error-recovery.md) when validation fails.

## Lifecycle

`blueprint-approved → draft → validated → contract-ready → implemented`

- **Create**: resolve blueprint/prototype, capture metrics, map selectors/states/interactions, choose thresholds, write JSON and regenerate consumers.
- **Validate**: check schema, references, selectors, metrics, required universal states, enum values, thresholds, accessibility and responsive annotations.
- **Promote**: require blocking validations green, approved prototype state and no browser console errors; then change only status and regenerate.
- **Update**: selector, threshold, sub-slot, accessibility and responsive corrections are allowed; route, ID and taxonomy changes require recreation/architecture review.
- **Refresh metrics**: replay the documented Playwright capture, update metrics/version and regenerate.

## Invariants

- `docs/contracts/pages/*.contract.json` is the source; generated TypeScript/MJS artifacts are consumers.
- Zero-tolerance checks remain zero. Shell thresholds are stricter than content sub-slots.
- Universal states include loading, empty, error and stale.
- Required shell slots declare stable selectors; accessibility and compact behavior are explicit.
- Never promote a contract to make a failing validator disappear.

## Commands and evidence

Use the commands in [contract-cli.md](references/contract-cli.md); project entry points include `bun run generate-contracts`. Preserve validator output and affected contract/version in the final report. When metrics or selectors change, run the target consumer test and relevant visual comparison.

## Completion

- JSON schema and blocking validators pass.
- Generated artifacts are synchronized with all contract JSON files.
- The target React consumer can locate required slots and states.
- Any prototype/design-system override has an explicit rationale and feedback path.
