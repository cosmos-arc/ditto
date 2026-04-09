import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { strategyHandlers } from "@/mocks/handlers/strategy";

import { StrategyDetailMeta } from "./strategy-detail-meta";
import { StrategyVersionsView } from "./strategy-versions-view";

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

beforeEach(() => server.use(...strategyHandlers));

describe("StrategyDetailMeta", () => {
	it("渲染策略名称", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("多因子动量策略 v3"),
		).resolves.toBeInTheDocument();
	});

	it("显示策略版本和股票池", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findAllByText(/v3/)).resolves.toHaveLength(2);
		await expect(screen.findByText(/沪深300/)).resolves.toBeInTheDocument();
	});

	it("显示策略状态", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("completed")).resolves.toBeInTheDocument();
	});

	it("显示因子标签", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("波动率因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("北向资金因子")).resolves.toBeInTheDocument();
	});
});

describe("StrategyVersionsView", () => {
	it("渲染版本列表", async () => {
		render(<StrategyVersionsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("v1")).resolves.toBeInTheDocument();
		await expect(screen.findByText("v2")).resolves.toBeInTheDocument();
		await expect(screen.findByText("v3")).resolves.toBeInTheDocument();
	});

	it("显示版本变更说明", async () => {
		render(<StrategyVersionsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("初始版本：单因子动量策略"),
		).resolves.toBeInTheDocument();
	});
});
