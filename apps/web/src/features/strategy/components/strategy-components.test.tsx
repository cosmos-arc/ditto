import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { strategyHandlers } from "@/mocks/handlers/strategy";
import { server } from "@/mocks/server";
import { StrategyHeader } from "./strategy-header";
import { StrategyListPage } from "./strategy-list-page";

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

describe("Strategy route page contract handoffs", () => {
	it("covers StrategyListPage route composition", () => {
		render(<StrategyListPage />, { wrapper: createWrapper() });

		expect(screen.getByText("策略列表")).toBeInTheDocument();
		expect(screen.getByText("Strategies")).toBeInTheDocument();
		expect(screen.getByText("Promotion")).toBeInTheDocument();
	});
});

describe("StrategyHeader", () => {
	it("渲染策略名称", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("ETF 行业轮动")).resolves.toBeInTheDocument();
	});

	it("显示策略版本与股票池", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("v3 · csi_etf_broad")).resolves.toBeInTheDocument();
	});

	it("显示策略标签", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("etf")).resolves.toBeInTheDocument();
		await expect(screen.findByText("rotation")).resolves.toBeInTheDocument();
	});

	it("显示版本 hash、snapshot、eligible start 与 R2 hard-gate 上下文", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("h-v3")).resolves.toBeInTheDocument();
		expect(screen.getByText("未绑定，Experiment preflight 时固定")).toBeInTheDocument();
		expect(screen.getByText("待 preflight 计算")).toBeInTheDocument();
		expect(screen.getByText("创建实验时按 live evidence 硬门禁")).toBeInTheDocument();
	});
});

// StrategyEditor / NodeInspector 已迁移到独立 co-located 测试（API 改为受控 props）。
// FactorBrowser 已删除（dead code，node-library 取代）。
