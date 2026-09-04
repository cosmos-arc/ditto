import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/types/generated/api";
import { createAgentRun, executeAgentRun, listAgentRuns, validateAgentCampaignStep } from "./agent-api";

type AgentRunResponse = components["schemas"]["AgentRunResponse"];

function runResponse(): AgentRunResponse {
	return {
		run_id: "run-21",
		session_id: "session-7",
		status: "running",
		objective_hash: "a".repeat(64),
		authority_hash: "b".repeat(64),
		max_model_tokens: 4096,
		max_model_spend_usd: "1.25",
		model_profile: "balanced",
		manifest_hash: "c".repeat(64),
		created_at: "2026-08-18T08:00:00Z",
		started_at: "2026-08-18T08:00:01Z",
		finished_at: null,
		revision: 3,
		objective: "Explain the factor evidence.",
		execution_plan: null,
		context: { context_type: "factor", context_id: "factor:mom-20" },
		output_summary: "Evidence is still being assembled.",
		tool_records: [],
		evidence_refs: ["ditto://evidence/factor/mom-20"],
		artifact_refs: [],
		guardrail: { status: "passed", reason_code: null },
		usage: {
			model_attempts: 1,
			model_turns: 2,
			tool_calls: 1,
			retries: 0,
			total_tokens: 700,
			model_spend_usd: "0.03",
			exhausted_reason: null,
		},
		failure_code: null,
		event_cursor: 5,
		projection_state: "complete",
		projection_reason: null,
		projection_version: 3,
		projection_updated_at: "2026-08-18T08:00:03Z",
	};
}

afterEach(() => vi.unstubAllGlobals());

describe("Agent API adapter", () => {
	it("preserves backend pagination and isolates bounded run filters", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: [runResponse()],
						pagination: { total: 41, limit: 20, offset: 20, has_more: true },
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(
			listAgentRuns({
				status: "running",
				sessionId: "session-7",
				contextType: "factor",
				contextId: "factor:mom-20",
				limit: 20,
				offset: 20,
			}),
		).resolves.toMatchObject({
			items: [{ runId: "run-21", context: { contextType: "factor", contextId: "factor:mom-20" }, eventCursor: 5 }],
			pagination: { total: 41, limit: 20, offset: 20, hasMore: true },
		});
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/agent/runs?status=running&session_id=session-7&context_type=factor&context_id=factor%3Amom-20&limit=20&offset=20",
			expect.objectContaining({ method: "GET" }),
		);
	});

	it("validates a structured Campaign wizard step without an idempotency header", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
			const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
			expect(body).toMatchObject({ step: "hypothesis", primary_metric_id: "sharpe_ratio" });
			return new Response(
				JSON.stringify({
					data: {
						step: "hypothesis",
						valid: true,
						canonical_manifest: null,
						manifest_hash: null,
					},
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			);
		});
		vi.stubGlobal("fetch", fetchMock);

		await expect(
			validateAgentCampaignStep({
				step: "hypothesis",
				campaign_id: "campaign-1",
				objective: "Test one falsifiable signal.",
				primary_metric_id: "sharpe_ratio",
				hypothesis: {
					statement: "Signal persists after costs.",
					mechanism: "Liquidity provision.",
					universe_hash: "a".repeat(64),
					expected_signal: "Sharpe improves.",
					failure_condition: "Sharpe does not improve.",
				},
			}),
		).resolves.toMatchObject({ step: "hypothesis", valid: true, manifestHash: null });
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/agent/campaigns/validation",
			expect.objectContaining({ method: "POST" }),
		);
	});

	it("creates a run with an explicit PIT scope and server-derived authority", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
			const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
			expect(body).not.toHaveProperty("authority_hash");
			expect(body.execution_scope).toEqual({
				allowed_universe: ["510300.SH"],
				decision_time: "2026-08-18T08:00:00Z",
				knowledge_cutoff: "2026-08-18T07:55:00Z",
				max_output_tokens: 1024,
				publication_cutoff: "2026-08-18T07:50:00Z",
				source_snapshot_id: "snapshot-certified-2026-08-18",
			});
			expect(body).not.toHaveProperty("api_key");
			return new Response(JSON.stringify({ data: runResponse() }), {
				status: 201,
				headers: { "Content-Type": "application/json" },
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		const run = await createAgentRun({
			sessionId: "session-7",
			objective: "Explain the factor evidence.",
			maxModelTokens: 4096,
			maxModelSpendUsd: "1.25",
			modelProfile: "balanced",
			context: { contextType: "factor", contextId: "factor:mom-20" },
			executionScope: {
				allowedUniverse: ["510300.SH"],
				decisionTime: "2026-08-18T08:00:00Z",
				knowledgeCutoff: "2026-08-18T07:55:00Z",
				maxOutputTokens: 1024,
				publicationCutoff: "2026-08-18T07:50:00Z",
				sourceSnapshotId: "snapshot-certified-2026-08-18",
			},
			idempotencyKey: "run-create-21",
		});

		expect(run.authorityHash).toMatch(/^[0-9a-f]{64}$/u);
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/agent/runs",
			expect.objectContaining({
				method: "POST",
				headers: expect.objectContaining({ "Idempotency-Key": "run-create-21" }),
			}),
		);
	});

	it("executes only the exact queued revision", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (_input, init) => {
			expect(JSON.parse(String(init?.body))).toEqual({ expected_revision: 3 });
			return new Response(JSON.stringify({ data: { ...runResponse(), status: "completed", revision: 5 } }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		await expect(executeAgentRun({ runId: "run-21", revision: 3 })).resolves.toMatchObject({
			runId: "run-21",
			status: "completed",
			revision: 5,
		});
		expect(fetchMock).toHaveBeenCalledWith(
			"/api/v1/agent/runs/run-21/execute",
			expect.objectContaining({ method: "POST" }),
		);
	});
});
