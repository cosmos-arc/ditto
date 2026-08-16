# R5 governed Agent security boundary

Status: deterministic controls are implemented; physical sandbox and live-model acceptance remain blocked by A3 and A4.

## Authority boundary

The model proposes structured intent. The deterministic host owns temporal context, evidence visibility, tool allowlists, budgets, approval, idempotency, leases, storage, grading, and every side effect. Agent imports flow `apps -> agent -> application`; Agent does not import capability storage, `analysis`, or Apps, and application/capability packages do not import Agent.

There are no model-callable publish, portfolio-weight, risk override, order, trade, broker, arbitrary SQL, filesystem, shell, or network tools. DecisionOpinion is shadow-only and cannot change DailyDecision V3 or downstream trading identities.

## Data and model boundary

- Evidence reads require explicit decision/knowledge/publication cutoffs, source snapshots, and versions; missing identity fails closed.
- Live OpenAI use requires A4, a dedicated project, MAM or ZDR, `store=false`, an allowed dataset/license/egress class, versioned model/profile/prompt/tool schema, and an explicit budget.
- The current balanced and quality reports are `not_run`, exit 5, and `release_gate_passed=false`. No credential was read, endpoint called, data exported, or model fee incurred.
- Raw permitted continuation content has a 30-day typed retention boundary. Formal artifacts, approvals, Episode manifests, audit summaries, and hash chains are retained. Deletion requires an exact dry-run hash and separate approval.
- OTel exports only a closed low-cardinality schema after redaction. Export failure cannot change business behavior.

## Generated-code boundary

Generated code is a fixed `fit`/`score` contract and cannot run on the host. The host validates AST, manifest, snapshot, seed, image/input/state attestations, serialization, output schema/shape/size/identity, and deterministic replay before trusted evaluation.

A3 remains mandatory for the physical OCI/gVisor runtime, immutable image digest, SBOM, dependency lock, seccomp profile, daemon use, and live sandbox attack acceptance. The Fake attack suite proves classification and host refusal only; it is not evidence of network, mount, resource, serialization, or escape resistance in a real runtime.

## Approval and persistence boundary

- Formal writes bind operator, authority, context, action hash, arguments hash, call ID, budget, and expiry.
- Approval decisions and Campaign authorization are append-only, idempotent, and revalidated immediately before the physical write.
- Agent SQLite and Research SQLite are separate, authenticated schemas. Backup is non-overwriting; restore targets are new paths and must pass integrity, foreign-key, schema, domain, and artifact-hash verification.
- Restart resumes from durable continuation/idempotency/lease state. Replay does not re-execute tool side effects.

## Degradation and rollback

All Agent feature flags default false. With the master flag false, optional dependencies are not probed. Model provider, Agent database, sandbox, and exporter failures produce structured Agent unavailability while core Ditto remains usable. Rollback disables all five flags and preserves evidence; it never deletes databases or widens a fallback path.

## Residual blockers

- A3: no approved physical runtime/image/SBOM/seccomp/dependency identity or live attack target.
- A4: no approved project/MAM-ZDR/credential/data-egress/budget identity for live comparison.
- G4/G5: R5 does not claim external Beta, authentication/RBAC, multi-tenant isolation, legal commercialization, automatic trading, or broker connectivity.

The release preflight must remain BLOCKED until A3/A4 evidence is independently produced and validated. Feature completeness cannot override these gates.
