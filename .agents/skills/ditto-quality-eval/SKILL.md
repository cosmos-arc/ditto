---
name: ditto-quality-eval
description: Use only when the user explicitly requests a repository-wide Ditto quality evaluation, scorecard, radar assessment, or full quality baseline. Supports quick, full, and selected-dimension modes; collects the baseline once, applies deterministic weights/schema, and writes docs/reviews only for full mode or an explicit --write request.
---

# Ditto Quality Evaluation

Evaluate the repository with a repeatable rubric. Do not invoke this skill for ordinary implementation, review, or a single failing check.

## Select mode

- `quick` (default): code, architecture, and tests; present results without writing a report.
- `full`: all six dimensions; write `docs/reviews/YYYY-MM-DD-quality-eval.md`.
- `--dimension code,arch,...`: evaluate only named dimensions; do not write unless `--write` is explicit.
- `--write`: persist the selected result using the same report schema.

Dimensions and weights are fixed:

| Key | Dimension | Weight | Reference |
|---|---|---:|---|
| code | Code quality | 0.20 | `references/code-quality.md` |
| arch | Architecture | 0.25 | `references/architecture.md` |
| test | Tests | 0.15 | `references/test-quality.md` |
| eng | Engineering process | 0.10 | `references/engineering-process.md` |
| ops | Operations | 0.15 | `references/operations.md` |
| domain | Quant domain | 0.15 | `references/domain-specific.md` |

## Collect one baseline

Run each selected baseline command at most once and retain the complete command/result:

```bash
pixi run -e dev lint
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
git log --oneline -20
```

Do not rerun the full baseline inside dimension analysis. Mark unavailable metrics as `not_measured` with the reason; never invent a score input.

## Evaluate dimensions

Read only the references for selected dimensions. In full mode, independent read-only dimensions may use the host's native parallel agents; quick and selected modes do not require agents. No fixed agent count is allowed.

For every rubric item emit:

```json
{
  "id": "A-001",
  "item": "boundary enforcement",
  "weight": 3,
  "status": "pass | warning | fail | not_measured",
  "evidence": "command, path, or observed fact",
  "recommendation": null
}
```

Score `pass=100%`, `warning=60%`, `fail=0%`; exclude `not_measured` from numerator and denominator while reporting its coverage gap. A reference hard-fail caps that dimension at 2.0/5.0.

Compute each dimension to four decimals, then the normalized weighted total across selected measured dimensions. Round displayed scores to two decimals. Do not replace the fixed weights with a simple average.

## Present or write

Use `references/radar-template.md` for the stable output layout. Include baseline provenance, dimension scores, measurement coverage, severity-sorted top issues, and comparison only when a compatible prior report exists.

Quick mode returns the summary in conversation. Full or `--write` mode writes the report once, then reports its path. Never run this interactive evaluation automatically in CI.
