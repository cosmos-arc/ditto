import type {
	DataHealthProvider,
	DecisionBannerResponse,
	HomeAgentFinding,
	HomeAlert,
	HomePulseResponse,
	MarketIndex,
	MarketPulseMetric,
	PendingAction,
	RecentSignal,
} from "@/types";

export const mockHomePulse: HomePulseResponse = {
	date: "2026-03-28",
	session: "continuous",
	pendingActions: 2,
	criticalAlerts: 0,
	runningJobs: 3,
	pnlToday: 86472.5,
	pnlPercent: 0.34,
	riskLevel: "中等",
	regimeType: "温和风险偏好",
};

export const mockDecisionBanner: DecisionBannerResponse = {
	totalEquity: 25432180,
	dailyPnl: 86472.5,
	dailyPnlPercent: 0.34,
	riskUtilization: 0,
	leverage: 1.2,
	maxDrawdown: -3.8,
	ivix: 18.52,
	northboundFlow: 12.4,
	equitySparkline: [20.1, 19.8, 19.5, 19.2, 18.9, 18.7, 18.52],
	marketRegime: "mixed",
	regimeType: "温和风险偏好",
	suggestion: "波动回落，北向转暖，但局部拥挤。",
};

export const mockPendingActions: readonly PendingAction[] = [
	{
		id: "action-001",
		priority: "critical",
		title: "贵州茅台（600519）出现卖出信号",
		meta: "RSI 背离叠加放量，Alpha v3 置信度 87%，建议查看卖出上下文。",
		time: "3分钟前",
		badges: [
			{ type: "signal", label: "交易" },
			{ type: "priority", label: "P1" },
		],
		domain: "trading",
	},
	{
		id: "action-002",
		priority: "critical",
		title: "行业集中度超限 — 科技板块 > 35%",
		meta: "当前占比 37.2%，超过规则上限，需评估是否降集中度。",
		time: "12分钟前",
		badges: [
			{ type: "risk", label: "风控" },
			{ type: "priority", label: "P1" },
		],
		domain: "trading",
	},
	{
		id: "action-003",
		priority: "high",
		title: "价值因子 2026 Q1 回测完成",
		meta: "Sharpe 1.42，最大回撤 -8.3%，建议审阅后决定是否部署。",
		time: "1小时前",
		badges: [
			{ type: "research", label: "研究" },
			{ type: "priority", label: "P2" },
		],
		domain: "research",
	},
	{
		id: "action-004",
		priority: "medium",
		title: "Tushare API 频率接近上限",
		meta: "今日已用 4,820 / 5,000 次，3 小时后重置。",
		time: "2小时前",
		badges: [{ type: "platform", label: "平台" }],
		domain: "platform",
	},
	{
		id: "action-005",
		priority: "medium",
		title: "沪深300 1 分钟 K线缺失",
		meta: "14:32–14:33 数据缺失，正在自动补全，建议关注修复结果。",
		time: "42分钟前",
		badges: [{ type: "data", label: "数据" }],
		domain: "platform",
	},
];

export const mockHomeAlerts: readonly HomeAlert[] = [
	{
		id: "home-alert-001",
		severity: "critical",
		title: "组合 VaR 突破 95% 分位",
		desc: "组合 VaR 突破 95% 分位",
		time: "8分钟前",
	},
	{
		id: "home-alert-002",
		severity: "critical",
		title: "券商连接中断 — 中信证券",
		desc: "券商连接中断 — 中信证券",
		time: "15分钟前",
	},
	{
		id: "home-alert-003",
		severity: "warning",
		title: "模型漂移 — 情绪 Alpha v2",
		desc: "模型漂移 — 情绪 Alpha v2",
		time: "1小时前",
	},
	{
		id: "home-alert-004",
		severity: "info",
		title: "财报数据延迟",
		desc: "财报数据延迟",
		time: "2小时前",
	},
];

export const mockAgentFindings: readonly HomeAgentFinding[] = [
	{
		text: "情绪 Alpha v2 模型漂移检测 — 近 5 日 IC 从 0.041 降至 0.028，需关注。",
		source: "模型监控 · 2小时前",
		icon: "insight",
		summary: "模型监控 · 2小时前",
		time: "2小时前",
	},
	{
		text: "新因子「北向持仓变化率」验证中 — 初步 IC 0.055，待 3 个月滚动验证。",
		source: "因子研究 · 4小时前",
		icon: "warning",
		summary: "因子研究 · 4小时前",
		time: "4小时前",
	},
	{
		text: "行业轮动策略参数优化完成 — 新参数组 Sharpe 提升 0.15，待人工复核。",
		source: "优化引擎 · 6小时前",
		icon: "info",
		summary: "优化引擎 · 6小时前",
		time: "6小时前",
	},
];

export const mockDataHealth: readonly DataHealthProvider[] = [
	{
		label: "行情数据",
		status: "healthy",
		statusText: "正常",
		lastUpdate: "2026-03-28T09:30:00Z",
	},
	{
		label: "期权链",
		status: "healthy",
		statusText: "正常",
		lastUpdate: "2026-03-28T09:30:00Z",
	},
	{
		label: "财报数据",
		status: "degraded",
		statusText: "延迟",
		lastUpdate: "2026-03-28T08:00:00Z",
	},
	{
		label: "新闻资讯",
		status: "healthy",
		statusText: "正常",
		lastUpdate: "2026-03-28T09:30:00Z",
	},
	{
		label: "另类数据",
		status: "degraded",
		statusText: "陈旧（3天）",
		lastUpdate: "2026-03-25T09:30:00Z",
	},
];

export const mockMarketPulseMetrics: readonly MarketPulseMetric[] = [
	{
		label: "沪深300",
		value: "3,432",
		change: "+0.82%",
		sparkline: [3420, 3415, 3425, 3430, 3428, 3432],
	},
	{
		label: "波动率",
		value: "IVIX 18.52",
		change: "-3.1%",
		sparkline: [19.8, 19.5, 19.2, 18.9, 18.7, 18.52],
	},
	{
		label: "涨跌比",
		value: "2.1:1",
		change: "偏多",
	},
	{
		label: "北向资金",
		value: "+12.4 亿",
		change: "",
		sparkline: [8.2, 10.5, 9.1, 11.3, 12.0, 12.4],
	},
];

/** Legacy: retained for handler/test backwards compatibility */
export const mockRecentSignals: readonly RecentSignal[] = [];

/** Legacy: retained for handler/test backwards compatibility */
export const mockMarketIndices: readonly MarketIndex[] = [];
