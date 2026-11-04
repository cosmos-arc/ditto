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

### Approved break window (2026-10 data-layer reset, #390)

The maintainer approved destructive contract changes for the data-layer
simplification program (#390, sub-issues #391–#397): the project has never
shipped, no old clients exist, and no deprecation window, dual read/write or
legacy DTO adaptation is required. During this window `oasdiff breaking`
against the merge base is expected to fail on those PRs; the failure list must
be quoted in the PR description. The gate returns to fully green once the
program lands and main carries the final contract.

### Approved versioned breaks registry

For individually approved breaking changes outside a blanket window, Required
check 3's "an approved versioned break is documented" path is implemented as
`contracts/openapi/approved-breaks.yaml`. The gate still fails on every oasdiff
finding first; only then does it enumerate the findings in JSON form and match
each one exactly (rule id plus the finding's stable fingerprint) against a
registry entry that carries an approval reference (`approved-by`) and date.
Any unmatched finding fails the gate — the registry cannot widen anything, and
no wildcard or rule-level suppression exists.

Rules of use:

- An entry may only be added with an explicit maintainer approval reference
  (issue or PR where the break was ruled on) and the failure list quoted in the
  PR description.
- Entries are consumed exactly once per gate run; oasdiff fingerprints are
  content-addressed, so a leftover entry would silently re-approve an
  identical future change. The gate therefore fails on any unconsumed entry:
  once the merge base carries the change and the finding disappears, the
  entries must be removed in the first PR that lands after the break.
- The registry is parsed on every gate run; a malformed or non-UTF-8 registry
  file fails the gate closed regardless of whether a break is being approved.

## Required runtime validation

Compile-time OpenAPI types are insufficient when a malformed response could
authorize or misrepresent an action. Validate discriminators and critical
identity/hash/status fields at runtime for Agent SSE, approvals, order commands,
risk decisions, ledger mutations, recovery receipts, and version negotiation.

## Required checks

1. Canonical FastAPI export is byte-identical to `contracts/openapi/v1.json`.
2. Redocly strict lint reports no errors.
3. `oasdiff breaking` passes against merge base and the latest release baseline,
   or every finding is exactly matched in the approved-breaks registry
   (`contracts/openapi/approved-breaks.yaml`) with an approval reference.
4. `openapi-typescript` output in a temporary directory is byte-identical to the
   committed generated file, including schema hash and generator version.
5. Web type tests reject a wrong path, method, parameter location, body, and
   response assumption.
6. Adapter and production-mode system tests cover both success and structured
   failure behavior.
