import type {
	EquityPoint,
	GetSignalDetailResponse,
	GetSignalsResponse,
	OrdersSummaryResponse,
	Position,
	RiskSummaryResponse,
	SignalsQueueResponse,
	TradingSessionResponse,
} from "@/types";

export const mockTradingSession: TradingSessionResponse = {
	phase: "continuous",
	cashBalance: 1_250_000,
	margin: {
		totalMargin: 500_000,
		usedMargin: 320_000,
		availableMargin: 180_000,
		maintenanceRatio: 0.65,
	},
	riskBudget: 0.45,
	routeHealth: {
		name: "MiniQMT",
		status: "healthy",
		latency: 12,
	},
	marginData: {
		totalMargin: 500_000,
		usedMargin: 320_000,
		availableMargin: 180_000,
		maintenanceRatio: 0.65,
	},
};

export const mockEquity: readonly EquityPoint[] = [
	{ time: "2026-04-01T15:00:00Z", equity: 1_500_000, pnl: 0, pnlPercent: 0 },
	{ time: "2026-04-02T15:00:00Z", equity: 1_508_200, pnl: 8200, pnlPercent: 0.55 },
	{ time: "2026-04-03T15:00:00Z", equity: 1_495_600, pnl: -4400, pnlPercent: -0.29 },
	{ time: "2026-04-04T15:00:00Z", equity: 1_512_300, pnl: 12_300, pnlPercent: 0.82 },
	{ time: "2026-04-05T15:00:00Z", equity: 1_506_800, pnl: 6800, pnlPercent: 0.45 },
	{ time: "2026-04-06T15:00:00Z", equity: 1_520_100, pnl: 20_100, pnlPercent: 1.34 },
	{ time: "2026-04-07T15:00:00Z", equity: 1_518_500, pnl: 18_500, pnlPercent: 1.23 },
	{ time: "2026-04-08T15:00:00Z", equity: 1_535_400, pnl: 35_400, pnlPercent: 2.36 },
	{ time: "2026-04-09T15:00:00Z", equity: 1_542_800, pnl: 42_800, pnlPercent: 2.85 },
	{ time: "2026-04-10T15:00:00Z", equity: 1_538_200, pnl: 38_200, pnlPercent: 2.55 },
] as const;

export const mockPositions: readonly Position[] = [
	{
		code: "000001.SZ",
		name: "平安银行",
		qty: 10000,
		availableQty: 10000,
		avgCost: 11.25,
		currentPrice: 12.08,
		pnl: 8300,
		pnlPercent: 7.38,
		weight: 0.08,
		frozenQty: 0,
	},
	{
		code: "600519.SH",
		name: "贵州茅台",
		qty: 200,
		availableQty: 200,
		avgCost: 1680.0,
		currentPrice: 1755.5,
		pnl: 15_100,
		pnlPercent: 4.49,
		weight: 0.23,
		frozenQty: 0,
	},
	{
		code: "300750.SZ",
		name: "宁德时代",
		qty: 800,
		availableQty: 800,
		avgCost: 195.0,
		currentPrice: 210.8,
		pnl: 12_640,
		pnlPercent: 8.1,
		weight: 0.11,
		frozenQty: 0,
	},
	{
		code: "000858.SZ",
		name: "五粮液",
		qty: 1500,
		availableQty: 1500,
		avgCost: 138.5,
		currentPrice: 145.2,
		pnl: 10_050,
		pnlPercent: 4.84,
		weight: 0.14,
		frozenQty: 0,
	},
	{
		code: "601318.SH",
		name: "中国平安",
		qty: 3000,
		availableQty: 2000,
		avgCost: 42.8,
		currentPrice: 45.6,
		pnl: 8400,
		pnlPercent: 6.54,
		weight: 0.09,
		frozenQty: 1000,
	},
] as const;

export const mockRiskSummary: RiskSummaryResponse = {
	var: -2.3,
	maxDD: -5.8,
	beta: 0.85,
	grossExposure: 180,
	netExposure: 65,
	nearLimit: false,
	breachCount: 0,
};

export const mockSignalsQueue: SignalsQueueResponse = {
	pending: 5,
	confirmed: 12,
	ignored: 3,
	ordered: 8,
};

export const mockOrdersSummary: OrdersSummaryResponse = {
	pending: 2,
	submitted: 1,
	partial: 1,
	filled: 15,
	failed: 0,
};

export const mockSignals: GetSignalsResponse = {
	items: [
		{
			id: "sig-001",
			time: "2026-04-09T09:35:00Z",
			instrument: "000001.SZ",
			source: "动量突破",
			direction: "BUY",
			weight: 0.06,
			confidence: 0.85,
			status: "pending",
			limitUpDownCheck: { limitUp: false, limitDown: false, days: 3 },
		},
		{
			id: "sig-002",
			time: "2026-04-09T09:42:00Z",
			instrument: "600519.SH",
			source: "获利了结",
			direction: "SELL",
			weight: 0.23,
			confidence: 0.72,
			status: "pending",
			limitUpDownCheck: { limitUp: false, limitDown: false, days: 0 },
		},
		{
			id: "sig-003",
			time: "2026-04-09T10:05:00Z",
			instrument: "300750.SZ",
			source: "均值回归",
			direction: "BUY",
			weight: 0.04,
			confidence: 0.68,
			status: "pending",
			limitUpDownCheck: { limitUp: true, limitDown: false, days: 1 },
		},
		{
			id: "sig-004",
			time: "2026-04-09T10:18:00Z",
			instrument: "000858.SZ",
			source: "资金流入",
			direction: "BUY",
			weight: 0.05,
			confidence: 0.91,
			status: "confirmed",
			limitUpDownCheck: { limitUp: false, limitDown: false, days: 2 },
		},
		{
			id: "sig-005",
			time: "2026-04-08T14:30:00Z",
			instrument: "601318.SH",
			source: "价值低估",
			direction: "BUY",
			weight: 0.07,
			confidence: 0.78,
			status: "ordered",
			limitUpDownCheck: { limitUp: false, limitDown: false, days: 5 },
		},
	] as const,
	total: 5,
	page: 1,
	pageSize: 20,
} as const;

export const mockSignalDetail: GetSignalDetailResponse = {
	explanation:
		"000001.SZ 平安银行在 2026-04-09 出现动量突破信号。近 5 日累计涨幅达 8.2%，突破 20 日布林带上轨，成交量较 20 日均量放大 1.6 倍。技术面 MACD 金叉确认，RSI 由 55 升至 68 尚未进入超买区间。基本面方面，银行板块一季度业绩预告普遍向好，信贷投放增速回升。综合评分 85 分，建议买入。",
	riskChecks: [
		{ name: "涨跌停检查", status: "pass", message: "近 3 日无涨跌停记录" },
		{ name: "集中度检查", status: "pass", message: "买入后单一持仓占比 8.3%，低于 10% 阈值" },
		{ name: "行业暴露", status: "warn", message: "银行板块持仓占比将达 15.2%，接近 18% 警戒线" },
		{ name: "流动性检查", status: "pass", message: "近 20 日日均成交额 12.8 亿元，流动性充裕" },
		{ name: "波动率检查", status: "fail", message: "近 10 日年化波动率 35.2%，高于 30% 阈值" },
	],
	portfolioImpact: {
		concentrationChange: 0.02,
		sectorExposure: 0.04,
		riskChange: 0.01,
	},
	actions: [
		{ type: "confirm", label: "确认信号", enabled: true },
		{ type: "ignore", label: "忽略信号", enabled: true },
		{ type: "ai_interpret", label: "AI 解读", enabled: true },
		{ type: "batch_confirm", label: "批量确认", enabled: false },
	],
} as const;
