import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { backtestHandlers } from "@/mocks/handlers/backtest";

import { BacktestKpiStrip } from "./backtest-kpi-strip";
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
