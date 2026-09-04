# Experiment catalog implementation feedback

- React route: `/research/experiments`
- Contract verification: 2026-08-29
- The catalog consumes only the live R3 experiment summary endpoint; it has no write path and no prototype-data fallback.
- Search, status filtering, selected-row identity, and the detail drawer all use the same summary object.
- Failure codes are shown explicitly; absence is rendered as `未报告失败`, not as a successful result claim.
- The catalog hands creation to the governed planner and full evidence to the experiment workbench.
