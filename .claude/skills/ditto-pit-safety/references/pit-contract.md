# Ditto PIT contract

## Visibility model

At decision time `T`, a row is usable only if every required visibility condition is satisfied:

- its knowledge/publication time is no later than the declared cutoff;
- its version is effective at the requested as-of time;
- it belongs to the selected source snapshot/revision universe;
- required identity and time metadata are present.

Missing cutoff, snapshot, or version metadata is an error for PIT-sensitive paths. A fallback to latest data is not safe.

## Version intervals

Use half-open intervals:

```python
visible = frame.filter(
    (pl.col("effective_from") <= as_of_date)
    & (
        pl.col("effective_to").is_null()
        | (pl.col("effective_to") > as_of_date)
    )
)
```

If `effective_to == 2026-01-15`, the version is not visible on that date. Boundary tests must cover the last included and first excluded instants.

## Knowledge time

Knowledge time is source-specific and must come from an explicit project contract. Typical interpretations include next-session availability for end-of-day bars, actual announcement time for filings, and published effective time for index constituents. Do not invent `trade_date + 1` locally when an existing service owns that rule.

## Historical windows

The value computed for decision row `T` must not consume row `T` when that observation is known only after the decision.

- Time-indexed DataFrame rolling: use a left-closed interval.
- Point-count Expr rolling: shift the series first, then roll.

```python
safe = pl.col("close").shift(1).rolling_mean(window_size=20).over("instrument_id")
```

Sort by entity and time before shift or rolling. Validate sparse calendars and group boundaries.

## As-of joins

Use a backward join from each decision to the latest record whose knowledge time is visible. Sort both inputs, partition by the complete entity key, and reject accidental forward/nearest strategies.

```python
result = decisions.join_asof(
    publications,
    left_on="decision_time",
    right_on="knowledge_time",
    by="instrument_id",
    strategy="backward",
)
```

The join output must retain or trace the selected source revision/snapshot.

## Snapshot propagation

Snapshot identity is part of the request and artifact identity. Include it in query DTOs, cache keys, materialization manifests, backtest inputs, lineage, and replay evidence. A cache keyed only by symbol/date can leak a later revision into an earlier run.

## Execution timing

Separate signal generation from execution eligibility. If a signal uses T close, it cannot fill at that same close unless the data contract explicitly proves earlier availability and the execution model supports it.

## Future-sentinel test

Create a row or revision strictly after the cutoff with an extreme value. Assert the result is identical with and without that future data. Then add a nearby row just inside the cutoff and assert it is consumed. This pair proves both exclusion and useful inclusion.

Mark the test `@pytest.mark.pit` and keep a focused regression test beside the owning package.
