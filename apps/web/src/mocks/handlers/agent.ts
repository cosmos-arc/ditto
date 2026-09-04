import { HttpResponse, http, type RequestHandler } from "msw";
import {
	mockAgentApprovals,
	mockAgentCampaigns,
	mockAgentCapability,
	mockAgentRuns,
	mockAgentSessions,
} from "../fixtures/agent";

function page<T>(items: readonly T[], request: Request) {
	const url = new URL(request.url);
	const limit = Number(url.searchParams.get("limit") ?? items.length);
	const offset = Number(url.searchParams.get("offset") ?? 0);
	return HttpResponse.json({
		data: items.slice(offset, offset + limit),
		pagination: {
			total: items.length,
			limit,
			offset,
			has_more: offset + limit < items.length,
		},
	});
}

export const agentHandlers: RequestHandler[] = [
	http.get("/api/v1/agent/capabilities", () => HttpResponse.json({ data: mockAgentCapability })),
	http.get("/api/v1/agent/sessions", ({ request }) => page(mockAgentSessions, request)),
	http.get("/api/v1/agent/runs", ({ request }) => {
		const url = new URL(request.url);
		const status = url.searchParams.get("status");
		const sessionId = url.searchParams.get("session_id");
		const contextType = url.searchParams.get("context_type");
		const contextId = url.searchParams.get("context_id");
		const runs = mockAgentRuns.filter(
			(run) =>
				(!status || run.status === status) &&
				(!sessionId || run.session_id === sessionId) &&
				(!contextType || run.context?.context_type === contextType) &&
				(!contextId || run.context?.context_id === contextId),
		);
		return page(runs, request);
	}),
	http.get("/api/v1/agent/runs/:runId/events", ({ params }) => {
		return new HttpResponse(
			`id: 18\nevent: run_updated\ndata: {"run_id":"${String(params.runId)}","status":"waiting_approval"}\n\n`,
			{ headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" } },
		);
	}),
	http.get("/api/v1/agent/runs/:runId", ({ params }) => {
		const run = mockAgentRuns.find((item) => item.run_id === params.runId);
		return run ? HttpResponse.json({ data: run }) : HttpResponse.json({ detail: "Run not found" }, { status: 404 });
	}),
	http.get("/api/v1/agent/approvals", ({ request }) => {
		const url = new URL(request.url);
		const status = url.searchParams.get("status");
		const runId = url.searchParams.get("run_id");
		const approvals = mockAgentApprovals.filter(
			(approval) => (!status || approval.status === status) && (!runId || approval.run_id === runId),
		);
		return page(approvals, request);
	}),
	http.get("/api/v1/agent/approvals/:approvalId", ({ params }) => {
		const approval = mockAgentApprovals.find((item) => item.approval_id === params.approvalId);
		return approval
			? HttpResponse.json({ data: approval })
			: HttpResponse.json({ detail: "Approval not found" }, { status: 404 });
	}),
	http.get("/api/v1/agent/campaigns", ({ request }) => {
		const url = new URL(request.url);
		const status = url.searchParams.get("status");
		return page(
			status ? mockAgentCampaigns.filter((campaign) => campaign.status === status) : mockAgentCampaigns,
			request,
		);
	}),
	http.get(
		"/api/v1/agent/campaigns/:campaignId/events",
		({ params }) =>
			new HttpResponse(`id: 18\nevent: campaign_completed\ndata: {"campaign_id":"${String(params.campaignId)}"}\n\n`, {
				headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
			}),
	),
	http.get("/api/v1/agent/campaigns/:campaignId", ({ params }) => {
		const campaign = mockAgentCampaigns.find((item) => item.campaign_id === params.campaignId);
		return campaign
			? HttpResponse.json({ data: campaign })
			: HttpResponse.json({ detail: "Campaign not found" }, { status: 404 });
	}),
];
