# Platform overview implementation feedback

- React route: `/platform`
- Contract verification: 2026-08-30
- Production and mock modes use the same generated catalog DTOs and the same five `/api/v1/ingestion/catalog/*` read paths. The route no longer has a prototype-only branch or private `/platform/*` mock endpoints.
- Catalog assets establish the dataset identities first. Remediation, source-health, fallback, and promotion summaries remain disabled until both those identities and an exact operator-visible trade date are bound; the full scope is in every query key and request.
- The health strip shows only backend-supported counts. It does not invent provider latency, CPU, memory, disk, API quota, pipeline duration, or task progress.
- [proto-deviation] The prototype's pipeline rerun, alert handling, and task-detail overlays were removed from the landing contract because no matching backend command contract exists. Governed catalog writes remain owned by `/platform/data-products`.
- [proto-deviation] The status bar spans the navigation rail to match this prototype's full-width terminal strip.
- At 1536px and 1366px the required shell, rail, header, health, main, detail, and status regions have exact geometry and no runtime warnings. Replacing fictitious infrastructure content produces measured pixel differences of 6.37% and 6.63%, recorded under a 7% threshold while structural and error gates remain zero-tolerance.
- No new backend endpoint, platform orchestration layer, or duplicate governance write flow was introduced.
