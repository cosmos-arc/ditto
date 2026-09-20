import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import type { BacktestRun } from "../types";
import { BacktestMultiRunCompare } from "./backtest-multi-run-compare";

// jsdom 无法承载 fancy-canvas：barrel 级同步 stub ChartCockpit 捕获喂养序列；
// ChartLegend 以等价行为内联重放（真实 legend 的开关行为由组件自身测试覆盖）。
const cockpitProps: { series: { id: string; bars: unknown[] }[]; chartId: string }[] = [];
vi.mock("@/components/chart", () => ({
	ChartCockpit: (props: { series: { id: string; bars: unknown[] }[]; chartId: string }) => {
		cockpitProps.push(props);
		return createElement("div", {
			"data-testid": "chart-cockpit-stub",
			"data-chart-series-ids": props.series.map((spec) => spec.id).join(","),
		});
	},
	ChartLegend: ({
		items,
		onToggle,
		testId,
	}: {
		items: { id: string; label: string; visible: boolean }[];
		onToggle: (id: string) => void;
		testId?: string;
	}) =>
		createElement(
			"div",
			{ "data-testid": testId },
			items.map((item) =>
				createElement(
					"button",
					{
						key: item.id,
						type: "button",
						"data-legend-id": item.id,
						"data-legend-visible": String(item.visible),
						onClick: () => onToggle(item.id),
					},
					item.label,
				),
			),
		),
}));

function run(runId: string): BacktestRun {
	return {
		runId,
		strategyId: "seed_etf_industry_rotation",
		strategyVersion: "4",
		mode: "backtest",
		status: "completed",
		startedAt: "2026-08-28T09:00:00Z",
		completedAt: "2026-08-28T09:14:00Z",
		errorMessage: "",
		parentRunId: "",
		benchmarkReturn: null,
		progressPct: 100,
		currentStep: "completed",
		completedDays: 60,
		totalDays: 60,
	};
}

const reportDto = {
	run_id: "run-a",
	period: { start: "2026-01-05", end: "2026-03-31" },
	initial_cash: 1_000_000,
	final_nav: 1_120_000,
	rebalance_freq: "weekly",
	alpha_stats: {
		annualized_return: 18.2,
		annualized_volatility: 12.4,
		sharpe_ratio: 1.47,
		sortino_ratio: 2.1,
		max_drawdown: -12.5,
		max_drawdown_duration_days: 48,
		calmar_ratio: 1.46,
		total_turnover: 9.8,
		avg_turnover_per_rebalance: 0.4,
		total_fees: 5400,
		net_return_after_cost: 17.1,
		cost_drag: 1.1,
	},
	aggregated_trade_stats: null,
};

function createWrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
	};
}

describe("BacktestMultiRunCompare", () => {
	it("overlays normalized navs of 2+ runs in palette order with a metrics diff table", async () => {
		server.use(
			http.get("/api/v1/backtests/runs/run-a/nav", () =>
				HttpResponse.json({
					data: [
						{ trade_date: "2026-01-05", nav: 1_000_000 },
						{ trade_date: "2026-01-06", nav: 1_100_000 },
					],
				}),
			),
			http.get("/api/v1/backtests/runs/run-b/nav", () =>
				HttpResponse.json({
					data: [
						{ trade_date: "2026-01-05", nav: 500_000 },
						{ trade_date: "2026-01-06", nav: 440_000 },
					],
				}),
			),
			http.get("/api/v1/backtests/runs/run-a/report", () => HttpResponse.json({ data: reportDto })),
			http.get("/api/v1/backtests/runs/run-b/report", () =>
				HttpResponse.json({ detail: "report not found", error_code: "BACKTEST_REPORT_NOT_FOUND" }, { status: 404 }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		// cockpit 收到两条归一化序列（各 run 按 nav₀ 归一，跨初始资金可比）
		await waitFor(() => {
			const last = cockpitProps.at(-1);
			expect(last?.series.map((spec) => spec.id)).toEqual(["run-a", "run-b"]);
			expect(last?.series[0]?.bars.map((bar) => (bar as { close: number }).close)).toEqual([1, 1.1]);
			expect(last?.series[1]?.bars.map((bar) => (bar as { close: number }).close)).toEqual([1, 0.88]);
		});
		// 图例按选中序占用 run 色板
		const legend = screen.getByTestId("multi-run-legend");
		expect(legend.querySelector("[data-legend-id='run-a']")).toHaveAttribute("data-legend-visible", "true");
		// 指标差异表：已发布 run 的真实指标 + 未发布 run 的诚实标注
		const table = screen.getByTestId("multi-run-metrics");
		expect(table.querySelector("[data-run-id='run-a']")).toHaveTextContent("18.20%");
		expect(table.querySelector("[data-run-id='run-a']")).toHaveTextContent("-12.50%");
		const rowB = table.querySelector("[data-run-id='run-b']");
		expect(rowB).toHaveAttribute("data-report-published", "false");
		expect(rowB).toHaveTextContent("未发布");
	});

	it("drops a series from the cockpit when its legend chip is toggled off", async () => {
		server.use(
			http.get("/api/v1/backtests/runs/run-a/nav", () =>
				HttpResponse.json({
					data: [
						{ trade_date: "2026-01-05", nav: 1_000_000 },
						{ trade_date: "2026-01-06", nav: 1_050_000 },
					],
				}),
			),
			http.get("/api/v1/backtests/runs/run-b/nav", () =>
				HttpResponse.json({
					data: [
						{ trade_date: "2026-01-05", nav: 1_000_000 },
						{ trade_date: "2026-01-06", nav: 980_000 },
					],
				}),
			),
			http.get("/api/v1/backtests/runs/:runId/report", () =>
				HttpResponse.json({ detail: "report not found", error_code: "BACKTEST_REPORT_NOT_FOUND" }, { status: 404 }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });
		await waitFor(() => {
			expect(screen.getByTestId("multi-run-legend")).toBeInTheDocument();
		});
		fireEvent.click(within(screen.getByTestId("multi-run-legend")).getByText("run-b"));
		await waitFor(() => {
			expect(screen.getByTestId("multi-run-legend").querySelector("[data-legend-id='run-b']")).toHaveAttribute(
				"data-legend-visible",
				"false",
			);
		});
		await waitFor(() => {
			expect(cockpitProps.at(-1)?.series.map((spec) => spec.id)).toEqual(["run-a"]);
		});
		// 差异表不受图例显隐影响，仍呈现全部选中 run
		expect(screen.getByTestId("multi-run-metrics").querySelectorAll("[data-run-id]")).toHaveLength(2);
	});
});
