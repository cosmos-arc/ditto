import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { backtestHandlers } from "@/mocks/handlers/backtest";
import { server } from "@/mocks/server";

// jsdom 无法承载 fancy-canvas：barrel 级同步 stub ChartCockpit，捕获 props 断言喂养数据。
const cockpitProps: Array<Record<string, unknown>> = [];
vi.mock("@/components/chart", () => ({
	ChartCockpit: (props: Record<string, unknown>) => {
		cockpitProps.push(props);
		return createElement("div", {
			"data-testid": "chart-cockpit-stub",
			"data-chart-panes": String(1 + ((props["subPanes"] as unknown[] | undefined)?.length ?? 0)),
		});
	},
}));

import { BacktestKpiStrip } from "./backtest-kpi-strip";
import { BacktestListPage } from "./backtest-list-page";
import { BacktestOverview } from "./backtest-overview";
import { BacktestReturnsView } from "./backtest-returns-view";
import { BacktestTrades } from "./backtest-trades";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...backtestHandlers);
	cockpitProps.length = 0;
});

describe("Backtest route page contract handoffs", () => {
	it("covers BacktestListPage route composition", async () => {
		render(<BacktestListPage />, { wrapper: createWrapper() });

		expect(await screen.findByRole("region", { name: "受控回测目录" })).toBeInTheDocument();
		expect(screen.getByText("Backtest Runs")).toBeInTheDocument();
		expect(screen.getByRole("complementary", { name: "回测运行详情" })).toBeInTheDocument();
	});
});

describe("BacktestKpiStrip", () => {
	it("渲染 KPI 指标", async () => {
		render(<BacktestKpiStrip jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("Sharpe")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/1.82/)).resolves.toBeInTheDocument();
	});

	it("显示年化收益", async () => {
		render(<BacktestKpiStrip jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("年化收益")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/18.2%/)).resolves.toBeInTheDocument();
	});
});

describe("BacktestTrades", () => {
	it("渲染受控成交列", async () => {
		render(<BacktestTrades jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("Instrument")).resolves.toBeInTheDocument();
		expect(screen.getByText("PnL")).toBeInTheDocument();
	});

	it("仅显示契约提供的 instrument identity", async () => {
		render(<BacktestTrades jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("Instrument #600519")).resolves.toBeInTheDocument();
		expect(screen.getByText("Instrument #300750")).toBeInTheDocument();
		expect(screen.queryByText("贵州茅台")).not.toBeInTheDocument();
	});
});

describe("BacktestOverview", () => {
	it("渲染净值 vs 基准叠加 + 超额与回撤副图", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("净值 vs 基准")).resolves.toBeInTheDocument();
		const chart = await screen.findByTestId("chart-cockpit-stub");
		// 主图（净值+基准）+ 超额副图 + 回撤副图 = 3 panes
		expect(chart).toHaveAttribute("data-chart-panes", "3");
		const last = cockpitProps.at(-1) as {
			series: Array<{ id: string; label: string; bars: unknown[] }>;
			subPanes: Array<{ id: string }>;
			bands: unknown[];
		};
		expect(last.series.map((spec) => spec.id)).toEqual(["nav", "benchmark"]);
		expect(last.series.map((spec) => spec.label)).toEqual(["策略净值", "基准"]);
		expect(last.subPanes.map((pane) => pane.id)).toEqual(["excess", "drawdown"]);
		expect(last.bands.length).toBeGreaterThan(0);
	});

	it("显示策略与基准的独立末值", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("1.1820")).resolves.toBeInTheDocument();
		await expect(screen.findByText("1.0740")).resolves.toBeInTheDocument();
	});

	it("水下曲线最深点与报告最大回撤同口径展示", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await screen.findByText("净值 vs 基准");
		// mock nav: 1 → 1.041 回撤至 1.041/1.056−1 ≈ −1.42%
		await expect(screen.findByText("最深回撤（水下曲线）")).resolves.toBeInTheDocument();
		expect(screen.getByText("−1.42%")).toBeInTheDocument();
	});

	it("基准缺失（404）时明确标注未配置并只渲染策略净值", async () => {
		render(<BacktestOverview jobId="bt-no-bench" />, { wrapper: createWrapper() });
		await expect(screen.findByText("净值 vs 基准")).resolves.toBeInTheDocument();
		expect(await screen.findByText("本运行未配置基准（benchmark 未发布）")).toHaveAttribute(
			"data-state",
			"benchmark-unavailable",
		);
		const last = cockpitProps.at(-1) as {
			series: Array<{ id: string }>;
			subPanes: Array<{ id: string }>;
		};
		expect(last.series.map((spec) => spec.id)).toEqual(["nav"]);
		expect(last.subPanes.map((pane) => pane.id)).toEqual(["drawdown"]);
	});

	it("基准已配置但行情无覆盖（200 空序列）时给出不可得状态", async () => {
		render(<BacktestOverview jobId="bt-empty-bench" />, { wrapper: createWrapper() });
		await expect(screen.findByText("净值 vs 基准")).resolves.toBeInTheDocument();
		expect(await screen.findByText("基准已配置，但本地行情无覆盖（基准数据不可得）")).toBeInTheDocument();
	});

	it("不展示没有公共资源支撑的持仓", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await screen.findByText("净值 vs 基准");
		expect(screen.queryByText("当前持仓")).not.toBeInTheDocument();
	});
});

describe("BacktestReturnsView", () => {
	it("渲染已发布的 performance report", async () => {
		render(<BacktestReturnsView jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("Performance report")).resolves.toBeInTheDocument();
	});

	it("显示报告资金与成交统计", async () => {
		render(<BacktestReturnsView jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1,000,000/)).resolves.toBeInTheDocument();
		expect(screen.getByText("24")).toBeInTheDocument();
	});

	it("不伪造月度收益", async () => {
		render(<BacktestReturnsView jobId="bt-001" />, { wrapper: createWrapper() });
		await screen.findByText("Performance report");
		expect(screen.queryByText("月度收益")).not.toBeInTheDocument();
	});
});
