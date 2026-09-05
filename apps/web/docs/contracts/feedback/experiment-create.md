# Experiment Create implementation feedback

- React route: `/research/experiments/new`
- Contract verification: 2026-08-29
- Style anchor: the Strategy Studio prototype supplies the shared three-column shell; no separate prototype or generic experiment platform was introduced.
- Planning truth: the source rail and form expose the exact experiment, strategy version, snapshot, validation, matrix, budget, seed, and execution policy used by the request serializer.
- Preflight semantics: Preflight is explicitly read-only. Any form edit invalidates the prior confirmation and launch remains disabled until the current ready plan hash is confirmed.
- Launch safety: typed rejections preserve the form and server Preflight evidence; an unknown 503 outcome reuses the same idempotency key.
- Missing evidence: values that have not been produced are shown as `尚未运行` or `未生成`, never as a fabricated zero.
