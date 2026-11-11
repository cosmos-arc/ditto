import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import type { BacktestRun } from "../types";
import { BacktestMultiRunCompare } from "./backtest-multi-run-compare";

// jsdom 无法承载 fancy-canvas：barrel 级 stub 只替换 ChartCockpit（捕获喂养序列）；
// ChartLegend 重导出真实叶子模块（无 canvas 依赖，行为不重复实现）。
type CockpitStubProps = {
	series: { id: string; bars: unknown[]; color?: string }[];
	chartId: string;
	identity?: { dataSourceName?: string };
};
const cockpitProps: CockpitStubProps[] = [];
vi.mock("@/components/chart", async () => {
	const { ChartLegend } = await import("@/components/chart/cockpit/chart-legend");
	return {
		ChartCockpit: (props: CockpitStubProps) => {
			cockpitProps.push(props);
			return createElement("div", {
				"data-testid": "chart-cockpit-stub",
				"data-chart-series-ids": props.series.map((spec) => spec.id).join(","),
			});
		},
		ChartLegend,
	};
});

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

/** 同口径 report：两个 run 均已发布、期间一致（其余轴对称未记录）。 */
const reportDto = (runId: string) => ({
	run_id: runId,
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
});

function createWrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
	};
}

function navHandler(runId: string, rows: { trade_date: string; nav: number }[]) {
	return http.get(`/api/v1/backtests/runs/${runId}/nav`, () => HttpResponse.json({ data: rows }));
}

describe("BacktestMultiRunCompare", () => {
	it("overlays normalized navs of caliber-compatible runs with caliber verification", async () => {
		server.use(
			navHandler("run-a", [
				{ trade_date: "2026-01-05", nav: 1_000_000 },
				{ trade_date: "2026-01-06", nav: 1_100_000 },
			]),
			navHandler("run-b", [
				{ trade_date: "2026-01-05", nav: 500_000 },
				{ trade_date: "2026-01-06", nav: 440_000 },
			]),
			http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
				HttpResponse.json({ data: reportDto(String(params["runId"])) }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		// 同口径（期间一致、其余轴对称未记录）的两个 run 并入同一叠加
		await waitFor(() => {
			const last = cockpitProps.at(-1);
			expect(last?.series.map((spec) => spec.id)).toEqual(["run-a", "run-b"]);
			expect(last?.series[0]?.bars.map((bar) => (bar as { close: number }).close)).toEqual([1, 1.1]);
			expect(last?.series[1]?.bars.map((bar) => (bar as { close: number }).close)).toEqual([1, 0.88]);
		});
		// 图例按选中序占用 run 色板
		const legend = screen.getByTestId("multi-run-legend");
		expect(legend.querySelector("[data-legend-id='run-a']")).toHaveAttribute("data-legend-visible", "true");
		// PNG/CSV 导出身份内嵌有序 run ids + 色槽位 + 口径结论：导出物可独立归因
		expect(cockpitProps.at(-1)).toMatchObject({
			identity: { dataSourceName: expect.stringContaining("run-a#1 · run-b#2") },
		});
		expect(cockpitProps.at(-1)?.identity?.dataSourceName).toContain("严格历史可得性未认证");
		expect(cockpitProps.at(-1)?.identity?.dataSourceName).toContain("口径核对：一致");
		// 口径核对表：五轴 + 结论，两个 run 均并入
		const caliber = await screen.findByTestId("multi-run-caliber");
		expect(caliber.querySelector("tr[data-run-id='run-a']")).toHaveTextContent("并入叠加");
		expect(caliber.querySelector("tr[data-run-id='run-b']")).toHaveTextContent("并入叠加");
		expect(caliber.querySelectorAll("th").length).toBe(7);
		// 对称未记录轴如实披露为未核对
		expect(screen.getByTestId("multi-run-caliber-disclosure")).toHaveTextContent(/未核对轴/);

		// 指标差异表：真实指标按 run 原值（表不归一化、不排名）
		const table = screen.getByTestId("multi-run-metrics");
		expect(table.querySelector("[data-run-id='run-a']")).toHaveTextContent("18.20%");
		expect(table.querySelector("[data-run-id='run-a']")).toHaveTextContent("-12.50%");
	});

	it("drops a series from the cockpit when its legend chip is toggled off", async () => {
		server.use(
			navHandler("run-a", [
				{ trade_date: "2026-01-05", nav: 1_000_000 },
				{ trade_date: "2026-01-06", nav: 1_050_000 },
			]),
			navHandler("run-b", [
				{ trade_date: "2026-01-05", nav: 1_000_000 },
				{ trade_date: "2026-01-06", nav: 980_000 },
			]),
			http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
				HttpResponse.json({ data: reportDto(String(params["runId"])) }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });
		await waitFor(() => {
			expect(cockpitProps.at(-1)?.series.map((spec) => spec.id)).toEqual(["run-a", "run-b"]);
		});
		const legend = screen.getByTestId("multi-run-legend");
		expect(legend.querySelector("[data-legend-id='run-a']")).toHaveAttribute("data-legend-visible", "true");
		fireEvent.click(within(legend).getByText("run-a"));
		await waitFor(() => {
			expect(legend.querySelector("[data-legend-id='run-a']")).toHaveAttribute("data-legend-visible", "false");
		});
		await waitFor(() => {
			expect(cockpitProps.at(-1)?.series.map((spec) => spec.id)).toEqual(["run-b"]);
		});
		// 色板索引绑定勾选序：隐藏首个 run 后，第二个 run 仍保持 --chart-run-2，不重排
		expect(cockpitProps.at(-1)?.series[0]?.color).toBe("var(--chart-run-2)");
		// 导出身份跟随可见序列并保留原色槽位：隐藏 run-a 后 run-b 仍是 #2（不重编号）
		expect(cockpitProps.at(-1)?.identity?.dataSourceName).toContain("run-b#2");
		expect(cockpitProps.at(-1)?.identity?.dataSourceName).not.toContain("run-a#");
		// 差异表不受图例显隐影响，仍呈现全部选中 run
		expect(screen.getByTestId("multi-run-metrics").querySelectorAll("[data-run-id]")).toHaveLength(2);
	});

	it("separates a run whose recorded caliber differs instead of merging it", async () => {
		server.use(
			navHandler("run-a", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			navHandler("run-b", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			http.get("/api/v1/backtests/runs/run-a/report", () => HttpResponse.json({ data: reportDto("run-a") })),
			http.get("/api/v1/backtests/runs/run-b/report", () =>
				HttpResponse.json({
					data: { ...reportDto("run-b"), period: { start: "2025-01-05", end: "2025-03-31" } },
				}),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		// 只剩一个可并入 run 时不构成对比：结构化解释替代单序列叠加
		const single = await screen.findByTestId("multi-run-caliber-single");
		expect(single).toHaveTextContent("可并入同一叠加的 run 只有一个");
		expect(screen.queryByTestId("chart-cockpit-stub")).not.toBeInTheDocument();
		const caliber = screen.getByTestId("multi-run-caliber");
		const rowB = caliber.querySelector("tr[data-run-id='run-b']");
		expect(rowB?.getAttribute("data-caliber-conclusion")).toContain("未并入");
		expect(rowB?.textContent).toContain("时间样本不同");
		expect(rowB?.textContent).toContain("2026-01-05 → 2026-03-31");
		expect(rowB?.textContent).toContain("2025-01-05 → 2025-03-31");
		// 指标表仍按原值呈现两个 run（分开解释不等于抹掉事实）
		expect(screen.getByTestId("multi-run-metrics").querySelectorAll("[data-run-id]")).toHaveLength(2);
	});

	it("renders a structured empty state when every selected run has no persisted NAV", async () => {
		server.use(
			http.get("/api/v1/backtests/runs/:runId/nav", () =>
				HttpResponse.json({ detail: "nav not found", error_code: "BACKTEST_NAV_NOT_FOUND" }, { status: 404 }),
			),
			http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
				HttpResponse.json({ data: reportDto(String(params["runId"])) }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		const empty = await screen.findByText("所选 run 均未落盘净值证据（无 nav.parquet）。");
		expect(empty.closest("[data-state='nav-empty']")).toBeInTheDocument();
		// 空态替代空白画布：cockpit 不挂载，图例位保留
		expect(screen.queryByTestId("chart-cockpit-stub")).not.toBeInTheDocument();
		expect(screen.getByTestId("multi-run-legend").querySelectorAll("button")).toHaveLength(2);
		// 差异表仍呈现（指标按 report 真实发布）
		expect(screen.getByTestId("multi-run-metrics").querySelectorAll("[data-run-id]")).toHaveLength(2);
	});

	it("explains instead of overlaying when no run has a published report to verify caliber", async () => {
		server.use(
			navHandler("run-a", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			navHandler("run-b", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			http.get("/api/v1/backtests/runs/:runId/report", () =>
				HttpResponse.json({ detail: "report not found", error_code: "BACKTEST_REPORT_NOT_FOUND" }, { status: 404 }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		const empty = await screen.findByTestId("multi-run-caliber-empty");
		expect(empty).toHaveTextContent(/没有已发布 report 的 run/);
		expect(screen.queryByTestId("chart-cockpit-stub")).not.toBeInTheDocument();
		expect(screen.queryByTestId("multi-run-legend")).not.toBeInTheDocument();
		// 口径表逐行说明原因；指标表保持诚实标注（404 落定后是「未发布」）
		const caliber = screen.getByTestId("multi-run-caliber");
		await waitFor(() => expect(caliber.querySelectorAll("tr[data-caliber-conclusion]")).toHaveLength(2));
		await waitFor(() =>
			expect(screen.getByTestId("multi-run-metrics").querySelector("[data-run-id='run-a']")).toHaveTextContent(
				"未发布",
			),
		);
	});

	it("distinguishes visible-only emptiness from an all-selected-empty selection", async () => {
		server.use(
			navHandler("run-a", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			http.get("/api/v1/backtests/runs/run-b/nav", () =>
				HttpResponse.json({ detail: "nav not found", error_code: "BACKTEST_NAV_NOT_FOUND" }, { status: 404 }),
			),
			http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
				HttpResponse.json({ data: reportDto(String(params["runId"])) }),
			),
		);
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });
		await waitFor(() => {
			expect(screen.getByTestId("chart-cockpit-stub")).toBeInTheDocument();
		});
		fireEvent.click(within(screen.getByTestId("multi-run-legend")).getByText("run-a"));
		await screen.findByText("当前可见 run 均未落盘净值证据；隐藏的 run 中仍有数据，点击图例恢复。");
		expect(screen.queryByTestId("chart-cockpit-stub")).not.toBeInTheDocument();
	});

	it("surfaces non-404 fetch failures with a retry instead of collapsing them to absent evidence", async () => {
		let navBFailing = true;
		server.use(
			navHandler("run-a", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			http.get("/api/v1/backtests/runs/run-b/nav", () =>
				navBFailing
					? HttpResponse.json({ detail: "boom", error_code: "NAV_500" }, { status: 500 })
					: HttpResponse.json({ data: [{ trade_date: "2026-01-05", nav: 900_000 }] }),
			),
			http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
				HttpResponse.json({ data: reportDto(String(params["runId"])) }),
			),
		);
		cockpitProps.length = 0;
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		const alert = await screen.findByRole("alert");
		expect(alert).toHaveAttribute("data-state", "fetch-error");
		expect(alert).toHaveTextContent(/净值.*读取失败/u);
		expect(screen.queryByTestId("chart-cockpit-stub")).not.toBeInTheDocument();

		navBFailing = false;
		fireEvent.click(screen.getByRole("button", { name: "重试读取所选 run 证据" }));
		await waitFor(() => {
			expect(screen.queryByRole("alert")).not.toBeInTheDocument();
		});
		await waitFor(() => {
			expect(cockpitProps.at(-1)?.series.map((spec) => spec.id)).toEqual(["run-a", "run-b"]);
		});
	});

	it("keeps surfacing a report failure even when the same run's nav is a 404 business state", async () => {
		server.use(
			navHandler("run-a", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
			http.get("/api/v1/backtests/runs/run-b/nav", () =>
				HttpResponse.json({ detail: "nav not found", error_code: "BACKTEST_NAV_NOT_FOUND" }, { status: 404 }),
			),
			http.get("/api/v1/backtests/runs/run-a/report", () =>
				HttpResponse.json({ detail: "report not found", error_code: "BACKTEST_REPORT_NOT_FOUND" }, { status: 404 }),
			),
			http.get("/api/v1/backtests/runs/run-b/report", () =>
				HttpResponse.json({ detail: "boom", error_code: "REPORT_500" }, { status: 500 }),
			),
		);
		render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });

		// 两个 run 的 report 都不可用（404 业务态 + 5xx 失败）：不产生叠加图，
		// 但 5xx 仍按获取失败显式暴露并可重试
		const empty = await screen.findByTestId("multi-run-caliber-empty");
		expect(empty).toBeInTheDocument();
		const alert = await screen.findByRole("alert");
		expect(alert).toHaveAttribute("data-state", "report-fetch-error");
		expect(alert).toHaveTextContent(/report 证据读取失败/u);
		expect(alert.querySelector("button")).toHaveTextContent("重试读取 report 证据");
	});

	it("excludes vanished runs from the hidden-series guard", async () => {
		server.use(
			http.get("/api/v1/backtests/runs/:runId/nav", () =>
				HttpResponse.json({ data: [{ trade_date: "2026-01-05", nav: 1_000_000 }] }),
			),
			http.get("/api/v1/backtests/runs/:runId/report", ({ params }) =>
				HttpResponse.json({ data: reportDto(String(params["runId"])) }),
			),
		);
		const view = render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b"), run("run-c")]} />, {
			wrapper: createWrapper(),
		});
		await waitFor(() => {
			expect(screen.getByTestId("multi-run-legend")).toBeInTheDocument();
		});
		// 隐藏 run-a 后目录刷新令其消失：隐藏 id 不占守卫位，仍可隐藏 run-b（run-c 保留）
		fireEvent.click(within(screen.getByTestId("multi-run-legend")).getByText("run-a"));
		view.rerender(<BacktestMultiRunCompare runs={[run("run-b"), run("run-c")]} />);
		fireEvent.click(within(screen.getByTestId("multi-run-legend")).getByText("run-b"));
		await waitFor(() => {
			expect(screen.getByTestId("multi-run-legend").querySelector("[data-legend-id='run-b']")).toHaveAttribute(
				"data-legend-visible",
				"false",
			);
		});
	});

	it("exports the comparison as CSV with the exact displayed strings and caliber verdicts", async () => {
		const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:compare");
		const revokeObjectURL = vi.fn();
		vi.stubGlobal("URL", Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL }));
		const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
		try {
			server.use(
				navHandler("run-a", [{ trade_date: "2026-01-05", nav: 1_000_000 }]),
				navHandler("run-b", [{ trade_date: "2026-01-05", nav: 900_000 }]),
				http.get("/api/v1/backtests/runs/run-a/report", () => HttpResponse.json({ data: reportDto("run-a") })),
				http.get("/api/v1/backtests/runs/run-b/report", () =>
					HttpResponse.json({
						data: { ...reportDto("run-b"), period: { start: "2025-01-05", end: "2025-03-31" } },
					}),
				),
			);
			render(<BacktestMultiRunCompare runs={[run("run-a"), run("run-b")]} />, { wrapper: createWrapper() });
			// 等 report 落定（结论不再是「读取中」）再导出：导出值与最终展示一致
			const caliber = await screen.findByTestId("multi-run-caliber");
			await waitFor(() =>
				expect(caliber.querySelector("tr[data-run-id='run-a']")?.getAttribute("data-caliber-conclusion")).toBe(
					"并入叠加",
				),
			);
			fireEvent.click(screen.getByRole("button", { name: "导出对比 CSV" }));
			expect(createObjectURL).toHaveBeenCalledOnce();
			const blob = createObjectURL.mock.calls[0]?.[0];
			if (!blob) throw new Error("comparison export did not produce a Blob");
			const csv = await blob.text();
			expect(csv).toContain("# comparison=run-a,run-b");
			// 指标列与差异表展示串同值（含千分位引号转义）
			expect(csv).toContain('"1,000,000"');
			expect(csv).toContain("18.20%");
			// 口径结论与表格结论同文
			expect(csv).toContain("并入叠加");
			expect(csv).toContain("未并入叠加：时间样本不同");
			const anchor = anchorClick.mock.instances.at(-1) as HTMLAnchorElement | undefined;
			expect(anchor?.download).toBe("backtest-compare.csv");
		} finally {
			anchorClick.mockRestore();
			vi.unstubAllGlobals();
		}
	});
});
