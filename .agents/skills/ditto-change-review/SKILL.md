---
name: ditto-change-review
description: Use when the user asks to review Ditto changes, before a PR, or after completing a high-risk diff. Performs a read-only, evidence-based review of architecture, PIT safety, public interfaces, tests, error handling, and release evidence, with findings ordered by severity and precise file locations.
---

# Ditto Change Review

Review the actual diff and report defects, not style preferences.

## Establish scope

1. Read root and affected package `AGENTS.md` files.
2. Inspect the base/head diff, untracked files in scope, and relevant tests.
3. Use the host's native review capability when available.
4. Use parallel read-only subagents only when the diff is large enough to split into genuinely independent dimensions. Do not force a fixed agent count.

Remain read-only unless the user separately asks to fix findings.

## Review dimensions

- Architecture: owner package, dependency direction, DI/composition, re-exports, hidden cycles, abstraction level.
- PIT: knowledge cutoff, snapshot propagation, windows, shifts, joins, revisions, execution timing, future sentinels.
- Interfaces: public contract compatibility, serialization/schema, defaults, error semantics, callers.
- Correctness: invariants, boundary values, state transitions, concurrency, partial failure and cleanup.
- Tests: meaningful RED evidence where required, regression coverage, boundary/error cases, false-positive mocks.
- Release evidence: validation commands, migrations/rollback, configuration impact, real-data or broker approvals.

## Evidence standard

Verify each candidate against reachable code and tests. Do not report hypothetical problems without a concrete failure path. Prefer a small number of high-confidence findings.

Output findings first, ordered `critical`, `high`, `medium`, `low`. Each finding must include:

- concise title and severity;
- exact file and line;
- concrete behavior or failure path;
- why existing tests or guards do not prevent it;
- smallest useful remediation direction.

Then list open questions and a brief validation summary. If no actionable finding remains, say so and name residual risks or unrun checks.
