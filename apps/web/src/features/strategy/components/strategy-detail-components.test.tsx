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
		await expect(screen.findByText("ETF 行业轮动")).resolves.toBeInTheDocument();
	});

	it("显示策略版本和股票池", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/v3 · csi_etf_broad/)).resolves.toBeInTheDocument();
	});

	it("显示策略生命周期", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("published")).resolves.toBeInTheDocument();
	});

	it("显示策略标签", async () => {
		render(<StrategyDetailMeta id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("etf")).resolves.toBeInTheDocument();
		await expect(screen.findByText("rotation")).resolves.toBeInTheDocument();
	});
});

describe("StrategyVersionsView", () => {
	it("渲染版本列表", async () => {
		render(<StrategyVersionsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("v1")).resolves.toBeInTheDocument();
		await expect(screen.findByText("v2")).resolves.toBeInTheDocument();
		await expect(screen.findByText("v3")).resolves.toBeInTheDocument();
	});

	it("显示版本审查结论", async () => {
		render(<StrategyVersionsView id="strat-001" />, { wrapper: createWrapper() });
		const approved = await screen.findAllByText("approved");
		expect(approved.length).toBeGreaterThanOrEqual(1);
	});
});

describe("StrategyOverview", () => {
	it("渲染策略流程", async () => {
		render(<StrategyOverview id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("策略流程")).resolves.toBeInTheDocument();
		await expect(screen.findByText("评分")).resolves.toBeInTheDocument();
		await expect(screen.findByText("选取")).resolves.toBeInTheDocument();
	});

	it("渲染风控约束", async () => {
		render(<StrategyOverview id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("风控约束")).resolves.toBeInTheDocument();
		// max_weight_per_instrument 同时出现在派生节点（流程）与风控约束区
		const constraints = await screen.findAllByText("max_weight_per_instrument");
		expect(constraints.length).toBeGreaterThanOrEqual(1);
	});

	it("显示策略参数", async () => {
		render(<StrategyOverview id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("策略参数")).resolves.toBeInTheDocument();
		await expect(screen.findByText("252")).resolves.toBeInTheDocument();
	});
});

describe("StrategyFactorsView", () => {
	it("渲染因子配置区域", async () => {
		render(<StrategyFactorsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("因子配置")).resolves.toBeInTheDocument();
	});

	it("显示 factor expression、权重和分析入口", async () => {
		render(<StrategyFactorsView id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("momentum_1m")).resolves.toBeInTheDocument();
		expect(screen.getByText("0.5")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "分析 momentum_1m" })).toHaveAttribute(
			"href",
			"/research/factors/momentum_1m",
		);
	});
});
