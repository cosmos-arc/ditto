# API Contract Agent Guide

## Ownership

`contracts/openapi/v1.json` is the only cross-language API contract. FastAPI in
`apps/backend` is its semantic provider; `apps/web/src/api` is the typed
consumer. The snapshot and generated TypeScript are checked-in derived files,
not hand-edited sources.

`contracts/cohorts/compatibility-policy.json` is the release compatibility
allowlist. Its SHA-256 sidecar is mandatory; `current` is materialized from the
exact Web build identity and `previous` may only be registered from a verified
release cohort manifest. Same-major inference is forbidden.

## Required flow

1. For route, DTO, status, content-type or compatibility changes, read
   [OpenAPI compatibility](openapi/README.md) and verify affected consumers.
2. Keep `operationId` explicit, unique and stable.
3. Export from the side-effect-free app factory to a temporary file and compare
   canonical bytes.
4. Run Redocly strict lint and oasdiff against merge base/release baselines.
5. Generate TypeScript and runtime operation-response metadata from the local
   snapshot into temporary paths. Require zero diff with both
   `apps/web/src/api/generated/schema.d.ts` and
   `apps/web/src/api/generated/operation-contracts.ts`.
6. Verify that typed transport rejects any undeclared success status or response
   media type before feature adapters run; `default` may cover undeclared error
   statuses, never an undeclared 2xx response.
7. Verify feature adapter tests and production-mode system E2E.

`/api/v1` permits compatible additions only. Breaking changes require a new API
version or explicit deprecation and approval. Never generate from a running
server or network URL, never create broad lint ignores, and never use mock-only
evidence for live behavior.

Run `task check-contract` before completion.
