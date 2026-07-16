import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { strategyHandlers } from "@/mocks/handlers/strategy";
import { server } from "@/mocks/server";

import { StrategyDetailMeta } from "./strategy-detail-meta";
import { StrategyFactorsView } from "./strategy-factors-view";
import { StrategyOverview } from "./strategy-overview";
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
		await expect(screen.findByText("多因子动量策略 v3")).resolves.toBeInTheDocument();
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
		await expect(screen.findByText("初始版本：单因子动量策略")).resolves.toBeInTheDocument();
	});
});

describe("StrategyOverview", () => {
	it("渲染 Pipeline 流程", async () => {
		render(<StrategyOverview id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("策略流程")).resolves.toBeInTheDocument();
		await expect(screen.findByText("股票池过滤")).resolves.toBeInTheDocument();
		await expect(screen.findByText("因子合成")).resolves.toBeInTheDocument();
	});

	it("渲染风控规则", async () => {
		render(<StrategyOverview id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("风控规则")).resolves.toBeInTheDocument();
		await expect(screen.findByText("个股最大持仓权重")).resolves.toBeInTheDocument();
	});

	it("显示因子权重配比", async () => {
		render(<StrategyOverview id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("因子权重")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/40%/)).resolves.toBeInTheDocument();
	});
});

describe("StrategyFactorsView", () => {
	it("渲染因子配置区域", async () => {
		render(<StrategyFactorsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("因子配置")).resolves.toBeInTheDocument();
	});

	it("显示因子权重分配", async () => {
		render(<StrategyFactorsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/40%/)).resolves.toBeInTheDocument();
		const factors30 = await screen.findAllByText(/30%/);
		expect(factors30).toHaveLength(2);
	});

	it("显示因子列表", async () => {
		render(<StrategyFactorsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("波动率因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("北向资金因子")).resolves.toBeInTheDocument();
	});
});
