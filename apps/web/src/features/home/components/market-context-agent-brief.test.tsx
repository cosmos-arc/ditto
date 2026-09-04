import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { AgentFindingsSection } from "./agent-findings-section";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

function run(status: "queued" | "completed") {
	return {
		authority_hash: "a".repeat(64),
		artifact_refs: status === "completed" ? ["certification://stock_daily/report-1"] : [],
		context: {
			context_id: "market-regime:sha256:mock-context:snapshot-set:sha256:mock-context",
			context_type: "market_context",
		},
		created_at: "2026-08-31T09:00:00Z",
		event_cursor: status === "completed" ? 4 : 1,
		evidence_refs: status === "completed" ? ["evidence://market-context/exact"] : [],
		execution_plan: null,
		failure_code: null,
		finished_at: status === "completed" ? "2026-08-31T09:00:03Z" : null,
		guardrail: status === "completed" ? { reason_code: null, status: "passed" } : null,
		manifest_hash: "b".repeat(64),
		max_model_spend_usd: "0.25",
		max_model_tokens: 2048,
		model_profile: "balanced",
		objective: "生成 MarketContext EvidenceBrief",
		objective_hash: "c".repeat(64),
		output_summary: status === "completed" ? "风险偏好偏强（0.28），但波动率仍对 drawdown guard 形成压力。" : null,
		projection_reason: null,
		projection_state: "complete",
		projection_updated_at: "2026-08-31T09:00:03Z",
		projection_version: 1,
		revision: status === "completed" ? 2 : 0,
		run_id: "run-market-1",
		session_id: "session-market-1",
		started_at: status === "completed" ? "2026-08-31T09:00:01Z" : null,
		status,
		tool_records:
			status === "completed"
				? [
						{
							arguments_hash: "d".repeat(64),
							artifact_refs: ["certification://stock_daily/report-1"],
							call_id: "call-market-1",
							evidence_refs: ["evidence://market-context/exact"],
							result_hash: "e".repeat(64),
							tool_name: "market_context_evidence",
						},
					]
				: [],
		usage: null,
	};
}

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
});

describe("Today MarketContext Agent Brief", () => {
	it("creates an exact snapshot-bound run and renders authenticated evidence", async () => {
		let createBody: Record<string, unknown> | null = null;
		server.use(
			http.post("/api/v1/agent/sessions", () =>
				HttpResponse.json({
					data: {
						created_at: "2026-08-31T09:00:00Z",
						retention_class: "standard",
						session_id: "session-market-1",
					},
				}),
			),
			http.post("/api/v1/agent/runs", async ({ request }) => {
				createBody = (await request.json()) as Record<string, unknown>;
				return HttpResponse.json({ data: run("queued") }, { status: 201 });
			}),
			http.post("/api/v1/agent/runs/run-market-1/execute", () => HttpResponse.json({ data: run("completed") })),
		);

		const user = userEvent.setup();
		render(<AgentFindingsSection />, { wrapper: wrapper() });

		await user.click(await screen.findByRole("button", { name: "生成 MarketContext Agent Brief" }));
		await expect(screen.findByText(/风险偏好偏强/)).resolves.toBeInTheDocument();
		expect(screen.getByText("evidence://market-context/exact")).toBeInTheDocument();
		expect(screen.getByText("market_context_evidence")).toBeInTheDocument();
		await waitFor(() => {
			expect(createBody).toMatchObject({
				context: {
					context_id: "market-regime:sha256:mock-context:snapshot-set:sha256:mock-context",
					context_type: "market_context",
				},
				execution_scope: {
					decision_time: expect.any(String),
					knowledge_cutoff: expect.any(String),
					publication_cutoff: expect.any(String),
					source_snapshot_id: "snapshot-set:sha256:mock-context",
				},
			});
		});
	});
});
