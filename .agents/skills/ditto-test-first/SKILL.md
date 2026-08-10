---
name: ditto-test-first
description: Use for Ditto bug fixes, behavior changes, public contracts, PIT behavior, risk controls, trading rules, execution, portfolio accounting, and backtest semantics. Requires observing a meaningful failing test before the implementation, then minimal GREEN, refactoring, and focused reruns. Excludes documentation, formatting, pure moves, and mechanical renames.
---

# Ditto Test First

Make the risk observable before changing production behavior.

## Confirm applicability

Use this workflow for bugs, externally visible behavior, public API/contracts, temporal/PIT behavior, risk, trading, execution, portfolio accounting, or backtest semantics.

Documentation, formatting, pure moves, generated mirrors, and mechanical renames are exempt if behavior is unchanged. If the “mechanical” change reveals semantic work, return to this workflow.

## RED

1. Locate the closest existing test layer and identify the public seam that should expose the behavior.
2. Add the smallest test that fails for the intended reason.
3. Run only that test and record:
   - exact command;
   - failing assertion/error;
   - why the failure demonstrates the missing or broken behavior.
4. If it passes unexpectedly, improve the observation before editing production code.

For PIT paths, invoke `ditto-pit-safety` and include a future sentinel. For cross-package contracts, invoke `ditto-architecture-change`.

## GREEN

1. Implement the smallest coherent change that satisfies the failing test.
2. Avoid unrelated cleanup and speculative abstraction.
3. Rerun the RED command until it passes.
4. Add boundary/error cases justified by the risk, not by a coverage target alone.

## REFACTOR and verify

Refactor only while the focused suite remains green. Then run the owning package tests and the validation level from root `AGENTS.md`.

Do not replace RED evidence with mocks that only assert implementation details. Prefer observable outputs, state transitions, boundary calls, persisted evidence, or domain events.

In the final report include RED evidence, the minimal behavior change, GREEN evidence, and the broader commands actually run.
