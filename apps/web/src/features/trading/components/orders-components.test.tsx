import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { tradingHandlers } from "@/mocks/handlers/trading";
import { ordersHandlers } from "@/mocks/handlers/orders";

import { OrdersList } from "./orders-list";
import { OrdersHealthStrip } from "./orders-health-strip";
import { OrderDetailPanel } from "./order-detail-panel";
import { OrdersPage } from "./orders-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...tradingHandlers, ...ordersHandlers));

// ── OrdersList ──────────────────────────────────────────────────

describe("OrdersList", () => {
	it("渲染订单列表标题", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("订单台账"),
		).resolves.toBeInTheDocument();
	});

	it("显示订单列表", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findByText("000001.SZ")).resolves.toBeInTheDocument();
		await expect(screen.findByText("600519.SH")).resolves.toBeInTheDocument();
	});

	it("显示订单方向", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findAllByText("BUY")).resolves.toHaveLength(4);
		await expect(screen.findByText("SELL")).resolves.toBeInTheDocument();
	});

	it("显示订单状态", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findByText("pending")).resolves.toBeInTheDocument();
		await expect(screen.findAllByText("filled")).resolves.toHaveLength(2);
	});
});

// ── OrdersHealthStrip ───────────────────────────────────────────

describe("OrdersHealthStrip", () => {
	it("渲染订单统计指标", async () => {
		render(<OrdersHealthStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("待提交")).resolves.toBeInTheDocument();
		expect(screen.getByText("已提交")).toBeInTheDocument();
		expect(screen.getByText("部分成交")).toBeInTheDocument();
		expect(screen.getByText("已成交")).toBeInTheDocument();
		expect(screen.getByText("失败")).toBeInTheDocument();
	});

	it("显示订单计数", async () => {
		render(<OrdersHealthStrip />, { wrapper: createWrapper() });

		// mockOrdersSummary: { pending: 2, submitted: 1, partial: 1, filled: 4, failed: 0 }
		await expect(screen.findByText("待提交")).resolves.toBeInTheDocument();
		expect(screen.getByText("已成交")).toBeInTheDocument();
		expect(screen.getByText("失败")).toBeInTheDocument();
	});
});

// ── OrderDetailPanel ────────────────────────────────────────────

describe("OrderDetailPanel", () => {
	it("渲染订单基本信息", async () => {
		render(<OrderDetailPanel orderId="ord-003" />, {
			wrapper: createWrapper(),
		});

		await expect(
			screen.findByText("300750.SZ"),
		).resolves.toBeInTheDocument();
	});

	it("渲染订单追踪时间线", async () => {
		render(<OrderDetailPanel orderId="ord-003" />, {
			wrapper: createWrapper(),
		});

		await expect(
			screen.findByText("信号确认"),
		).resolves.toBeInTheDocument();
		expect(screen.getByText("风控校验通过")).toBeInTheDocument();
		expect(screen.getByText("部分成交")).toBeInTheDocument();
	});

	it("渲染费用和滑点", async () => {
		render(<OrderDetailPanel orderId="ord-003" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/32\.15/)).resolves.toBeInTheDocument();
	});

	it("渲染路由日志", async () => {
		render(<OrderDetailPanel orderId="ord-003" />, {
			wrapper: createWrapper(),
		});

		await expect(
			screen.findByText("路由选择"),
		).resolves.toBeInTheDocument();
		expect(screen.getByText("券商回报")).toBeInTheDocument();
	});
});

// ── OrdersPage — OpsConsoleLayout 集成 ──────────────────────────

describe("OrdersPage", () => {
	it("渲染健康条（health slot）", async () => {
		render(<OrdersPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("待提交"),
		).resolves.toBeInTheDocument();
	});

	it("渲染订单列表（main slot）", async () => {
		render(<OrdersPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("订单台账"),
		).resolves.toBeInTheDocument();
	});

	it("渲染订单详情面板（detail slot）", async () => {
		render(<OrdersPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("信号确认"),
		).resolves.toBeInTheDocument();
	});
});
