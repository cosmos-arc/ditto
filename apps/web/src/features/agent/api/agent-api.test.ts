import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/api/generated/schema";
import { mockAgentApprovals, mockAgentCampaigns, mockAgentSessions } from "@/mocks/fixtures/agent";
import { capturedRequest, requestJson, requestPath } from "@/test/request";
import type { AgentCampaignManifestInput } from "../types";
import {
	cancelAgentRun,
	createAgentRun,
	decideAgentApproval,
	executeAgentRun,
	getAgentApproval,
	getAgentCampaign,
	getAgentRun,
	listAgentApprovals,
	listAgentCampaigns,
	listAgentRuns,
	listAgentSessions,
	validateAgentCampaignStep,
} from "./agent-api";

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

const campaignManifest: AgentCampaignManifestInput = {
	campaign_id: "campaign-coverage",
	objective: "Validate one falsifiable signal without widening authority.",
	primary_metric_id: "sharpe_ratio",
	hypothesis: {
		statement: "Signal persists after costs.",
		mechanism: "Liquidity provision.",
		universe_hash: "d".repeat(64),
		expected_signal: "Sharpe improves.",
		failure_condition: "Sharpe does not improve.",
	},
	baseline_candidate: {
		candidate_id: "baseline-1",
		ordinal: 0,
		parameters: { lookback: 20 },
		data_requirement_hashes: ["e".repeat(64)],
	},
	experiment_plan: {
		fold_protocol_id: "walk-forward",
		fold_protocol_version: 1,
		fold_protocol_hash: "f".repeat(64),
		snapshot_id: "snapshot-1",
		validation_objective_hash: "1".repeat(64),
		cost_model_hash: "2".repeat(64),
		seed: 7,
		purge_sessions: 2,
		embargo_sessions: 1,
	},
	budget: {
		candidate_limit: 4,
		fold_run_limit: 12,
		generation_limit: 2,
		concurrent_sandbox_limit: 1,
		wall_time_limit_seconds: 120,
		temporary_storage_limit_bytes: 1_000_000,
		model_spend_limit_usd_micros: 100_000,
		sandbox_resource_limits: {
			cpu_count: 1,
			memory_bytes: 512_000_000,
			process_limit: 8,
			temporary_storage_bytes: 1_000_000,
			wall_time_seconds: 60,
			output_bytes: 100_000,
		},
	},
	search_axis: "parameters",
	search_space_hash: "3".repeat(64),
	lineage_root: "ditto://campaign/campaign-coverage",
	stopping_rule: "two generations without improvement",
	allowed_tools: ["factor.evaluate"],
	prohibited_actions: ["broker.submit"],
};

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
		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe(
			"/api/v1/agent/runs?status=running&session_id=session-7&context_type=factor&context_id=factor%3Amom-20&limit=20&offset=20",
		);
		expect(request.method).toBe("GET");
	});

	it("validates a structured Campaign wizard step without an idempotency header", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const body = (await requestJson(capturedRequest([[input, init]]))) as Record<string, unknown>;
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
		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe("/api/v1/agent/campaigns/validation");
		expect(request.method).toBe("POST");
	});

	it("creates a run with an explicit PIT scope and server-derived authority", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const body = (await requestJson(capturedRequest([[input, init]]))) as Record<string, unknown>;
			expect(body).not.toHaveProperty("authority_hash");
			expect(body["execution_scope"]).toEqual({
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
		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe("/api/v1/agent/runs");
		expect(request.method).toBe("POST");
		expect(request.headers.get("Idempotency-Key")).toBe("run-create-21");
	});

	it("executes only the exact queued revision", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			expect(await requestJson(capturedRequest([[input, init]]))).toEqual({ expected_revision: 3 });
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
		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe("/api/v1/agent/runs/run-21/execute");
		expect(request.method).toBe("POST");
	});

	it("accepts the durable decision receipt returned by an approval mutation", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			expect(await requestJson(capturedRequest([[input, init]]))).toEqual({
				decision: "approve",
				expected_action_hash: "a".repeat(64),
				operator_id: "operator-1",
			});
			return new Response(
				JSON.stringify({
					data: {
						action_hash: "a".repeat(64),
						approval_id: "approval-1",
						decided_at: "2026-09-04T00:00:00Z",
						operator_id: "operator-1",
						reason: null,
						run_id: "run-1",
						status: "approved",
					},
				}),
				{ status: 200, headers: { "Content-Type": "application/json" } },
			);
		});
		vi.stubGlobal("fetch", fetchMock);

		await expect(
			decideAgentApproval({
				approvalId: "approval-1",
				actionHash: "a".repeat(64),
				decision: "approve",
				operatorId: "operator-1",
			}),
		).resolves.toBeUndefined();
		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe("/api/v1/agent/approvals/approval-1/decision");
		expect(request.method).toBe("POST");
	});

	it("uses bounded pagination defaults and maps absent run or campaign evidence to explicit nulls", async () => {
		const runWithoutOptionalEvidence: AgentRunResponse = {
			...runResponse(),
			context: null,
			guardrail: null,
			usage: null,
		};
		const campaignWithoutOptionalEvidence = {
			...mockAgentCampaigns[0],
			guardrail: null,
			usage: null,
		};
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const path = requestPath(capturedRequest([[input, init]])).split("?")[0];
			switch (path) {
				case "/api/v1/agent/sessions":
					return Response.json({ data: mockAgentSessions });
				case "/api/v1/agent/runs":
				case "/api/v1/agent/runs/run-21":
				case "/api/v1/agent/runs/run-21/cancel":
					return Response.json({
						data: path === "/api/v1/agent/runs" ? [runWithoutOptionalEvidence] : runWithoutOptionalEvidence,
					});
				case "/api/v1/agent/approvals":
					return Response.json({ data: mockAgentApprovals });
				case "/api/v1/agent/approvals/approval-research-104":
					return Response.json({ data: mockAgentApprovals[0] });
				case "/api/v1/agent/campaigns":
					return Response.json({ data: [campaignWithoutOptionalEvidence] });
				case "/api/v1/agent/campaigns/campaign-alpha-011":
					return Response.json({ data: campaignWithoutOptionalEvidence });
				default:
					throw new Error(`Unhandled Agent API test request: ${path}`);
			}
		});
		vi.stubGlobal("fetch", fetchMock);

		await expect(listAgentSessions()).resolves.toMatchObject({
			pagination: { total: 2, limit: 20, offset: 0, hasMore: false },
		});
		await expect(listAgentRuns()).resolves.toMatchObject({
			items: [{ context: null, guardrail: null, usage: null }],
			pagination: { total: 1, limit: 20, offset: 0, hasMore: false },
		});
		await expect(getAgentRun("run-21")).resolves.toMatchObject({ runId: "run-21", context: null });
		await expect(cancelAgentRun({ runId: "run-21", revision: 3 })).resolves.toMatchObject({ revision: 3 });
		await expect(
			listAgentApprovals({ status: "pending", runId: "run-research-104", limit: 1, offset: 0 }),
		).resolves.toMatchObject({ items: [{ approvalId: "approval-research-104" }] });
		await expect(getAgentApproval("approval-research-104")).resolves.toMatchObject({
			approvalId: "approval-research-104",
		});
		await expect(listAgentCampaigns({ status: "running", limit: 1, offset: 0 })).resolves.toMatchObject({
			items: [{ guardrail: null, usage: null }],
		});
		await expect(getAgentCampaign("campaign-alpha-011")).resolves.toMatchObject({
			campaignId: "campaign-alpha-011",
			guardrail: null,
			usage: null,
		});
	});

	it("serializes every campaign validation stage as a detached copy", async () => {
		const bodies: unknown[] = [];
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const request = capturedRequest([[input, init]]);
			bodies.push(await requestJson(request));
			const body = bodies.at(-1) as { readonly step?: string; readonly manifest?: unknown };
			return Response.json({
				data: {
					step: body.step ?? "manifest",
					valid: true,
					canonical_manifest: body.manifest ?? null,
					manifest_hash: body.manifest ? "4".repeat(64) : null,
				},
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		await validateAgentCampaignStep({
			step: "experiment_plan",
			search_axis: campaignManifest.search_axis,
			baseline_candidate: campaignManifest.baseline_candidate,
			experiment_plan: campaignManifest.experiment_plan,
		});
		await validateAgentCampaignStep({
			step: "governance",
			budget: campaignManifest.budget,
			search_space_hash: campaignManifest.search_space_hash,
			lineage_root: campaignManifest.lineage_root,
			stopping_rule: campaignManifest.stopping_rule,
			allowed_tools: campaignManifest.allowed_tools,
			prohibited_actions: campaignManifest.prohibited_actions,
		});
		await expect(validateAgentCampaignStep({ step: "manifest", manifest: campaignManifest })).resolves.toMatchObject({
			step: "manifest",
			valid: true,
			manifestHash: "4".repeat(64),
		});

		expect(bodies).toHaveLength(3);
		expect(bodies[0]).toMatchObject({ step: "experiment_plan", baseline_candidate: { parameters: { lookback: 20 } } });
		expect(bodies[1]).toMatchObject({ step: "governance", allowed_tools: ["factor.evaluate"] });
		expect(bodies[2]).toMatchObject({
			step: "manifest",
			manifest: { campaign_id: "campaign-coverage", prohibited_actions: ["broker.submit"] },
		});
	});

	it("includes an explicit nullable rejection reason without weakening the approval authority hash", async () => {
		let body: unknown;
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			body = await requestJson(capturedRequest([[input, init]]));
			return Response.json({
				data: {
					action_hash: "a".repeat(64),
					approval_id: "approval-1",
					decided_at: "2026-09-04T00:00:00Z",
					operator_id: "operator-1",
					reason: null,
					run_id: "run-1",
					status: "rejected",
				},
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		await decideAgentApproval({
			approvalId: "approval-1",
			actionHash: "a".repeat(64),
			decision: "reject",
			operatorId: "operator-1",
			reason: null,
		});
		expect(body).toEqual({
			decision: "reject",
			expected_action_hash: "a".repeat(64),
			operator_id: "operator-1",
			reason: null,
		});
	});
});
