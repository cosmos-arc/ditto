import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModelHistoryPanel } from "./model-history-panel";

function renderPanel() {
	return render(
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			<ModelHistoryPanel strategyId="strategy-model" asOf="2026-03-04" />
		</QueryClientProvider>,
	);
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("ModelHistoryPanel", () => {
	it("shows replay guidance before any query is committed", () => {
		renderPanel();
		expect(screen.getByText("模型目标（Model）")).toBeInTheDocument();
		expect(screen.getByText(/填写区间与初始资本后重放/)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "重放目标" })).toBeEnabled();
	});

	it("replays with the committed identity and renders saved targets and numbers", async () => {
		const user = userEvent.setup();
		let requestedHref: string | undefined;
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async (input) => {
				requestedHref = input instanceof Request ? input.url : String(input);
				return new Response(
					JSON.stringify({
						data: {
							result_id: "model-history:sha256:panel-1",
							strategy_id: "strategy-model",
							currency: "CNY",
							start_date: "2026-03-02",
							end_date: "2026-03-04",
							initial_capital: "100000.00",
							knowledge_cutoff: "2026-03-04T08:00:00Z",
							publication_cutoff: "2026-03-04T08:00:00Z",
							empty_reason: null,
							targets: [
								{
									signal_date: "2026-03-02",
									artifact_id: "signal-package-a",
									checksum: "sha256:aaa",
								},
							],
							method: "twr-linked-v1",
							valuation_policy_version: "account-valuation-stale-evidence-v1",
							points: [
								{
									on_date: "2026-03-02",
									valuation_instant: "2026-03-02T23:59:59.999999+08:00",
									total_value: "100000.00",
									cash: "0.00",
									external_flow: "0",
									period_return: null,
									cumulative_return: "0",
									segment_id: 0,
									price_time: "2026-03-02T07:00:00Z",
									stale: false,
									source_snapshot_ids: ["snapshot:stock_daily:1"],
									quality: [],
								},
							],
							segments: [
								{
									segment_id: 0,
									start_date: "2026-03-02",
									end_date: "2026-03-02",
									start_value: "100000.00",
									end_value: "100000.00",
									linked_return: null,
									closed_reason: "range_end",
									quality: [],
								},
							],
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				);
			}),
		);
		renderPanel();

		await user.clear(screen.getByLabelText("Model 重放开始日期"));
		await user.type(screen.getByLabelText("Model 重放开始日期"), "2026-03-02");
		await user.clear(screen.getByLabelText("Model 知识截止"));
		await user.type(screen.getByLabelText("Model 知识截止"), "2026-03-04T08:00:00Z");
		await user.clear(screen.getByLabelText("Model 初始资本"));
		await user.type(screen.getByLabelText("Model 初始资本"), "100000");
		await user.click(screen.getByRole("button", { name: "重放目标" }));

		await waitFor(() => {
			expect(screen.getByText(/model-history:sha256:panel-1/)).toBeInTheDocument();
		});
		const url = new URL(requestedHref ?? "");
		expect(url.pathname).toBe("/api/v1/portfolio/model-history");
		expect(url.searchParams.get("strategy_id")).toBe("strategy-model");
		expect(url.searchParams.get("initial_capital")).toBe("100000.00");
		expect(screen.getByText(/signal-package-a/)).toBeInTheDocument();
		expect(screen.getByText(/2026-03-02 的保存目标/)).toBeInTheDocument();
	});

	it("explains an empty replay and labels missing-target gap rows", async () => {
		const user = userEvent.setup();
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(
				async () =>
					new Response(
						JSON.stringify({
							data: {
								result_id: "model-history:sha256:empty-1",
								strategy_id: "strategy-model",
								currency: "CNY",
								start_date: "2026-03-02",
								end_date: "2026-03-04",
								initial_capital: "100000.00",
								knowledge_cutoff: "2026-03-04T08:00:00Z",
								publication_cutoff: "2026-03-04T08:00:00Z",
								empty_reason: "no_visible_targets",
								targets: [],
								method: "twr-linked-v1",
								valuation_policy_version: "account-valuation-stale-evidence-v1",
								points: [
									{
										on_date: "2026-03-02",
										valuation_instant: "2026-03-02T23:59:59.999999+08:00",
										total_value: null,
										cash: null,
										external_flow: "0",
										period_return: null,
										cumulative_return: null,
										segment_id: null,
										price_time: null,
										stale: false,
										source_snapshot_ids: [],
										quality: [{ code: "target_missing", detail: "" }],
									},
								],
								segments: [],
							},
						}),
						{ status: 200, headers: { "Content-Type": "application/json" } },
					),
			),
		);
		renderPanel();

		await user.clear(screen.getByLabelText("Model 重放开始日期"));
		await user.type(screen.getByLabelText("Model 重放开始日期"), "2026-03-02");
		await user.clear(screen.getByLabelText("Model 知识截止"));
		await user.type(screen.getByLabelText("Model 知识截止"), "2026-03-04T08:00:00Z");
		await user.click(screen.getByRole("button", { name: "重放目标" }));

		await waitFor(() => {
			expect(screen.getByText(/区间内没有可见的保存目标，无可重放历史（no_visible_targets）/)).toBeInTheDocument();
		});
		expect(screen.getByText("缺保存目标")).toBeInTheDocument();
	});

	it("renders an error with retry when the replay fails", async () => {
		const user = userEvent.setup();
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () => new Response("boom", { status: 500 })),
		);
		renderPanel();

		await user.click(screen.getByRole("button", { name: "重放目标" }));

		await waitFor(() => {
			expect(screen.getByRole("alert")).toHaveTextContent(/Model 历史重放失败/);
		});
		expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
	});
});
