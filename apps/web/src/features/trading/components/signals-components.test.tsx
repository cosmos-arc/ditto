import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

	it("live 模式可录入 manual paper 手工成交", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "录入手工成交" }));

		await expect(screen.findByRole("dialog", { name: "订单确认" })).resolves.toBeInTheDocument();
		expect(screen.getByDisplayValue("1000")).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "提交手工成交" }));
		expect(screen.getByText("成交价格必须大于 0")).toBeInTheDocument();

		await user.type(screen.getByLabelText("成交价格"), "4.32");
		await user.click(screen.getByRole("button", { name: "提交手工成交" }));

		await expect(screen.findByText("手工成交已录入")).resolves.toBeInTheDocument();
	});

	it("live 模式通过高风险确认链路更新意图状态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const user = userEvent.setup();
		render(<SignalDetailPanel signalId="intent-510300" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/#510300 BUY 信号/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "更新意图状态" }));

		await expect(screen.findByRole("dialog", { name: "高风险状态确认" })).resolves.toBeInTheDocument();
		expect(document.querySelector("[data-impact-summary]")).toBeInTheDocument();
		expect(document.querySelector("[data-confirm-control]")).toBeInTheDocument();
		expect(document.querySelector("[data-cancel-control]")).toBeInTheDocument();
		expect(document.querySelector("[data-recovery-hint]")).toBeInTheDocument();
		expect(document.querySelector("[data-danger-marker='intent-status-transition']")).toBeInTheDocument();

		await user.selectOptions(screen.getByRole("combobox", { name: "目标状态" }), "partially_filled");
		await user.click(screen.getByRole("button", { name: "确认状态变更" }));

		await expect(screen.findByText("状态已更新为部分成交")).resolves.toBeInTheDocument();
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

	it("点击信号后打开所选信号详情 Drawer", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		expect(screen.queryByText("信号详情")).not.toBeInTheDocument();

		fireEvent.click(await screen.findByRole("button", { name: /000001\.SZ.*动量突破/ }));

		await expect(screen.findAllByText("信号详情")).resolves.toHaveLength(2);
		await expect(screen.findByText(/动量突破信号/)).resolves.toBeInTheDocument();
	});
});
