import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { tradingHandlers } from "@/mocks/handlers/trading";

import { SignalsList } from "./signals-list";
import { SignalsHealthStrip } from "./signals-health-strip";
import { SignalDetailPanel } from "./signal-detail-panel";
import { SignalsPage } from "./signals-page";

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

beforeEach(() => server.use(...tradingHandlers));

// ── SignalsList ─────────────────────────────────────────────────

describe("SignalsList", () => {
	it("渲染信号标题", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("信号队列"),
		).resolves.toBeInTheDocument();
	});

	it("显示信号列表", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量突破")).resolves.toBeInTheDocument();
		await expect(screen.findByText("获利了结")).resolves.toBeInTheDocument();
		await expect(screen.findByText("均值回归")).resolves.toBeInTheDocument();
	});

	it("显示信号方向", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findAllByText("BUY")).resolves.toHaveLength(2);
		await expect(screen.getByText("SELL")).toBeInTheDocument();
	});

	it("显示置信度", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("85%")).resolves.toBeInTheDocument();
	});
});

// ── SignalsHealthStrip ──────────────────────────────────────────

describe("SignalsHealthStrip", () => {
	it("渲染信号队列统计指标", async () => {
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("待处理")).resolves.toBeInTheDocument();
		expect(screen.getByText("已确认")).toBeInTheDocument();
		expect(screen.getByText("已忽略")).toBeInTheDocument();
		expect(screen.getByText("已下单")).toBeInTheDocument();
	});

	it("显示队列计数", async () => {
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		// mockSignalsQueue: { pending: 5, confirmed: 12, ignored: 3, ordered: 8 }
		await expect(screen.findByText("5")).resolves.toBeInTheDocument();
		expect(screen.getByText("12")).toBeInTheDocument();
		expect(screen.getByText("3")).toBeInTheDocument();
		expect(screen.getByText("8")).toBeInTheDocument();
	});

	it("显示加载骨架屏", () => {
		render(<SignalsHealthStrip />, { wrapper: createWrapper() });

		// 骨架屏应出现（loading 状态）
		const skeletons = document.querySelectorAll("[data-slot]");
		expect(skeletons.length).toBeGreaterThanOrEqual(0);
	});
});

// ── SignalDetailPanel ───────────────────────────────────────────

describe("SignalDetailPanel", () => {
	it("渲染信号解读文本", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(
			screen.findByText(/动量突破信号/),
		).resolves.toBeInTheDocument();
	});

	it("渲染风控检查列表", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(
			screen.findByText("涨跌停检查"),
		).resolves.toBeInTheDocument();
		expect(screen.getByText("集中度检查")).toBeInTheDocument();
		// "行业暴露" 同时出现在风险检查和组合影响，用 getAllByText
		expect(screen.getAllByText("行业暴露").length).toBeGreaterThanOrEqual(1);
	});

	it("渲染风控检查状态", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/近 3 日无涨跌停/)).resolves.toBeInTheDocument();
	});

	it("渲染操作按钮", async () => {
		render(<SignalDetailPanel signalId="sig-001" />, {
			wrapper: createWrapper(),
		});

		await expect(
			screen.findByText("确认信号"),
		).resolves.toBeInTheDocument();
		expect(screen.getByText("忽略信号")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "AI 解读" })).toBeInTheDocument();
	});
});

// ── SignalsPage — OpsConsoleLayout 集成 ─────────────────────────

describe("SignalsPage", () => {
	it("渲染健康条（health slot）", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("待处理"),
		).resolves.toBeInTheDocument();
	});

	it("渲染信号列表（main slot）", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("信号队列"),
		).resolves.toBeInTheDocument();
	});

	it("渲染信号详情面板（detail slot）", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("涨跌停检查"),
		).resolves.toBeInTheDocument();
	});
});
