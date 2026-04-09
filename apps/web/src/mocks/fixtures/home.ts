import type {
	HomePulseResponse,
	DecisionBannerResponse,
	PendingAction,
	HomeAlert,
	RecentSignal,
	AgentFinding,
	DataHealthProvider,
	MarketIndex,
} from "@/types";

export const mockHomePulse: HomePulseResponse = {
	date: "2026-04-08",
	session: "continuous",
	pendingActions: 5,
	criticalAlerts: 1,
	runningJobs: 3,
	pnlToday: 12580.5,
	pnlPercent: 0.82,
};

export const mockDecisionBanner: DecisionBannerResponse = {
	totalEquity: 1580000,
	dailyPnl: 12580.5,
	dailyPnlPercent: 0.82,
	riskUtilization: 45,
	marketRegime: "risk_on",
	regimeType: "震荡偏强 — 多数板块资金净流入",
	suggestion: "当前市场环境下建议维持多头配置，关注消费与科技板块轮动机会。风控指标正常，可适度加仓至 70% 敞口。",
};

export const mockPendingActions: readonly PendingAction[] = [
	{
		id: "action-001",
		priority: "critical",
		title: "平安银行信号待复核",
		meta: "BUY 信号 · 置信度 85% · 剩余有效期 2h",
		time: "2026-04-08T09:15:00Z",
		badge: { type: "signal", label: "信号" },
		domain: "trading",
	},
	{
		id: "action-002",
		priority: "high",
		title: "回测任务完成",
		meta: "动量策略 v3 · Sharpe 1.82 · 已通过阈值",
		time: "2026-04-08T08:45:00Z",
		badge: { type: "backtest", label: "回测" },
		domain: "research",
	},
	{
		id: "action-003",
		priority: "medium",
		title: "FRED 数据源告警",
		meta: "延迟 230ms · 超阈值 3 倍",
		time: "2026-04-08T08:15:00Z",
		badge: { type: "alert", label: "告警" },
		domain: "platform",
	},
	{
		id: "action-004",
		priority: "medium",
		title: "因子 IC 下降",
		meta: "动量因子 IC 跌至 0.03 · 需审核",
		time: "2026-04-08T07:30:00Z",
		badge: { type: "factor", label: "因子" },
		domain: "research",
	},
	{
		id: "action-005",
		priority: "low",
		title: "API 配额预警",
		meta: "tushare 今日已用 45% · 剩余 5500 次",
		time: "2026-04-08T06:00:00Z",
		badge: { type: "resource", label: "资源" },
		domain: "platform",
	},
];

export const mockHomeAlerts: readonly HomeAlert[] = [
	{
		id: "home-alert-001",
		severity: "critical",
		title: "FRED 数据源连接超时",
		desc: "FRED API 响应时间超过 200ms 阈值，可能影响宏观指标更新",
		time: "2026-04-08T08:15:00Z",
	},
	{
		id: "home-alert-002",
		severity: "warning",
		title: "MiniQMT 连接延迟升高",
		desc: "行情推送延迟从 50ms 升至 150ms",
		time: "2026-04-08T09:05:00Z",
	},
	{
		id: "home-alert-003",
		severity: "info",
		title: "每日数据管道完成",
		desc: "所有定时任务已完成，52 条记录更新",
		time: "2026-04-08T06:00:00Z",
	},
];

export const mockRecentSignals: readonly RecentSignal[] = [
	{
		ticker: "000001.SZ",
		action: "BUY",
		strategy: "动量突破 v3",
		confidence: 85,
		time: "2026-04-08T09:15:00Z",
	},
	{
		ticker: "600519.SH",
		action: "HOLD",
		strategy: "价值因子轮动",
		confidence: 72,
		time: "2026-04-08T09:00:00Z",
	},
	{
		ticker: "300750.SZ",
		action: "SELL",
		strategy: "技术面 RSI",
		confidence: 68,
		time: "2026-04-08T08:45:00Z",
	},
];

export const mockAgentFindings: readonly AgentFinding[] = [
	{
		text: "检测到消费板块资金持续净流入 3 天，建议关注白酒龙头",
		source: "sector-flow",
		icon: "insight",
	},
	{
		text: "创业板换手率异常升高，可能与季报窗口期有关",
		source: "anomaly",
		icon: "warning",
	},
	{
		text: "北向资金今日净买入 28 亿，连续 5 日净流入",
		source: "northbound",
		icon: "info",
	},
];

export const mockDataHealth: readonly DataHealthProvider[] = [
	{
		label: "tushare",
		status: "healthy",
		statusText: "正常 · 延迟 45ms",
		lastUpdate: "2026-04-08T09:30:00Z",
	},
	{
		label: "MiniQMT",
		status: "healthy",
		statusText: "正常 · 实时连接",
		lastUpdate: "2026-04-08T09:30:05Z",
	},
	{
		label: "FRED",
		status: "warning",
		statusText: "延迟偏高 · 230ms",
		lastUpdate: "2026-04-08T08:00:00Z",
	},
	{
		label: "LLM",
		status: "healthy",
		statusText: "正常 · Claude 3.5",
		lastUpdate: "2026-04-08T09:20:00Z",
	},
];

export const mockMarketIndices: readonly MarketIndex[] = [
	{
		name: "上证指数",
		code: "000001.SH",
		price: 3258.36,
		change: 28.45,
		changePercent: 0.88,
		dir: "up",
	},
	{
		name: "深证成指",
		code: "399001.SZ",
		price: 10542.18,
		change: -35.62,
		changePercent: -0.34,
		dir: "down",
	},
	{
		name: "创业板指",
		code: "399006.SZ",
		price: 2089.75,
		change: 15.30,
		changePercent: 0.74,
		dir: "up",
	},
	{
		name: "沪深300",
		code: "000300.SH",
		price: 3842.10,
		change: 22.80,
		changePercent: 0.60,
		dir: "up",
	},
	{
		name: "恒生指数",
		code: "HSI",
		price: 22580.45,
		change: 320.50,
		changePercent: 1.44,
		dir: "up",
	},
	{
		name: "标普500",
		code: "SPX",
		price: 5425.80,
		change: -18.25,
		changePercent: -0.34,
		dir: "down",
	},
];
