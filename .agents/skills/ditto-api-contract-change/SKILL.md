---
name: ditto-api-contract-change
description: Use for Ditto FastAPI routes, HTTP DTOs, OpenAPI snapshots, operationId changes, generated Web API types, typed transport, runtime compatibility, or any behavior that changes the backend-to-Web contract.
---

# Ditto API contract change

Treat the contract as one cross-stack change:

```text
apps/backend -> contracts/openapi/v1.json -> generated paths -> typed transport -> feature adapter
```

## Before editing

1. Read `contracts/AGENTS.md`, the nearest backend/Web `AGENTS.md`, and
   [the compatibility policy](references/compatibility-policy.md).
2. Identify the FastAPI provider, every Web consumer, the stable `operationId`,
   error statuses, content types, and runtime validation needs.
3. For behavior or public-interface changes, observe a meaningful failing
   backend contract test or Web compile/adapter test before implementation.

## Required implementation shape

- FastAPI route and response models are the semantic provider. Do not make a
  Python DTO importable by Web code.
- Keep `operationId` explicit, unique, and stable across Python renames.
- `/api/v1` accepts compatible additions only. Route incompatible changes to a
  new version or a documented deprecation sequence.
- Generate OpenAPI only from the side-effect-free app factory and only from a
  local file. Never use a running service or network source for codegen.
- Never hand-edit `contracts/openapi/v1.json` or generated TypeScript.
- Generated DTOs may be imported only by `src/api` and feature API adapters.
  Components consume view models, not generated schemas.
- Streaming, approval, trading, risk, and ledger boundaries require runtime
  discrimination in addition to TypeScript types.

## Evidence before completion

Run the focused RED/GREEN tests, then `pixi run -e dev check-contract`. For a
contract or cross-stack behavior change also run `pixi run -e dev check-web`,
the affected backend tests, and `pixi run -e dev test-system` when the behavior
is user-visible. Report breaking-diff baselines and every command actually run.

Stop rather than accepting a broad lint ignore, generated-file manual patch,
unapproved breaking change, mock-only proof of live behavior, or schema hash
mismatch.
