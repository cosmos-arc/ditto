import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { liveDailyDecisionV3 as mockDailyDecisionV3, portfolioHandlers } from "@/mocks/handlers/portfolio";
import { server } from "@/mocks/server";
import type { components } from "@/types/generated/api";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PortfolioOverviewPage } from "./portfolio-overview-page";
import { PortfolioPage } from "./portfolio-page";
// @contract-handoff PortfolioMockWorkspace
// @contract-handoff PortfolioPositionDetailDrawer
// @contract-handoff PortfolioTradeDetailDialog
import { PortfolioSessionStrip } from "./portfolio-session-strip";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";

type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
type DailyDecisionV3Response = components["schemas"]["DailyDecisionV3Response"];
type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];

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

beforeEach(() => {
	server.use(...portfolioHandlers);
	window.history.replaceState({}, "", "/portfolio");
});

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
} satisfies DailyDecisionReportResponse;

const liveDailyDecisionV2 = {
	identity: {
		strategy_id: "seed_etf_industry_rotation",
		strategy_version: "1",
		account_id: "paper-a",
		sleeve_id: "manual-paper-a-seed_etf_industry_rotation",
		signal_date: "2026-07-02",
		decision_date: "2026-07-02",
		intended_trade_date: "2026-07-03",
	},
	readiness: {
		status: "review",
		reason_codes: ["RISK_WARNING"],
		details: ["risk review"],
	},
	data: {
		required_datasets: ["etf_daily"],
		snapshot_ids: { etf_daily: "sha256:etf-daily" },
		dataset_states: [
			{
				dataset: "etf_daily",
				status: "ready",
				snapshot_id: "sha256:etf-daily",
				reason: "",
			},
		],
		freshness: "ready",
		dq_state: "passed",
	},
	run_package: {
		outcome: "completed",
		batch_key: "eod-2026-07-02-seed_etf_industry_rotation-1",
		artifact_id: "signal-package-1",
		checksum: "sha256:package-1",
		checksum_valid: true,
		no_rebalance: false,
		factor_evidence: {},
		risk_evidence: ["RISK_WARNING"],
	},
	account_positions: {
		baseline_id: "baseline-1",
		account_id: "paper-a",
		sleeve_id: "manual-paper-a-seed_etf_industry_rotation",
		cash_available: 60_000,
		cash_settled: 60_000,
		cash_frozen: 0,
		total_value: 100_000,
		nav: 1,
		exposure: 40_000,
		as_of: "2026-07-02",
		positions: liveDailyDecision.positions,
	},
	actions: [
		{
			intent_id: "intent-510300",
			instrument_id: 510300,
			direction: "buy",
			target_weight: 0.3,
			current_weight: 0.12,
			delta_weight: 0.18,
			raw_quantity: 1_050,
			rounded_quantity: 1_000,
			suggested_quantity: 1000,
			reference_price: 4.31,
			lot_size: 100,
			cash_impact: -4_310,
			reason: "rounded_down_to_board_lot",
			sizing_readiness: "ready",
			risk_flags: ["RISK_WARNING"],
			intent_status: "pending",
			filled_quantity: 400,
			remaining_quantity: 600,
		},
	],
	execution_review: {
		deviation: liveDailyDecision.deviation,
		pnl: liveDailyDecision.pnl,
		effective_fills: [
			{
				fill_id: "fill-510300-001",
				intent_id: "intent-510300",
				strategy_id: "seed_etf_industry_rotation",
				trade_date: "2026-07-03",
				instrument_id: 510300,
				direction: "buy",
				quantity: 400,
				fill_price: 4.32,
				fee: 1.2,
				slippage: 0.01,
				notes: "manual paper fill",
				settlement_date: "2026-07-06",
			},
		],
		exceptions: [],
		unresolved_conflicts: [],
	},
} satisfies DailyDecisionV2Response;

const liveDailyDecisionV3 = {
	...mockDailyDecisionV3,
	v2: liveDailyDecisionV2,
	readiness: "review",
	blocking_reasons: ["RISK_WARNING"],
} satisfies DailyDecisionV3Response;

describe("Trading route page contract handoffs", () => {
	it("covers PortfolioPage route composition", () => {
		render(<PortfolioPage />, { wrapper: createWrapper() });

		expect(screen.getByText("组合总览")).toBeInTheDocument();
		expect(screen.getByText("总资产")).toBeInTheDocument();
		expect(screen.getAllByText("2,847,320.50")).toHaveLength(2);
		expect(screen.getByRole("tab", { name: "持仓" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByText("PnL 曲线")).toBeInTheDocument();
		expect(screen.getByText("组合风险")).toBeInTheDocument();
	});

	it("mock Portfolio 在持仓、交易与归因之间切换", () => {
		render(<PortfolioPage />, { wrapper: createWrapper() });

		fireEvent.click(screen.getByRole("tab", { name: "交易" }));
		expect(screen.getByRole("tab", { name: "交易" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByText("10:18:35")).toBeInTheDocument();

		fireEvent.click(screen.getByRole("tab", { name: "归因" }));
		expect(screen.getByText("收益归因")).toBeInTheDocument();
		expect(screen.getByText("选股贡献")).toBeInTheDocument();
	});

	it("mock Portfolio 可从持仓与交易打开对应详情", async () => {
		render(<PortfolioPage />, { wrapper: createWrapper() });

		fireEvent.click(screen.getByRole("button", { name: "查看 贵州茅台 持仓详情" }));
		await expect(screen.findByText("持仓详情")).resolves.toBeInTheDocument();
		expect(within(screen.getByRole("dialog", { name: "持仓详情" })).getByText("600519.SH")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Close" }));

		fireEvent.click(screen.getByRole("tab", { name: "交易" }));
		fireEvent.click(screen.getByRole("button", { name: "查看 贵州茅台 成交详情" }));
		await expect(screen.findByText("成交详情")).resolves.toBeInTheDocument();
		expect(screen.getByText("来源：Alpha v3")).toBeInTheDocument();
	});

	it("mock Portfolio 不暴露旧全部平仓危险动作", async () => {
		render(<PortfolioPage />, { wrapper: createWrapper() });

		expect(screen.queryByRole("button", { name: "全部平仓" })).not.toBeInTheDocument();
	});

	it("live 模式展示组合构建、真实 positions、归因空态与 Pipeline Strip", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/manual/daily-decision/v3", () => HttpResponse.json({ data: liveDailyDecisionV3 })),
			http.get("/api/v1/manual/daily-decision/v2", () => HttpResponse.json({ data: liveDailyDecisionV2 })),
			http.get("/api/v1/manual/daily-decision", () => HttpResponse.json({ data: liveDailyDecision })),
		);

		render(<PortfolioPage />, { wrapper: createWrapper() });

		expect((await screen.findAllByText("#510300")).length).toBeGreaterThanOrEqual(2);
		expect(screen.getByText("组合构建证据")).toBeInTheDocument();
		expect(screen.getByText("sha256:mock-policy-r4")).toBeInTheDocument();
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
			http.get("/api/v1/manual/daily-decision/v3", () => HttpResponse.json({ data: liveDailyDecisionV3 })),
			http.get("/api/v1/manual/daily-decision/v2", () => HttpResponse.json({ data: liveDailyDecisionV2 })),
			http.get("/api/v1/manual/daily-decision", () => HttpResponse.json({ data: liveDailyDecision })),
			http.get("/api/v1/manual/comparison", () =>
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

		await expect(screen.findByText("回测 vs Manual 归因")).resolves.toBeInTheDocument();
		await expect(screen.findByText("跟踪误差")).resolves.toBeInTheDocument();
		expect(screen.getByText("12.5 bps")).toBeInTheDocument();
		expect(screen.queryByText("无归因数据")).not.toBeInTheDocument();
	});
});

describe("PortfolioSessionStrip", () => {
	it("live 模式显示显式 manual/paper 决策范围", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<PortfolioSessionStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("manual / paper")).resolves.toBeInTheDocument();
		expect(screen.getByText("决策范围由 URL 显式选择")).toBeInTheDocument();
	});

	it("将交易阶段映射为可读标签", async () => {
		render(<PortfolioSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText("连续竞价")).resolves.toBeInTheDocument();
	});

	it("显示现金余额", async () => {
		render(<PortfolioSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText(/8,432,180/)).resolves.toBeInTheDocument();
	});

	it("显示保证金信息", async () => {
		render(<PortfolioSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText(/3,218,400/)).resolves.toBeInTheDocument();
	});

	it("在 mock 原型模式展示 Manual/Paper 范围，并对缺失队列 fail closed", async () => {
		render(<PortfolioSessionStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("连续竞价")).resolves.toBeInTheDocument();
		expect(screen.getByText("担保比例")).toBeInTheDocument();
		expect(screen.getByText("286%")).toBeInTheDocument();
		expect(screen.getByText("账户模式")).toBeInTheDocument();
		expect(screen.getByText("Manual / Paper")).toBeInTheDocument();
		expect(screen.getByText("数据来源")).toBeInTheDocument();
		expect(screen.getByText("原型快照")).toBeInTheDocument();
		expect(screen.queryByText("券商连接")).not.toBeInTheDocument();
		expect(screen.getByText("执行队列")).toBeInTheDocument();
		expect(screen.getByText("暂无可靠数据")).toBeInTheDocument();
	});
});

describe("EquityPnlBlock", () => {
	it("live 模式显示 equity 合同不可用空态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<EquityPnlBlock />, { wrapper: createWrapper() });

		await expect(screen.findByText("权益曲线不可用")).resolves.toBeInTheDocument();
		expect(screen.getByText("当前公开合同未提供权益时序")).toBeInTheDocument();
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

	it("live 模式只展示 Daily Decision 风险证据，不请求 prototype 风险摘要", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const legacyRiskHandler = vi.fn(() => HttpResponse.json({}));
		server.use(
			http.get("/api/trading/risk/summary", legacyRiskHandler),
			http.get("/api/v1/manual/daily-decision/v2", () => HttpResponse.json({ data: liveDailyDecisionV2 })),
		);

		render(<RiskAlertsBlock />, { wrapper: createWrapper() });

		await expect(screen.findAllByText("RISK_WARNING")).resolves.not.toHaveLength(0);
		expect(screen.queryByText("VaR")).not.toBeInTheDocument();
		expect(legacyRiskHandler).not.toHaveBeenCalled();
	});
});

describe("PortfolioOverviewPage - DecisionBanner", () => {
	it("原型与实时模式保持相同的分析页骨架", () => {
		const prototype = render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		const prototypeSlots = Array.from(prototype.container.querySelectorAll(":scope [data-slot]"))
			.map((element) => element.getAttribute("data-slot"))
			.filter((slot): slot is string => ["strip", "banner", "main", "activity", "analysis"].includes(slot ?? ""));
		prototype.unmount();

		vi.stubEnv("VITE_USE_MOCK", "false");
		const live = render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		const liveSlots = Array.from(live.container.querySelectorAll(":scope [data-slot]"))
			.map((element) => element.getAttribute("data-slot"))
			.filter((slot): slot is string => ["strip", "banner", "main", "activity", "analysis"].includes(slot ?? ""));

		expect(prototypeSlots).toEqual(["strip", "banner", "main", "activity", "analysis"]);
		expect(liveSlots).toEqual(prototypeSlots);
	});

	it("live 桌面主工作区由 PortfolioOverviewPage 局部提供纵向滚动", () => {
		vi.stubEnv("VITE_USE_MOCK", "false");

		const { container } = render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		const mainContent = container.querySelector("[data-slot='main'] > div");
		expect(mainContent).toHaveClass("md:h-full");
		expect(mainContent).toHaveClass("md:overflow-y-auto");
	});

	it("live 模式提供显式可提交的 strategy/account/date 执行范围", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		window.history.replaceState(
			{},
			"",
			"/portfolio/model?strategy_id=strategy-x&account_id=paper-x&trade_date=2026-07-02",
		);

		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		const form = await screen.findByRole("form", { name: "执行范围" });
		expect(within(form).getByLabelText("策略 ID")).toHaveValue("strategy-x");
		expect(within(form).getByLabelText("账户 ID")).toHaveValue("paper-x");
		expect(within(form).getByLabelText("信号日期")).toHaveValue("2026-07-02");
		expect(within(form).getByRole("button", { name: "加载决策" })).toBeInTheDocument();
	});

	it("live 模式从 daily-decision 渲染 primary answer", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/manual/daily-decision/v3", () => HttpResponse.json({ data: liveDailyDecisionV3 })),
			http.get("/api/v1/manual/daily-decision/v2", () => HttpResponse.json({ data: liveDailyDecisionV2 })),
			http.get("/api/v1/manual/daily-decision", () => HttpResponse.json({ data: liveDailyDecision })),
		);

		const { container } = render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await expect(screen.findAllByText("需复核")).resolves.not.toHaveLength(0);
		const banner = screen.getByTestId("decision-banner");
		expect(within(banner).getByText("1 条")).toBeInTheDocument();
		expect(within(banner).getByText("1 项提示")).toBeInTheDocument();
		expect(container.querySelector("[data-primary-answer='true']")).toBeInTheDocument();
	});

	it("blocked 状态关闭决策横幅中的交易动作", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/manual/daily-decision/v3", () =>
				HttpResponse.json({
					data: {
						...liveDailyDecisionV3,
						readiness: "blocked",
						blocking_reasons: ["ACCOUNT_BASELINE_MISSING"],
					},
				}),
			),
		);

		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await expect(screen.findAllByText("阻塞")).resolves.not.toHaveLength(0);
		const banner = screen.getByTestId("decision-banner");
		expect(within(banner).queryByText("打开信号")).not.toBeInTheDocument();
		expect(within(banner).queryByText("复核证据")).not.toBeInTheDocument();
		expect(within(banner).queryByText(/^[▲▼] 阻塞$/)).not.toBeInTheDocument();
		expect(within(banner).getByText("关闭")).toBeInTheDocument();
		expect(within(banner).queryByText("1 条")).not.toBeInTheDocument();
	});

	it("live 契约失败时显示可重试错误且不回退原型净值", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/manual/daily-decision/v3", () =>
				HttpResponse.json({ detail: "temporary failure" }, { status: 503 }),
			),
		);

		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("加载失败")).resolves.toBeInTheDocument();
		expect(within(screen.getByTestId("decision-banner")).getByRole("button", { name: "重试" })).toBeInTheDocument();
		expect(screen.queryByText("1.0842")).not.toBeInTheDocument();
	});

	it("live 模式 Overview 信号队列使用 daily-decision 而非 mock 常量", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/manual/daily-decision/v3", () => HttpResponse.json({ data: liveDailyDecisionV3 })),
			http.get("/api/v1/manual/daily-decision/v2", () => HttpResponse.json({ data: liveDailyDecisionV2 })),
			http.get("/api/v1/manual/daily-decision", () => HttpResponse.json({ data: liveDailyDecision })),
		);

		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("1 条")).resolves.toBeInTheDocument();
		const signalsQueue = document.querySelector("[data-info-unit='signals-queue']");
		expect(signalsQueue).toBeInTheDocument();
		expect(within(signalsQueue as HTMLElement).getByText("#510300")).toBeInTheDocument();
		expect(within(signalsQueue as HTMLElement).queryByText("贵州茅台")).not.toBeInTheDocument();
		expect(within(signalsQueue as HTMLElement).queryByText("宁德时代")).not.toBeInTheDocument();
	});

	it("live 模式 Overview 订单区使用手工执行流水而非 mock 委托", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		server.use(
			http.get("/api/v1/manual/daily-decision/v3", () => HttpResponse.json({ data: liveDailyDecisionV3 })),
			http.get("/api/v1/manual/daily-decision/v2", () => HttpResponse.json({ data: liveDailyDecisionV2 })),
			http.get("/api/v1/manual/daily-decision", () => HttpResponse.json({ data: liveDailyDecision })),
		);

		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("1 条")).resolves.toBeInTheDocument();
		const ordersPanel = document.querySelector("[data-info-unit='orders-panel']");
		expect(ordersPanel).toBeInTheDocument();
		await within(ordersPanel as HTMLElement).findByText("manual / paper");
		expect(within(ordersPanel as HTMLElement).getByText("fill-159915-001")).toBeInTheDocument();
		expect(within(ordersPanel as HTMLElement).queryByText("贵州茅台")).not.toBeInTheDocument();
		expect(within(ordersPanel as HTMLElement).queryByText("五粮液")).not.toBeInTheDocument();
	});

	it("渲染今日盈亏决策横幅", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("今日盈亏")).resolves.toBeInTheDocument();
	});

	it("显示今日盈亏数值", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/86,472\.50/)).resolves.toBeInTheDocument();
	});

	it("显示今日涨幅", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/\+0\.34%/)).resolves.toBeInTheDocument();
	});

	it("显示人工复核判断文本", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/先复核贵州茅台卖出信号/)).resolves.toBeInTheDocument();
	});

	it("显示震荡市状态标签", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("震荡市")).resolves.toBeInTheDocument();
	});

	it("显示待处理信号和待成交订单指标", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("待处理信号")).resolves.toBeInTheDocument();
		await expect(screen.findByText("待成交订单")).resolves.toBeInTheDocument();
	});

	it("显示信号、持仓与风控复核入口", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("复核信号")).resolves.toBeInTheDocument();
		await expect(screen.findByText("查看持仓")).resolves.toBeInTheDocument();
		await expect(screen.findByText("查看风控")).resolves.toBeInTheDocument();
	});
});

describe("PortfolioOverviewPage - OrdersPanel", () => {
	it("渲染委托订单标题", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("委托订单")).resolves.toBeInTheDocument();
	});

	it("默认显示待成交订单", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		// "贵州茅台" appears in multiple places (signals, positions, orders)
		const moutaiElements = await screen.findAllByText("贵州茅台");
		expect(moutaiElements.length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText("五粮液")).toBeInTheDocument();
	});

	it("显示待成交订单的价格", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1750\.00/)).resolves.toBeInTheDocument();
		expect(screen.getByText(/146\.00/)).toBeInTheDocument();
	});

	it("切换到已成交标签显示成交订单", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		// Wait for page to render first
		await screen.findByText("委托订单");

		fireEvent.click(screen.getByRole("button", { name: "已成交" }));
		expect(screen.getAllByText("宁德时代").length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText("平安银行").length).toBeGreaterThanOrEqual(1);
	});

	it("切换到已撤单标签显示撤单订单", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		await screen.findByText("委托订单");

		fireEvent.click(screen.getByRole("button", { name: "已撤单" }));
		// "中国平安" appears in signals panel too, so use findAllByText
		const elements = screen.getAllByText("中国平安");
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});

	it("买入订单显示买标记", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		const buyBadge = (await screen.findAllByText("买"))[0];
		expect(buyBadge).toBeInTheDocument();
	});

	it("卖出订单显示卖标记", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });
		const sellBadge = (await screen.findAllByText("卖"))[0];
		expect(sellBadge).toBeInTheDocument();
	});
});
