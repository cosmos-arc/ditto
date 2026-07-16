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
	it("covers BacktestListPage route composition", () => {
		render(<BacktestListPage />, { wrapper: createWrapper() });

		expect(screen.getByText("回测列表")).toBeInTheDocument();
		expect(screen.getByText("Backtests")).toBeInTheDocument();
		expect(screen.getByText("Result Preview")).toBeInTheDocument();
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
	it("渲染交易记录标题", async () => {
		render(<BacktestTrades jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("交易记录")).resolves.toBeInTheDocument();
	});

	it("显示交易列表", async () => {
		render(<BacktestTrades jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		expect(screen.getAllByText("五粮液")).toHaveLength(2);
	});
});

describe("BacktestOverview", () => {
	it("渲染 NAV 曲线区域", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("净值曲线")).resolves.toBeInTheDocument();
	});

	it("渲染持仓列表", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("当前持仓")).resolves.toBeInTheDocument();
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
	});

	it("显示持仓权重", async () => {
		render(<BacktestOverview jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/25%/)).resolves.toBeInTheDocument();
	});
});

describe("BacktestReturnsView", () => {
	it("渲染月度收益区域", async () => {
		render(<BacktestReturnsView jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("月度收益")).resolves.toBeInTheDocument();
	});

	it("显示月度收益率数据", async () => {
		render(<BacktestReturnsView jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/2.8%/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/3.5%/)).resolves.toBeInTheDocument();
	});

	it("显示基准收益", async () => {
		render(<BacktestReturnsView jobId="bt-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("基准")).resolves.toBeInTheDocument();
	});
});
