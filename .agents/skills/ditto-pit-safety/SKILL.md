---
name: ditto-pit-safety
description: Use for Ditto data queries, rolling or shift operations, joins, factors, feature materialization, backtests, signals, knowledge dates, publication cutoffs, revisions, and source snapshots. Prevents look-ahead by requiring fail-closed visibility, explicit time semantics, snapshot propagation, and future-sentinel tests.
---

# Ditto PIT Safety

Assume data is unavailable until the code proves it was knowable at the decision time.

Read [references/pit-contract.md](references/pit-contract.md) before changing temporal query or computation logic.

## Define time before code

Record the decision timestamp and distinguish:

- observation/effective time: when the fact describes the world;
- publication/knowledge time: when the system could know it;
- source snapshot: which revision universe is visible;
- execution time: when a signal can become an order or fill.

If any required dimension is absent or ambiguous, fail closed. Do not substitute wall-clock “now” or silently choose the latest revision.

## Preserve causality

- Propagate `knowledge_date`, publication cutoff, and source snapshot across services, DTOs, caches, materialization, and replay.
- Use half-open version validity: `effective_from <= as_of < effective_to`, with null `effective_to` meaning open-ended.
- Use backward as-of joins on the knowledge field, partitioned by entity and sorted explicitly.
- Exclude the current decision row from historical features: a left-closed time window or an explicit `shift(1)` before point-count rolling.
- Keep T-day decisions from executing on unavailable T-day close information; model the next eligible execution time explicitly.
- Key caches and artifacts by all temporal visibility inputs.

## Prove absence of leakage

1. Add a future sentinel or late revision that would materially change the output if leaked.
2. First show the test fails for the unsafe behavior or missing guard.
3. Implement the smallest fail-closed correction.
4. Assert both the boundary instant and a nearby allowed instant.
5. Run the target tests and:

```bash
pixi run -e dev pytest -m pit
```

For cross-package changes also run `pixi run -e dev arch-check`; for production Python finish with `pixi run -e dev check`.

Report the decision time, knowledge cutoff, snapshot identity, window/join semantics, sentinel used, and commands run.
