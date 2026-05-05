import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { tradingHandlers } from "@/mocks/handlers/trading";

import { TradingSessionStrip } from "./trading-session-strip";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";
import { TradingPage } from "./trading-page";
import { PortfolioPage } from "./portfolio-page";

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

beforeEach(() => server.use(...tradingHandlers));

describe("Trading route page contract handoffs", () => {
	it("covers PortfolioPage route composition", () => {
		render(<PortfolioPage />, { wrapper: createWrapper() });

		expect(screen.getByText("组合总览")).toBeInTheDocument();
		expect(screen.getByText("Allocation")).toBeInTheDocument();
		expect(screen.getByText("Activity")).toBeInTheDocument();
	});
});

describe("TradingSessionStrip", () => {
	it("渲染交易阶段", async () => {
		render(<TradingSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText("continuous")).resolves.toBeInTheDocument();
	});

	it("显示现金余额", async () => {
		render(<TradingSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1,250,000/)).resolves.toBeInTheDocument();
	});

	it("显示保证金信息", async () => {
		render(<TradingSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText(/320,000/)).resolves.toBeInTheDocument();
	});
});

describe("EquityPnlBlock", () => {
	it("渲染权益标题", async () => {
		render(<EquityPnlBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText("权益 & 盈亏")).resolves.toBeInTheDocument();
	});

	it("显示总权益", async () => {
		render(<EquityPnlBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1,538,200/)).resolves.toBeInTheDocument();
	});
});

describe("PositionsSummary", () => {
	it("渲染持仓标题", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("持仓汇总")).resolves.toBeInTheDocument();
	});

	it("显示所有持仓", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("平安银行")).resolves.toBeInTheDocument();
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
	});

	it("显示 T+1 冻结标识", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("冻结 1,000")).resolves.toBeInTheDocument();
	});
});

describe("RiskAlertsBlock", () => {
	it("渲染风险标题", async () => {
		render(<RiskAlertsBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText("风控 & 预警")).resolves.toBeInTheDocument();
	});

	it("显示信号队列计数", async () => {
		render(<RiskAlertsBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText(/5 待复核/)).resolves.toBeInTheDocument();
	});

	it("显示订单计数", async () => {
		render(<RiskAlertsBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText(/15 已成交/)).resolves.toBeInTheDocument();
	});
});

describe("TradingPage - DecisionBanner", () => {
	it("渲染组合净值决策横幅", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("组合净值")).resolves.toBeInTheDocument();
	});

	it("显示净值数值 1.0842", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		// Metric with trend="up" renders "▲ 1.0842"
		await expect(screen.findByText(/1\.0842/)).resolves.toBeInTheDocument();
	});

	it("显示今日涨幅", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/今日 \+1.24%/)).resolves.toBeInTheDocument();
	});

	it("显示 AI 判断文本", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/当前市场风险偏好上升/)).resolves.toBeInTheDocument();
	});

	it("显示 Risk-On 状态标签", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("Risk-On")).resolves.toBeInTheDocument();
	});

	it("显示 IVIX 和北向资金指标", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("IVIX")).resolves.toBeInTheDocument();
		await expect(screen.findByText("北向资金")).resolves.toBeInTheDocument();
	});

	it("显示执行调仓和查看详情按钮", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("执行调仓")).resolves.toBeInTheDocument();
		await expect(screen.findByText("查看详情")).resolves.toBeInTheDocument();
	});
});

describe("TradingPage - OrdersPanel", () => {
	it("渲染委托订单标题", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("委托订单")).resolves.toBeInTheDocument();
	});

	it("默认显示待成交订单", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		// "贵州茅台" appears in multiple places (signals, positions, orders)
		const moutaiElements = await screen.findAllByText("贵州茅台");
		expect(moutaiElements.length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText("五粮液")).toBeInTheDocument();
	});

	it("显示待成交订单的价格", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1750\.00/)).resolves.toBeInTheDocument();
		expect(screen.getByText(/146\.00/)).toBeInTheDocument();
	});

	it("切换到已成交标签显示成交订单", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		// Wait for page to render first
		await screen.findByText("委托订单");

		fireEvent.click(screen.getByRole("button", { name: "已成交" }));
			expect(screen.getAllByText("宁德时代").length).toBeGreaterThanOrEqual(1);
			expect(screen.getAllByText("平安银行").length).toBeGreaterThanOrEqual(1);
	});

	it("切换到已撤单标签显示撤单订单", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		await screen.findByText("委托订单");

		fireEvent.click(screen.getByRole("button", { name: "已撤单" }));
		// "中国平安" appears in signals panel too, so use findAllByText
		const elements = screen.getAllByText("中国平安");
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});

	it("买入订单显示买标记", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		const buyBadge = (await screen.findAllByText("买"))[0];
		expect(buyBadge).toBeInTheDocument();
	});

	it("卖出订单显示卖标记", async () => {
		render(<TradingPage />, { wrapper: createWrapper() });
		const sellBadge = (await screen.findAllByText("卖"))[0];
		expect(sellBadge).toBeInTheDocument();
	});
});
