import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { ETFAllocationReview } from "./etf-allocation-review";

afterEach(() => window.history.replaceState(null, "", "/"));

it("restores an exact version and account while keeping unpriced actual weights unknown", async () => {
	window.history.replaceState(
		null,
		"",
		"/portfolio?etfVersion=v1&etfReviewAccount=paper:paper-a&etfReviewAsOf=2026-09-02",
	);
	server.use(
		http.get("/api/v1/portfolio/etf-allocations/demo/versions", () =>
			HttpResponse.json({
				data: [
					{
						version_id: "v1",
						allocation_id: "demo",
						parent_version_id: null,
						asof: "2026-09-01",
						knowledge_cutoff: "2026-09-01T09:00:00Z",
						source_snapshot_id: "snapshot:recorded:etf",
						mode: "equal",
						weights: { "2000001": "0.40000000", "2000002": "0.40000000" },
						cash_weight: "0.20000000",
						max_position_weight: "0.50000000",
						tracking_exposure: { "000300.SH": "0.80000000" },
						reason: "broad exposure",
						rule_version: "etf-allocation-v1",
						paper_status: "research_only",
						review_status: "review_approved",
						created_at: "2026-09-01T09:00:00Z",
					},
				],
			}),
		),
		http.get("/api/v1/paper/accounts", () =>
			HttpResponse.json({
				data: {
					accounts: [
						{
							account_id: "paper-a",
							account_kind: "paper",
							account_name: "模拟甲",
							currency: "CNY",
							opened_at: "2026-09-01T00:00:00Z",
						},
					],
				},
			}),
		),
		http.get("/api/v1/manual/accounts", () => HttpResponse.json({ data: { accounts: [] } })),
		http.get("/api/v1/paper/accounts/paper-a/ledger", () =>
			HttpResponse.json({
				data: {
					account: {
						account_id: "paper-a",
						account_kind: "paper",
						name: "模拟甲",
						currency: "CNY",
						opened_at: "2026-09-01T00:00:00Z",
					},
					events: [],
					snapshot: {
						account_id: "paper-a",
						account_kind: "paper",
						as_of: "2026-09-02",
						currency: "CNY",
						cash: { available: "60000", frozen: "0", settled: "60000", total: "60000" },
						event_count: 1,
						ledger_hash: "account-ledger:sha256:paper-a",
						positions: [
							{
								instrument_id: 2000001,
								quantity: "100",
								available_quantity: "100",
								average_cost: "4",
								last_price: "0",
								market_value: "0",
								realized_pnl: "0",
								total_fees: "0",
								unrealized_pnl: "0",
							},
						],
						realized_pnl: "0",
						total_fees: "0",
						total_value: "60000",
						unrealized_pnl: "0",
						valuation_complete: false,
					},
				},
			}),
		),
	);
	render(
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			<ETFAllocationReview allocationId="demo" />
		</QueryClientProvider>,
	);
	expect(await screen.findByText(/已知同指数目标暴露：000300.SH 0.80000000/)).toBeVisible();
	expect(await screen.findByText(/Paper 模拟成交账本/)).toBeVisible();
	expect(screen.getByText(/缺少同日价格证据，无法计算实际权重/)).toBeVisible();
	expect(screen.getByText(/当前配置目标不会回填历史/)).toBeVisible();
	fireEvent.change(screen.getByLabelText("复盘账本日期"), { target: { value: "2026-09-03" } });
	expect(new URLSearchParams(window.location.search).get("etfReviewAsOf")).toBe("2026-09-03");
});
