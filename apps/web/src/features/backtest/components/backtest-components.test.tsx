import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { backtestHandlers } from "@/mocks/handlers/backtest";
import { server } from "@/mocks/server";

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

beforeEach(() => server.use(...backtestHandlers));

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
	it("渲染 NAV 曲线区域", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("净值与基准")).resolves.toBeInTheDocument();
	});

	it("显示策略与基准的独立末值", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("1.1820")).resolves.toBeInTheDocument();
		await expect(screen.findByText("1.0740")).resolves.toBeInTheDocument();
	});

	it("不展示没有公共资源支撑的持仓", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await screen.findByText("净值与基准");
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
