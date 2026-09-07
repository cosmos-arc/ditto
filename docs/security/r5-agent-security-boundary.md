# R5 governed Agent security boundary

Status: deterministic controls, the OrbStack physical sandbox, GLM 5.3 Coding Plan balanced/quality online acceptance, and the R5.5 release preflight are complete. Coding Plan remains forbidden for standalone/production execution; production activation requires a standard API credential.

## Authority boundary

The model proposes structured intent. The deterministic host owns temporal context, evidence visibility, tool allowlists, budgets, approval, idempotency, leases, storage, grading, and every side effect. Agent imports flow `apps -> agent -> application`; Agent does not import capability storage, `analysis`, or Apps, and application/capability packages do not import Agent.

There are no model-callable publish, portfolio-weight, risk override, order, trade, broker, arbitrary SQL, filesystem, shell, or network tools. DecisionOpinion is shadow-only and cannot change DailyDecision V3 or downstream trading identities.

## Data and model boundary

- Evidence reads require explicit decision/knowledge/publication cutoffs, source snapshots, and versions; missing identity fails closed.
- Live OpenAI use requires A4, a dedicated project, MAM or ZDR, `store=false`, an allowed dataset/license/egress class, versioned model/profile/prompt/tool schema, and an explicit budget.
- The current balanced and quality reports each contain 120 authenticated live observations and pass every suite, quality, safety, usage-cap and latency gate. Balanced used 242,462 total tokens with read/complex P95 of 20.058/22.729 seconds; quality used 250,644 tokens with read/complex P95 of 22.877/21.935 seconds. Raw model output and credentials are absent from the artifacts.
- The Apps-owned formal runner requires one hash-addressed A4 scope covering approval, provider data controls, runnable synthetic dataset, license/egress, model revision and one total-token cap per profile. It preflights all 120 cases and requires the actual dataset and prompt/tool manifests to match before credential access, binds the provider to the full run identity, authenticates per-case request/input/output usage and output hashes, and stops on the first cumulative token-cap overrun. Monetary cost is deliberately `not evaluated` in the report rather than asserted as zero; the provider console is the billing source.
- A4 rev4 permits the GLM 5.3 Coding Plan 120-case online acceptance only inside the approved Codex developer task, against `https://open.bigmodel.cn/api/v1`, with frozen synthetic data. The credential is injected from Keychain, the adapter forces `store=false` and disables hosted tracing/tools, and only hashes/usage/graded observations are persisted. Apps rejects this credential kind in production mode. Composition binds `glm_coding_plan_validation` to `/api/v1` Responses and production `formal_api` to `https://open.bigmodel.cn/api/paas/v4` Chat Completions with distinct continuation/provider identities.
- The earlier two-request smoke remains a composition check and records `production_eligible=false`. The balanced/quality reports satisfy the user-approved R5 online acceptance criterion, but do not become evidence for GLM standard API or OpenAI production behavior.
- Raw permitted continuation content has a 30-day typed retention boundary. Formal artifacts, approvals, Episode manifests, audit summaries, and hash chains are retained. Deletion requires an exact dry-run hash and separate approval.
- OTel exports only a closed low-cardinality schema after redaction. Export failure cannot change business behavior.

## Generated-code boundary

Generated code is a fixed `fit`/`score` contract and cannot run on the host. The host validates AST, manifest, snapshot, seed, image/input/state attestations, serialization, output schema/shape/size/identity, and deterministic replay before trusted evaluation.

The runtime is CPython 3.13.14 on a digest-pinned distroless Debian 13 base; it contains no shell, package manager, installer, or unused Debian Python libraries. Optional SQLite/curses dynamic libraries are deliberately absent because the fixed runner does not use them. A3 is accepted only for OrbStack 2.2.1 on the recorded arm64 daemon profile and immutable image `127.0.0.1:55000/ditto/r5-research-sandbox@sha256:8eface2a3ea24f1170ee1ccf09c1e42fa07e3c9f797ad53969e87e6b7516e8ea`. The Apps-owned runner revalidates the daemon profile before every execution and enforces no network, no mounts or inherited environment, non-root, read-only rootfs, bounded noexec tmpfs, cap-drop ALL, no-new-privileges, default-deny seccomp and CPU/memory/PID/wall/output limits. The physical suite passed 11 attack cases plus fresh-container, concurrency and `fit→score`; every execution has a recomputable manifest attestation. Docker access remains in the Apps composition root and neither Agent nor a candidate receives the daemon socket. This evidence does not claim Kubernetes, Docker Desktop/ECI, Linux rootless or gVisor coverage.

## Approval and persistence boundary

- Formal writes bind operator, authority, context, action hash, arguments hash, call ID, budget, and expiry.
- Approval decisions and Campaign authorization are append-only, idempotent, and revalidated immediately before the physical write.
- Agent SQLite and Research SQLite are separate, authenticated schemas. Backup is non-overwriting; restore targets are new paths and must pass integrity, foreign-key, schema, domain, and artifact-hash verification.
- Restart resumes from durable continuation/idempotency/lease state. Replay does not re-execute tool side effects.

## Degradation and rollback

All Agent feature flags default false. With the master flag false, optional dependencies are not probed. Model provider, Agent database, sandbox, and exporter failures produce structured Agent unavailability while core Ditto remains usable. Rollback disables all five flags and preserves evidence; it never deletes databases or widens a fallback path.

## Residual deployment boundaries

- Production credential: no GLM standard API key has been used or approved for deployment. Before enabling a deployed Agent, replace the Coding Plan credential, review production provider/data-control/license/egress/model identity, and rerun affected evals if the accepted identity changes.
- G4/G5: R5 does not claim external Beta, authentication/RBAC, multi-tenant isolation, legal commercialization, automatic trading, or broker connectivity.

The release preflight is PASS with all six checks passed and no blocker/failure. It independently validates the A3 live report, every execution attestation, image/SBOM/lock/seccomp hashes, and both authenticated GLM reports. This implementation result does not override the separate production credential boundary or enable any feature flag.
