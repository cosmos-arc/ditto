# OpenAPI 契约与兼容性

## Supported line

The current and immediately previous release cohorts are the supported upgrade
and rollback combination. A cohort is identified by product version, Git SHA,
API contract version, API contract SHA-256, and backend/Web artifact digests.

## Compatible `/api/v1` changes

- Add an optional request field with a documented default.
- Add a response field when consumers tolerate unknown fields.
- Add an endpoint with a new stable `operationId`.
- Add an enum value only when clients already handle an unknown value; otherwise
  it is breaking.
- Widen accepted input without weakening risk, authorization, PIT, or validation
  semantics.

## Breaking changes

- Delete or rename a route, method, parameter, request field, response field,
  status, or content type.
- Change a path/query/body field from optional to required.
- Narrow an input type, response type, enum, numeric range, or nullability.
- Change envelope shape, pagination, error semantics, discriminator, units,
  currency, time zone, or timestamp meaning.
- Reuse an `operationId` for different semantics or change it because a Python
  function was renamed.
- Make previously available data fail closed/open differently without a new
  semantic version and consumer migration.

Breaking changes require `/api/v2` or an explicit deprecation window, migration
tests, and owner approval. `oasdiff` is a minimum detector, not authority to
declare a change compatible; domain semantic changes still require review.

## Required runtime validation

Compile-time OpenAPI types are insufficient when a malformed response could
authorize or misrepresent an action. Validate discriminators and critical
identity/hash/status fields at runtime for Agent SSE, approvals, order commands,
risk decisions, ledger mutations, recovery receipts, and version negotiation.

## Required checks

1. Canonical FastAPI export is byte-identical to `contracts/openapi/v1.json`.
2. Redocly strict lint reports no errors.
3. `oasdiff breaking` passes against merge base and the latest release baseline,
   or an approved versioned break is documented.
4. `openapi-typescript` output in a temporary directory is byte-identical to the
   committed generated file, including schema hash and generator version.
5. Web type tests reject a wrong path, method, parameter location, body, and
   response assumption.
6. Adapter and production-mode system tests cover both success and structured
   failure behavior.
