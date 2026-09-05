import { beforeEach, describe, expect, it } from "vitest";
import type {
	AgentApprovalResponse,
	AgentCampaignResponse,
	AgentRunResponse,
	AgentSessionResponse,
} from "@/features/agent/api/agent-api";
import { parseAgentSse } from "@/features/agent/api/agent-event-stream";
import { server } from "@/mocks/server";
import { agentHandlers } from "./agent";

beforeEach(() => {
	server.use(...agentHandlers);
});

describe("agentHandlers", () => {
	it("serves deterministic capability and Campaign projections for visual fixtures", async () => {
		const [capabilityResponse, campaignsResponse] = await Promise.all([
			fetch("/api/v1/agent/capabilities"),
			fetch("/api/v1/agent/campaigns?limit=50&offset=0"),
		]);
		const capability = await capabilityResponse.json();
		const campaigns = (await campaignsResponse.json()) as { data: AgentCampaignResponse[] };

		expect(capability.data).toMatchObject({ enabled: true, runtime_state: "available" });
		expect(campaigns.data).toHaveLength(3);
		expect(campaigns.data[0]).toMatchObject({
			campaign_id: "campaign-alpha-011",
			source_snapshot_id: "snapshot-11",
			status: "running",
		});
	});

	it("returns the same stable projection from the Campaign detail endpoint", async () => {
		const response = await fetch("/api/v1/agent/campaigns/campaign-alpha-011");
		const payload = (await response.json()) as { data: AgentCampaignResponse };

		expect(response.status).toBe(200);
		expect(payload.data.event_cursor).toBe(17);
		expect(payload.data.evidence_refs).toContain("ditto://evidence/alpha/momentum-stability");
	});

	it("serves the Console session, Run, and Approval collections without backend fallthrough", async () => {
		const [sessionsResponse, runsResponse, approvalsResponse] = await Promise.all([
			fetch("/api/v1/agent/sessions?limit=20&offset=0"),
			fetch("/api/v1/agent/runs?limit=20&offset=0"),
			fetch("/api/v1/agent/approvals?limit=20&offset=0"),
		]);
		const sessions = (await sessionsResponse.json()) as { data: AgentSessionResponse[] };
		const runs = (await runsResponse.json()) as { data: AgentRunResponse[] };
		const approvals = (await approvalsResponse.json()) as { data: AgentApprovalResponse[] };

		expect(sessionsResponse.status).toBe(200);
		expect(runsResponse.status).toBe(200);
		expect(approvalsResponse.status).toBe(200);
		expect(sessions.data[0]).toMatchObject({ session_id: "session-research-104", retention_class: "audit" });
		expect(runs.data[0]).toMatchObject({ run_id: "run-research-104", status: "waiting_approval" });
		expect(approvals.data[0]).toMatchObject({ approval_id: "approval-research-104", status: "pending" });
	});

	it("serves runtime-valid Run and Campaign stream fixtures", async () => {
		const [runResponse, campaignResponse] = await Promise.all([
			fetch("/api/v1/agent/runs/run-research-104/events"),
			fetch("/api/v1/agent/campaigns/campaign-alpha-011/events"),
		]);
		const [runBody, campaignBody] = await Promise.all([runResponse.text(), campaignResponse.text()]);

		expect(runResponse.headers.get("content-type")).toContain("text/event-stream");
		expect(campaignResponse.headers.get("content-type")).toContain("text/event-stream");
		expect(parseAgentSse(runBody, 17, { kind: "runs", identity: "run-research-104" })).toEqual([
			expect.objectContaining({ id: 18, eventType: "approval_waiting" }),
		]);
		expect(parseAgentSse(campaignBody, 17, { kind: "campaigns", identity: "campaign-alpha-011" })).toEqual([
			expect.objectContaining({ id: 18, eventType: "campaign_completed" }),
		]);
	});
});
