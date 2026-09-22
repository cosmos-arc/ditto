import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ManualHistoryPanel } from "./manual-history-panel";

const LEDGER_REVISION = { event_count: 2, ledger_hash: "account-ledger:sha256:panel" };

function historyPayload() {
	return {
		result_id: "manual-history:sha256:panel-1",
		account_id: "manual-main",
		currency: "CNY",
		start_date: "2026-03-02",
		end_date: "2026-03-04",
		knowledge_cutoff: "2026-03-04T08:00:00Z",
		publication_cutoff: "2026-03-04T08:00:00Z",
		source_snapshot_ids: ["snapshot:stock_daily:1"],
		ledger_revision: LEDGER_REVISION,
		method: "twr-linked-v1",
		valuation_policy_version: "manual-valuation-stale-evidence-v1",
		points: [
			{
				on_date: "2026-03-02",
				valuation_instant: "2026-03-02T23:59:59.999999+08:00",
				total_value: "100.00",
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
			{
				on_date: "2026-03-03",
				valuation_instant: "2026-03-03T23:59:59.999999+08:00",
				total_value: "110.00",
				cash: "0.00",
				external_flow: "0",
				period_return: "0.1",
				cumulative_return: "0.1",
				segment_id: 0,
				price_time: "2026-03-03T07:00:00Z",
				stale: false,
				source_snapshot_ids: ["snapshot:stock_daily:1"],
				quality: [],
			},
			{
				on_date: "2026-03-04",
				valuation_instant: "2026-03-04T23:59:59.999999+08:00",
				total_value: "221.00",
				cash: "100.00",
				external_flow: "100.00",
				period_return: "0.05",
				cumulative_return: "0.155",
				segment_id: 0,
				price_time: "2026-03-04T07:00:00Z",
				stale: false,
				source_snapshot_ids: ["snapshot:stock_daily:1"],
				quality: [],
			},
		],
		segments: [
			{
				segment_id: 0,
				start_date: "2026-03-02",
				end_date: "2026-03-04",
				start_value: "100.00",
				end_value: "221.00",
				linked_return: "0.155",
				closed_reason: "range_end",
				quality: [],
			},
		],
	};
}

function renderPanel(asOf = "2026-03-04") {
	return render(
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			<ManualHistoryPanel accountId="manual-main" asOf={asOf} ledgerRevision={LEDGER_REVISION} />
		</QueryClientProvider>,
	);
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("ManualHistoryPanel", () => {
	it("shows identity guidance before any query is committed", () => {
		renderPanel();
		expect(screen.getByText(/填写区间与价格快照后查询/)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "查询历史" })).toBeDisabled();
	});

	it("fetches with the committed identity and renders backend numbers only", async () => {
		const user = userEvent.setup();
		let requestedHref: string | undefined;
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async (input) => {
				requestedHref = input instanceof Request ? input.url : String(input);
				return new Response(JSON.stringify({ data: historyPayload() }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				});
			}),
		);
		renderPanel();

		await user.clear(screen.getByLabelText("历史开始日期"));
		await user.type(screen.getByLabelText("历史开始日期"), "2026-03-02");
		await user.clear(screen.getByLabelText("知识截止"));
		await user.type(screen.getByLabelText("知识截止"), "2026-03-04T08:00:00Z");
		await user.type(screen.getByLabelText("价格快照"), "snapshot:stock_daily:1");
		await user.click(screen.getByRole("button", { name: "查询历史" }));

		await waitFor(() => {
			expect(screen.getAllByText("15.50%").length).toBeGreaterThan(0);
		});
		const requestedUrl = new URL(requestedHref ?? "");
		expect(requestedUrl.pathname).toBe("/api/v1/manual/accounts/manual-main/history");
		expect(requestedUrl.searchParams.get("ledger_hash")).toBe(LEDGER_REVISION.ledger_hash);
		expect(requestedUrl.searchParams.get("ledger_event_count")).toBe("2");
		expect(screen.getAllByText("10.00%").length).toBeGreaterThan(0);
		expect(screen.getAllByText("5.00%").length).toBeGreaterThan(0);
		expect(screen.getAllByText("221.00").length).toBeGreaterThan(0);
		expect(screen.getByText(/区间结束/)).toBeInTheDocument();
		expect(screen.getByText(/manual-history:sha256:panel-1/)).toBeInTheDocument();
	});

	it("renders an error with retry when the query fails", async () => {
		const user = userEvent.setup();
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () => new Response("boom", { status: 500 })),
		);
		renderPanel();

		await user.type(screen.getByLabelText("价格快照"), "snapshot:stock_daily:1");
		await user.click(screen.getByRole("button", { name: "查询历史" }));

		await waitFor(() => {
			expect(screen.getByRole("alert")).toHaveTextContent(/历史收益查询失败/);
		});
		expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
	});
});
