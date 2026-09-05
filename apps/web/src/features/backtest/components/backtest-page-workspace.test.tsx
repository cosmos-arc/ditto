import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { BacktestPage } from "./backtest-page";

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return { ...actual, useParams: () => ({ id: "bt-live-001" }) };
});

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } })}
		>
			{children}
		</QueryClientProvider>
	);
}

const RUN = {
	run_id: "bt-live-001",
	strategy_id: "seed_etf_industry_rotation",
	strategy_version: "4",
	mode: "backtest",
	status: "completed",
	started_at: "2026-08-28T09:00:00Z",
	completed_at: "2026-08-28T09:14:00Z",
	error_message: "",
	parent_run_id: "",
	benchmark_return: 7.4,
	progress_pct: 100,
	current_step: "completed",
	completed_days: 244,
	total_days: 244,
};

const REPORT = {
	run_id: "bt-live-001",
	period: { start: "2025-01-01", end: "2025-12-31" },
	initial_cash: 1_000_000,
	final_nav: 1.182,
	rebalance_freq: "monthly",
	nav_series: null,
	aggregated_trade_stats: {
		total_trades: 24,
		long_trades: 24,
		short_trades: 0,
		win_trades: 14,
		loss_trades: 10,
		win_rate: 0.5833,
		profit_factor: 1.65,
		avg_win: 14800,
		avg_loss: -8900,
		avg_win_loss_ratio: 1.66,
		max_consecutive_wins: 4,
		max_consecutive_losses: 3,
		avg_holding_days: 18.4,
		median_holding_days: 16,
		best_trade: 32000,
		worst_trade: -18000,
		avg_trade_return_pct: 0.012,
	},
	alpha_stats: {
		annualized_return: 0.182,
		annualized_volatility: 0.1,
		sharpe_ratio: 1.82,
		sortino_ratio: 2.35,
		max_drawdown: -0.125,
		max_drawdown_duration_days: 28,
		calmar_ratio: 1.45,
		information_ratio: 0.73,
		tracking_error: 0.06,
		beta: 0.82,
		alpha_annualized: 0.11,
		total_turnover: 3.2,
		avg_turnover_per_rebalance: 0.27,
		total_fees: 3120,
		net_return_after_cost: 0.174,
		cost_drag: 0.008,
	},
};

function registerHandlers() {
	server.use(
		http.get("/api/v1/backtests/runs/bt-live-001", () => HttpResponse.json({ data: RUN })),
		http.get("/api/v1/backtests/runs/bt-live-001/report", () => HttpResponse.json({ data: REPORT })),
		http.get("/api/v1/backtests/runs/bt-live-001/nav", () =>
			HttpResponse.json({
				data: [
					{ trade_date: "2025-01-02", nav: 1 },
					{ trade_date: "2025-12-31", nav: 1.182 },
				],
			}),
		),
		http.get("/api/v1/backtests/runs/bt-live-001/benchmark", () =>
			HttpResponse.json({
				data: {
					run_id: "bt-live-001",
					dates: ["2025-01-02", "2025-12-31"],
					navs: [1, 1.074],
					benchmark_return: 7.4,
				},
			}),
		),
		http.get("/api/v1/backtests/runs/bt-live-001/trades", () =>
			HttpResponse.json({
				data: [
					{
						trade_date: "2025-04-03",
						instrument_id: 600519,
						direction: "long",
						entry_date: "2025-03-03",
						exit_date: "2025-04-03",
						entry_price: 1500,
						exit_price: 1625,
						quantity: 100,
						pnl: 12500,
					},
				],
			}),
		),
		http.get("/api/v1/backtests/runs/bt-live-001/audit", () =>
			HttpResponse.json({
				data: [
					{
						id: 7,
						run_id: "bt-live-001",
						trade_date: "2025-04-03",
						record_type: "execution.fill",
						instrument_id: 600519,
						payload: { order_id: "order-7" },
						created_at: "2026-08-28T09:08:00Z",
					},
				],
			}),
		),
	);
}

describe("BacktestPage governed workspace", () => {
	beforeEach(registerHandlers);

	it("keeps exact run identity while switching among live report, trade, and audit resources", async () => {
		const user = userEvent.setup();
		render(<BacktestPage />, { wrapper });

		expect(await screen.findByRole("region", { name: "回测结果工作台" })).toBeInTheDocument();
		expect(await screen.findByRole("heading", { name: "Backtest bt-live-001" })).toBeInTheDocument();
		expect(await screen.findByText("1.82")).toBeInTheDocument();
		expect(screen.getByText("18.2%")).toBeInTheDocument();
		expect(await screen.findByText("净值与基准")).toBeInTheDocument();
		expect(screen.queryByText("当前持仓")).not.toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "收益报告" }));
		expect(screen.getByText("Performance report")).toBeInTheDocument();
		expect(screen.getByText(/1,000,000/)).toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "成交" }));
		expect(screen.getByText("Instrument #600519")).toBeInTheDocument();
		expect(screen.getByText(/12,500/)).toBeInTheDocument();

		await user.click(screen.getByRole("tab", { name: "审计证据" }));
		expect(screen.getByText("execution.fill")).toBeInTheDocument();
		expect(screen.getByTestId("backtest-detail-bottom")).toHaveTextContent(/2025-01-01.*2025-12-31/);

		await user.click(screen.getByRole("button", { name: "导出报告" }));
		expect(screen.getByRole("dialog", { name: "导出回测报告" })).toHaveTextContent("bt-live-001");
	});

	it("fails closed with a typed run retry and no synthetic performance", async () => {
		server.use(
			http.get("/api/v1/backtests/runs/bt-live-001", () =>
				HttpResponse.json({ detail: "run unavailable", error_code: "BACKTEST_RUN_UNAVAILABLE" }, { status: 503 }),
			),
		);

		render(<BacktestPage />, { wrapper });

		expect(await screen.findByRole("alert")).toHaveTextContent(/503 BACKTEST_RUN_UNAVAILABLE/);
		expect(screen.getByRole("button", { name: "重试回测运行" })).toBeInTheDocument();
		expect(screen.queryByText("Sharpe")).not.toBeInTheDocument();
	});
});
