import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { http, HttpResponse } from "msw";
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

const liveDailyDecision = {
	strategy_id: "seed_etf_industry_rotation",
	trade_date: "2026-07-02",
	readiness: { status: "review", reasons: ["manual review required"] },
	signal_intents: [
		{
			intent_id: "intent-510300",
			strategy_id: "seed_etf_industry_rotation",
			signal_date: "2026-07-02",
			instrument_id: 510300,
			direction: "buy",
			target_weight: 0.3,
			current_weight: 0.12,
			delta_weight: 0.18,
			quantity: 1000,
			status: "pending",
		},
	],
	positions: [
		{
			snapshot_id: "pos-510300",
			strategy_id: "seed_etf_industry_rotation",
			snapshot_date: "2026-07-02",
			instrument_id: 510300,
			quantity: 1000,
			available_quantity: 800,
			average_cost: 4.12,
			market_value: 4300,
			unrealized_pnl: 180,
			realized_pnl: 20,
			total_fees: 3,
		},
	],
	deviation: {
		strategy_id: "seed_etf_industry_rotation",
		signal_date: "2026-07-02",
		total_signals: 1,
		filled: 0,
		unfilled: 1,
		items: [
			{
				instrument_id: 510300,
				signal_action: "buy",
				signal_weight: 0.3,
				actual_weight: 0.12,
				deviation_bps: 125,
				fill_status: "unfilled",
			},
		],
	},
	pnl: {
		total_realized_pnl: 20,
		total_unrealized_pnl: 180,
		total_fees: 3,
		net_pnl: 197,
	},
} as const;

describe("Trading route page contract handoffs", () => {
	it("covers PortfolioPage route composition", () => {
		render(<PortfolioPage />, { wrapper: createWrapper() });

		expect(screen.getByText("组合总览")).toBeInTheDocument();
		expect(screen.getByText("Allocation")).toBeInTheDocument();
		expect(screen.getByText("Activity")).toBeInTheDocument();
	});

	it("live 模式展示真实 positions/pnl、归因空态与 Pipeline Strip", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/trade/daily-decision", () =>
				HttpResponse.json({ data: liveDailyDecision }),
			),
		);

		render(<PortfolioPage />, { wrapper: createWrapper() });

		await expect(screen.findAllByText("#510300")).resolves.toHaveLength(2);
		expect(screen.getByText("净盈亏")).toBeInTheDocument();
		expect(screen.getByText(/¥197/)).toBeInTheDocument();
		expect(screen.getByText("归因")).toBeInTheDocument();
		expect(screen.getByText("无归因数据")).toBeInTheDocument();
		expect(screen.getByText("Signal-to-Order Pipeline")).toBeInTheDocument();
		expect(screen.getByText("待复核")).toBeInTheDocument();
		expect(screen.getByText("成交")).toBeInTheDocument();
		expect(screen.getByText("手工执行流水")).toBeInTheDocument();
		await expect(screen.findByText("fill-159915-001")).resolves.toBeInTheDocument();
	});

	it("live 模式 Portfolio 带 run_id 时渲染 comparison 归因数据", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/trade/daily-decision", () =>
				HttpResponse.json({ data: liveDailyDecision }),
			),
			http.get("/api/v1/trade/comparison", () =>
				HttpResponse.json({
					data: {
						backtest_return: 0.08,
						actual_return: 0.071,
						return_diff: -0.009,
						return_diff_bps: -90,
						backtest_sharpe: 1.3,
						actual_sharpe: 1.1,
						backtest_total_cost: 12,
						actual_total_cost: 18,
						cost_drag_bps: 6,
						nav_correlation: 0.98,
						max_nav_diff_bps: 42,
						avg_daily_tracking_error_bps: 12.5,
					},
				}),
			),
		);

		render(<PortfolioPage comparisonRunId="run-001" />, { wrapper: createWrapper() });

		await expect(screen.findByText("回测 vs 实盘归因")).resolves.toBeInTheDocument();
		await expect(screen.findByText("跟踪误差")).resolves.toBeInTheDocument();
		expect(screen.getByText("12.5 bps")).toBeInTheDocument();
		expect(screen.queryByText("无归因数据")).not.toBeInTheDocument();
	});
});

describe("TradingSessionStrip", () => {
	it("live 模式显示 session 未接 live 空态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<TradingSessionStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("V1a 未接 live")).resolves.toBeInTheDocument();
		expect(screen.getByText("Session 数据待后端补齐")).toBeInTheDocument();
	});

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
	it("live 模式显示 equity 未接 live 空态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<EquityPnlBlock />, { wrapper: createWrapper() });

		await expect(screen.findByText("V1a 未接 live")).resolves.toBeInTheDocument();
		expect(screen.getByText("Equity 曲线待后端补齐")).toBeInTheDocument();
	});

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
	it("live 模式从 daily-decision 渲染 primary answer", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/trade/daily-decision", () =>
				HttpResponse.json({ data: liveDailyDecision }),
			),
		);

		const { container } = render(<TradingPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("需复核")).resolves.toBeInTheDocument();
		expect(screen.getByText("信号 1 条")).toBeInTheDocument();
		expect(screen.getByText("偏差 125 bps")).toBeInTheDocument();
		expect(container.querySelector("[data-primary-answer='true']")).toBeInTheDocument();
	});

	it("live 模式 Overview 信号队列使用 daily-decision 而非 mock 常量", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/trade/daily-decision", () =>
				HttpResponse.json({ data: liveDailyDecision }),
			),
		);

		render(<TradingPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("信号 1 条")).resolves.toBeInTheDocument();
		const signalsQueue = document.querySelector("[data-info-unit='signals-queue']");
		expect(signalsQueue).toBeInTheDocument();
		expect(within(signalsQueue as HTMLElement).getByText("#510300")).toBeInTheDocument();
		expect(within(signalsQueue as HTMLElement).queryByText("贵州茅台")).not.toBeInTheDocument();
		expect(within(signalsQueue as HTMLElement).queryByText("宁德时代")).not.toBeInTheDocument();
	});

	it("live 模式 Overview 订单区使用手工执行流水而非 mock 委托", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/trade/daily-decision", () =>
				HttpResponse.json({ data: liveDailyDecision }),
			),
		);

		render(<TradingPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("信号 1 条")).resolves.toBeInTheDocument();
		const ordersPanel = document.querySelector("[data-info-unit='orders-panel']");
		expect(ordersPanel).toBeInTheDocument();
		await within(ordersPanel as HTMLElement).findByText("manual / paper");
		expect(within(ordersPanel as HTMLElement).getByText("fill-159915-001")).toBeInTheDocument();
		expect(within(ordersPanel as HTMLElement).queryByText("贵州茅台")).not.toBeInTheDocument();
		expect(within(ordersPanel as HTMLElement).queryByText("五粮液")).not.toBeInTheDocument();
	});

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
