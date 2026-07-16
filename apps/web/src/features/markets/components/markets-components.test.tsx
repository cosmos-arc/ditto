import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { marketsHandlers } from "@/mocks/handlers/markets";
import { server } from "@/mocks/server";
import { CapitalRotationTable } from "./capital-rotation-table";
import { MacroDriversBar } from "./macro-drivers-bar";
import { MarketCardGrid } from "./market-card-grid";
import { WatchlistPage } from "./watchlist-page";

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

beforeEach(() => server.use(...marketsHandlers));

describe("Markets route page contract handoffs", () => {
	it("covers WatchlistPage route composition", () => {
		render(<WatchlistPage />, { wrapper: createWrapper() });

		expect(screen.getByText("自选监控")).toBeInTheDocument();
		expect(screen.getByText("Watchlist")).toBeInTheDocument();
		expect(screen.getByText("Context")).toBeInTheDocument();
	});
});

describe("MarketCardGrid", () => {
	it("渲染 6 张市场卡片", async () => {
		render(<MarketCardGrid />, { wrapper: createWrapper() });

		await expect(screen.findByText("上证A股")).resolves.toBeInTheDocument();
		await expect(screen.findByText("恒生指数")).resolves.toBeInTheDocument();
		await expect(screen.findByText("纳斯达克")).resolves.toBeInTheDocument();
		await expect(screen.findByText("标普500")).resolves.toBeInTheDocument();
		await expect(screen.findByText("黄金")).resolves.toBeInTheDocument();
		await expect(screen.findByText("原油WTI")).resolves.toBeInTheDocument();
	});
});

describe("MacroDriversBar", () => {
	it("渲染宏观驱动标题", async () => {
		render(<MacroDriversBar />, { wrapper: createWrapper() });

		await expect(screen.findByText("宏观驱动")).resolves.toBeInTheDocument();
	});

	it("显示宏观指标", async () => {
		render(<MacroDriversBar />, { wrapper: createWrapper() });

		await expect(screen.findByText("DXY 美元指数")).resolves.toBeInTheDocument();
		await expect(screen.findByText("VIX 恐慌")).resolves.toBeInTheDocument();
	});
});

describe("CapitalRotationTable", () => {
	it("渲染资金轮动标题", async () => {
		render(<CapitalRotationTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("资金轮动")).resolves.toBeInTheDocument();
	});

	it("显示板块列表", async () => {
		render(<CapitalRotationTable />, { wrapper: createWrapper() });

		await expect(screen.findByText("科技")).resolves.toBeInTheDocument();
		await expect(screen.findByText("消费")).resolves.toBeInTheDocument();
	});
});
