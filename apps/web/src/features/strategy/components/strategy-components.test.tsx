import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { strategyHandlers } from "@/mocks/handlers/strategy";

import { StrategyHeader } from "./strategy-header";
import { FactorBrowser } from "./factor-browser";
import { StrategyEditor } from "./strategy-editor";
import { StrategyInspector } from "./strategy-inspector";

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

describe("StrategyHeader", () => {
	it("渲染策略名称", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("多因子动量策略 v3")).resolves.toBeInTheDocument();
	});

	it("显示策略版本", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("v3 · 沪深300")).resolves.toBeInTheDocument();
	});

	it("显示因子列表", async () => {
		render(<StrategyHeader id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("波动率因子")).resolves.toBeInTheDocument();
	});
});

describe("FactorBrowser", () => {
	it("渲染因子库标题", async () => {
		render(<FactorBrowser />, { wrapper: createWrapper() });
		await expect(screen.findByText("因子库")).resolves.toBeInTheDocument();
	});

	it("显示因子列表", async () => {
		render(<FactorBrowser />, { wrapper: createWrapper() });
		await expect(screen.findByText("价值因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("情绪因子")).resolves.toBeInTheDocument();
	});
});

describe("StrategyEditor", () => {
	it("渲染策略代码", async () => {
		render(<StrategyEditor id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/def strategy/)).resolves.toBeInTheDocument();
	});

	it("显示当前版本代码", async () => {
		render(<StrategyEditor id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/momentum/)).resolves.toBeInTheDocument();
	});
});

describe("StrategyInspector", () => {
	it("渲染策略参数", async () => {
		render(<StrategyInspector id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("策略参数")).resolves.toBeInTheDocument();
	});

	it("显示股票池", async () => {
		render(<StrategyInspector id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("沪深300")).resolves.toBeInTheDocument();
	});

	it("显示因子列表", async () => {
		render(<StrategyInspector id="strat-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
		await expect(screen.findByText("波动率因子")).resolves.toBeInTheDocument();
	});
});
