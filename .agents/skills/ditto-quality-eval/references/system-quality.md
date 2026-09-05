# Cross-stack system quality evidence

Evaluate these system-specific signals within the fixed quality dimensions:

- FastAPI export, committed OpenAPI bytes, Redocly lint, oasdiff against merge
  base/release, and generated TypeScript zero-diff;
- production Web build using `runtime=live` against an isolated API/state root;
- health/readiness, version/hash negotiation, CORS, structured errors, restart,
  timeout and schema-mismatch behavior;
- root Harness coverage of staged, unstaged, untracked, rename/delete and mode
  changes, plus receipt invalidation and truthful command evidence;
- CI trigger completeness, stable total gate, platform support, least privilege,
  supply-chain scans and cache boundaries;
- independent backend/Web artifacts, smoke tests, SBOM/provenance/checksums and a
  mutually consistent release cohort manifest.

Mock-only or prototype-only tests cannot prove live cross-stack behavior. Mark
unavailable platform, release, protection or CI-history data as `not_measured`.
