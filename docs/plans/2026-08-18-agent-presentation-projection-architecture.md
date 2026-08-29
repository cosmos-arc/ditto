# Agent Presentation Projection Architecture

> **Status:** approved for implementation
> **Date:** 2026-08-18
> **Drivers:** R5 frontend recovery, readable evidence, exact approvals, and Decision Briefing

## 1. Problem

The public Agent API can create and fetch identities that the caller already knows, but it cannot rebuild the operator workspace after a refresh. The Agent metadata database deliberately stores only objective, payload, and output hashes. SSE contains durable notification facts, not display content. Those properties are correct for the audit store, but insufficient for a governed UI that must show readable, redacted evidence and exact approval scope.

The missing public read surface is:

- non-sensitive capability and degradation status;
- paginated sessions, runs, campaigns, and approvals;
- readable run projections with context, result summary, redacted tool records, evidence and artifact references, guardrail outcome, budget usage, event cursor, and projection version;
- a shadow-only DecisionOpinion lookup keyed by an exact Daily Decision V3 identity.

## 2. Decision

Keep the existing Agent metadata SQLite database hash-only. Add an independent Agent presentation projection store with its own schema version and integrity markers. The presentation store is a derived read model, never an authority source for execution, approval, PIT, Campaign state, or audit verification.

The projection stores only server-selected display fields:

- normalized objective and stable context identity supplied at run creation;
- terminal or paused status and a bounded readable GroundedAnswer summary;
- redacted tool name/call identity plus result hash, evidence references, and artifact references;
- guardrail status and stable failure code;
- bounded usage counters and stop reason;
- last persisted event cursor, projection version, and updated time.

It must not store provider credentials, raw continuation state, arbitrary tool arguments/results, HTTP headers, model configuration secrets, or browser-supplied provider identifiers.

## 3. Ownership and dependency direction

- `ditto_agent.runtime.service` owns Agent capability/list/projection contracts exposed through `AgentRuntimePort`.
- `ditto_agent.presentation` owns the sanitized projection value objects and projection sink contract.
- `ditto_agent.storage.sqlite.presentation_store` owns the separate SQLite implementation.
- `GovernedAgentOrchestrator` may publish a derived outcome through an injected presentation sink after the deterministic outcome has been assembled. The sink cannot influence orchestration state.
- `ditto_apps.registry.agent.runtime` composes metadata and presentation readers/writers and adapts them to the public runtime port.
- `ditto_application.agent_campaign_runtime` continues to own Campaign public contracts; its port gains read-only pagination without importing Agent.
- `ditto_application.queries.decision_opinion` owns the shadow opinion query contract. The provider adapter in `ditto_apps.registry` reads the Agent-owned shadow store. Application never imports Agent.
- `ditto_apps.api.routes.agent_routes` and explicit Pydantic DTOs remain thin transport adapters.

No capability package imports Agent or Apps. Agent continues to consume business state only through Application contracts.

## 4. Public API surface

The Agent router adds:

- `GET /api/v1/agent/capabilities`
- `GET /api/v1/agent/sessions`
- `GET /api/v1/agent/runs`
- `GET /api/v1/agent/approvals`
- `GET /api/v1/agent/approvals/{approval_id}`
- `GET /api/v1/agent/campaigns`
- `GET /api/v1/agent/decision-opinions` keyed by exact strategy, account, trade date, and V3 artifact identity

Existing `GET /runs/{run_id}` becomes the complete presentation response. Existing mutation and SSE routes remain unchanged.

Pagination is cursor-free offset/limit for this single-user local deployment. Filters are explicit, bounded, and equality-based. List responses include `total`, `limit`, `offset`, and `has_more`. Stable ordering is newest first with identity as the deterministic tie-breaker.

## 5. Failure and degradation semantics

- Capability status is always readable, including when the Agent feature is disabled.
- Disabled or degraded runtimes reject new writes with the existing typed 503 boundary.
- A configured persisted query runtime may continue reading historical projections while model/provider creation is unavailable.
- Missing projection content is represented as `partial` with a stable reason code; clients never reconstruct text from hashes.
- Missing DecisionOpinion is `unavailable`, not a Daily Decision V3 failure.
- Missing cutoff or source snapshot makes DecisionOpinion provenance mismatch and fail-closed for display trust, without modifying V3 readiness or actions.

## 6. Schema and lifecycle

The new file is `agent-presentation.sqlite3` below the Agent data root. Schema version 1 contains a single authenticated run projection table. JSON columns use canonical `orjson` encoding and strict decoding. Projection writes are monotonic by `projection_version`; an older version cannot overwrite a newer one.

The presentation database has an independent lifecycle in the Agent database bundle. Retention may delete derived presentation rows only after the authoritative run is outside retention; deleting a presentation row never deletes or rewrites core audit facts.

The DecisionOpinion shadow store remains independent. Its new exact-identity index/query is read-only and must preserve the opinion's stored PIT provenance.

## 7. Verification

- Contract-first tests observe missing list/capability/projection routes before implementation.
- Store tests cover restart recovery, canonical decoding, version monotonicity, redaction, and corrupt-row fail-closed behavior.
- Runtime tests cover disabled/degraded capabilities, filtering, pagination, pending/expired approval state, and partial projections.
- DecisionOpinion tests include future-dated cutoff/snapshot sentinels and prove the V3 response remains independent.
- API/OpenAPI tests lock every new route and explicit DTO.
- `pixi run -e dev arch-check`, focused PIT tests, and the full backend check are required before promotion.

## 8. Rollback

The presentation store is derived and isolated. Rollback removes the new read routes and stops writing the projection file; the hash-only Agent database, Campaign store, DecisionOpinion shadow records, approvals, and SSE audit chain remain valid. The derived file can be retained for forward recovery or removed only through an explicit operator-approved maintenance step.
