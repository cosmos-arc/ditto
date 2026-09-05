import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { ContextActionsProvider, type ContextActionsRequest } from "@/providers";
import type { PortfolioComparison, PortfolioComparisonIdentity } from "../api/portfolio-comparison";
import { PortfolioComparisonWorkspace } from "./portfolio-comparison-workspace";
import { PortfolioPage } from "./portfolio-page";

type Comparison = PortfolioComparison;

const renderContextActions = vi.fn((request: ContextActionsRequest) => (
	<a
		href="#context-action"
		data-context-id={request.contextId}
		data-context-type={request.contextType}
		data-objective={request.evidenceObjective}
	>
		{request.evidenceLabel ?? "请求证据分析"}
	</a>
));

const identity: PortfolioComparisonIdentity = {
	strategy_id: "strategy-1",
	model_portfolio_id: "model-main",
	paper_account_id: "paper-main",
	manual_account_id: "manual-main",
	paper_session_id: "paper-session-1",
	as_of: "2026-08-31",
	knowledge_cutoff: "2026-08-31T15:00:00+08:00",
	publication_cutoff: "2026-08-31T15:00:00+08:00",
	source_snapshot_ids: ["snapshot:stock", "snapshot:fund"],
	valuation_snapshot_id: "valuation:abc",
};

function portfolio(kind: "model" | "paper" | "manual", totalValue: string, weights: [string, string]) {
	return {
		portfolio_id: `${kind}-main`,
		portfolio_kind: kind,
		as_of: identity.as_of,
		valuation_snapshot_id: "valuation:abc",
		source_snapshot_ids: identity.source_snapshot_ids,
		currency: "CNY" as const,
		cash: kind === "model" ? "10000" : kind === "paper" ? "19800" : "29400",
		cash_weight: kind === "model" ? "0.10" : kind === "paper" ? "0.20" : "0.30",
		total_value: totalValue,
		invested_weight: kind === "model" ? "0.90" : kind === "paper" ? "0.80" : "0.70",
		realized_pnl: kind === "model" ? "0" : "1200",
		unrealized_pnl: kind === "manual" ? "800" : "1500",
		fees: kind === "model" ? "0" : "6.30",
		pending_event_count: kind === "paper" ? 1 : 0,
		alert_codes: kind === "paper" ? ["RISK_BLOCKED"] : [],
		positions: [
			{
				instrument_id: 600519,
				quantity: "100",
				last_price: "500",
				market_value: "50000",
				weight: weights[0],
				average_cost_value: "45000",
				realized_pnl: "0",
				unrealized_pnl: "5000",
				fees: "3.10",
				industry: "consumer",
			},
			{
				instrument_id: 510300,
				quantity: "1000",
				last_price: "40",
				market_value: "40000",
				weight: weights[1],
				average_cost_value: "38000",
				realized_pnl: "0",
				unrealized_pnl: "2000",
				fees: "3.20",
				industry: "fund",
			},
		],
	};
}

const zeroAttribution = {
	unfilled_bps: "0",
	slippage_amount: "0",
	fee_amount: "0",
	risk_blocked_bps: "0",
	user_choice_bps: "0",
};

const comparison: Comparison = {
	strategy_id: identity.strategy_id,
	as_of: identity.as_of,
	valuation_snapshot_id: "valuation:abc",
	source_snapshot_ids: identity.source_snapshot_ids,
	model: portfolio("model", "100000", ["0.50", "0.40"]),
	paper: portfolio("paper", "99000", ["0.45", "0.35"]),
	manual: portfolio("manual", "98000", ["0.40", "0.30"]),
	model_vs_paper: {
		comparison_kind: "model_vs_paper",
		baseline_portfolio_id: "model-main",
		observed_portfolio_id: "paper-main",
		total_abs_drift_bps: "1000",
		cash_drift_bps: "1000",
		items: [],
		attribution: {
			...zeroAttribution,
			unfilled_bps: "300",
			slippage_amount: "42.50",
			fee_amount: "6.30",
			risk_blocked_bps: "150",
		},
	},
	model_vs_manual: {
		comparison_kind: "model_vs_manual",
		baseline_portfolio_id: "model-main",
		observed_portfolio_id: "manual-main",
		total_abs_drift_bps: "2000",
		cash_drift_bps: "2000",
		items: [],
		attribution: { ...zeroAttribution, user_choice_bps: "2000" },
	},
	paper_vs_manual: {
		comparison_kind: "paper_vs_manual",
		baseline_portfolio_id: "paper-main",
		observed_portfolio_id: "manual-main",
		total_abs_drift_bps: "1000",
		cash_drift_bps: "1000",
		items: [],
		attribution: zeroAttribution,
	},
};

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return (
			<ContextActionsProvider renderActions={renderContextActions}>
				<QueryClientProvider client={client}>{children}</QueryClientProvider>
			</ContextActionsProvider>
		);
	};
}

afterEach(() => {
	vi.unstubAllEnvs();
	renderContextActions.mockClear();
	window.history.replaceState({}, "", "/portfolio");
});

describe("PortfolioComparisonWorkspace", () => {
	it("renders same-snapshot MODEL, PAPER and MANUAL columns with mutually meaningful attribution", async () => {
		server.use(http.get("/api/v1/portfolio/comparison", () => HttpResponse.json({ data: comparison })));

		render(<PortfolioComparisonWorkspace identity={identity} />, { wrapper: wrapper() });

		await expect(screen.findByRole("heading", { name: "MODEL / PAPER / MANUAL" })).resolves.toBeInTheDocument();
		expect(within(screen.getByTestId("portfolio-column-model")).getByText("¥100,000.00")).toBeInTheDocument();
		expect(within(screen.getByTestId("portfolio-column-paper")).getByText("¥99,000.00")).toBeInTheDocument();
		expect(within(screen.getByTestId("portfolio-column-manual")).getByText("¥98,000.00")).toBeInTheDocument();
		expect(screen.getByText("未成交 300 bps")).toBeInTheDocument();
		expect(screen.getByText("风险阻塞 150 bps")).toBeInTheDocument();
		expect(screen.getByText("用户选择 2,000 bps")).toBeInTheDocument();
		expect(screen.getByText("valuation:abc")).toBeInTheDocument();
		expect(screen.getByText("snapshot:stock + snapshot:fund")).toBeInTheDocument();
		const diagnostic = screen.getByRole("link", { name: "请求组合诊断" });
		expect(diagnostic).toHaveAttribute("data-context-type", "portfolio");
		expect(diagnostic.getAttribute("data-context-id")).toContain(identity.model_portfolio_id);
		expect(diagnostic.getAttribute("data-objective")).toContain(identity.paper_account_id);
		expect(diagnostic.getAttribute("data-objective")).toContain(identity.manual_account_id);
		expect(diagnostic.getAttribute("data-objective")).toContain(identity.paper_session_id);
		expect(diagnostic.getAttribute("data-objective")).toContain(identity.source_snapshot_ids[0] ?? "");
	});

	it("previews constraints and stress without exposing any apply action", async () => {
		let requestBody: Record<string, unknown> | undefined;
		server.use(
			http.get("/api/v1/portfolio/comparison", () => HttpResponse.json({ data: comparison })),
			http.post("/api/v1/portfolio/scenario-previews", async ({ request }) => {
				requestBody = (await request.json()) as Record<string, unknown>;
				return HttpResponse.json({
					data: {
						baseline_kind: "paper",
						proposed_weights: { "510300": "0.35", "600519": "0.35" },
						applied_constraints: [
							"cash_reserve_weight=0.15",
							"max_position_weight=0.35",
							"excluded_instrument_id=600519",
						],
						risk: {
							as_of: identity.as_of,
							valuation_snapshot_id: "valuation:abc",
							source_snapshot_ids: identity.source_snapshot_ids,
							before: {
								gross_exposure: 0.8,
								cash_weight: 0.2,
								industry_exposure: { consumer: 0.45, fund: 0.35 },
								stressed_return: -0.064,
							},
							after: {
								gross_exposure: 0.7,
								cash_weight: 0.3,
								industry_exposure: { fund: 0.35 },
								stressed_return: -0.028,
							},
							turnover: 0.18,
							constraint_findings: ["CASH_RESERVE_SATISFIED"],
						},
					},
				});
			}),
		);

		render(<PortfolioComparisonWorkspace identity={identity} />, { wrapper: wrapper() });
		await screen.findByRole("heading", { name: "MODEL / PAPER / MANUAL" });
		fireEvent.change(screen.getByLabelText("预演基线"), { target: { value: "paper" } });
		fireEvent.change(screen.getByLabelText("单仓上限"), { target: { value: "0.35" } });
		fireEvent.change(screen.getByLabelText("现金保留"), { target: { value: "0.15" } });
		fireEvent.change(screen.getByLabelText("排除标的"), { target: { value: "600519" } });
		fireEvent.change(screen.getByLabelText("市场冲击"), { target: { value: "-0.08" } });
		fireEvent.click(screen.getByRole("button", { name: "运行只读预演" }));

		await expect(screen.findByText("换手率 18.00%")).resolves.toBeInTheDocument();
		expect(screen.getByText("仅预演，不写入任何账户或 target")).toBeInTheDocument();
		expect(screen.queryByRole("button", { name: /应用|写入|调仓/u })).not.toBeInTheDocument();
		expect(requestBody).toMatchObject({
			baseline_kind: "paper",
			excluded_instrument_ids: [600519],
			max_position_weight: "0.35",
			cash_reserve_weight: "0.15",
			market_shock: -0.08,
		});
	});

	it("fails closed when exact identity is incomplete", () => {
		render(<PortfolioComparisonWorkspace />, { wrapper: wrapper() });

		expect(screen.getByRole("alert")).toHaveTextContent("缺少精确组合身份");
	});

	it("enters comparison mode only from a complete explicit URL identity", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const search = new URLSearchParams({
			mode: "comparison",
			strategy_id: identity.strategy_id,
			model_portfolio_id: identity.model_portfolio_id,
			paper_account_id: identity.paper_account_id,
			manual_account_id: identity.manual_account_id,
			paper_session_id: identity.paper_session_id,
			as_of: identity.as_of,
			knowledge_cutoff: identity.knowledge_cutoff,
			publication_cutoff: identity.publication_cutoff,
			valuation_snapshot_id: identity.valuation_snapshot_id ?? "",
		});
		for (const snapshotId of identity.source_snapshot_ids) search.append("source_snapshot_ids", snapshotId);
		window.history.replaceState({}, "", `/portfolio?${search.toString()}`);
		server.use(http.get("/api/v1/portfolio/comparison", () => HttpResponse.json({ data: comparison })));

		render(<PortfolioPage />, { wrapper: wrapper() });

		await expect(screen.findByRole("heading", { name: "MODEL / PAPER / MANUAL" })).resolves.toBeInTheDocument();
	});
});
