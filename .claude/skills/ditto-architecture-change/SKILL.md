---
name: ditto-architecture-change
description: Use for Ditto changes involving multiple packages, a new module or concept, dependency direction, public API or contract, dependency injection, directory placement, composition roots, or architecture refactoring. Requires identifying capability plane, provider, consumers, machine-enforced boundaries, and architecture validation.
---

# Ditto Architecture Change

Keep the package graph explicit and let machine boundaries decide what is legal.

## Establish the boundary

1. Read `docs/architecture/agent-context-pack.md` before proposing a placement.
2. Inspect `.importlinter` and the nearest package `AGENTS.md`; treat them as current machine and local facts.
3. Read `docs/architecture/boundaries-and-abstraction-standards.md` only when introducing a new concept/name, changing abstraction level, or resolving ambiguous ownership.
4. State four things before editing:
   - capability plane and owner package;
   - provider/implementation;
   - direct consumers;
   - contract or Protocol that crosses the boundary.

## Choose the narrowest design

- Put domain behavior in the owning capability package.
- Put orchestration in `application`; put adapters and composition in `apps.registry`.
- Put only stable, behavior-free, cross-package primitives in `kernel`.
- Keep technical infrastructure in `platform` and domain schemas in their owner package.
- Make consumers import the defining leaf module. Do not solve direction problems with cross-package re-exports, `TYPE_CHECKING`, delayed imports, or a service-locator shortcut.
- Prefer an existing contract. Add a new abstraction only when at least one real provider and consumer require it.

## Implement and prove

1. For public behavior or contract changes, invoke `ditto-test-first` and observe RED.
2. Update `.importlinter` only when the intended architecture itself changes and the user has approved that boundary change.
3. Keep DI wiring at the composition root and test the consumer-facing contract.
4. Run targeted tests while iterating.
5. Finish with:

```bash
pixi run -e dev arch-check
pixi run -e dev check
```

Report the final provider/consumer path and validation evidence. Do not claim completion while `arch-check` fails.
