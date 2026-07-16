import type { HealthStatus, MarketRegime, MarketSession, Priority, Severity, SignalDirection } from "./common";

// === Request Types ===

export type GetHomePulseRequest = undefined;

export type GetDecisionBannerRequest = undefined;

export type GetPendingActionsRequest = undefined;

export type GetHomeAlertsRequest = undefined;

export type GetRecentSignalsRequest = undefined;

export type GetAgentFindingsRequest = undefined;

export type GetDataHealthRequest = undefined;

export type GetMarketPulseMetricsRequest = undefined;

export type GetMarketIndicesRequest = undefined;

// === Response Types ===

/** Home 脉动 */
export type HomePulseResponse = {
	readonly date: string;
	readonly session: MarketSession;
	readonly pendingActions: number;
	readonly criticalAlerts: number;
	readonly runningJobs: number;
	readonly pnlToday: number;
	readonly pnlPercent: number;
	readonly riskLevel: string;
	readonly regimeType: string;
};

/** 决策横幅 */
export type DecisionBannerResponse = {
	readonly totalEquity: number;
	readonly dailyPnl: number;
	readonly dailyPnlPercent: number;
	readonly riskUtilization: number;
	readonly leverage: number;
	readonly maxDrawdown: number;
	readonly ivix: number;
	readonly northboundFlow: number;
	readonly equitySparkline: readonly number[];
	readonly marketRegime: MarketRegime;
	readonly regimeType: string;
	readonly suggestion: string;
};

/** 待处理事项徽章 */
export type ActionBadge = {
	readonly type: string;
	readonly label: string;
};

/** 待处理事项 */
export type PendingAction = {
	readonly id: string;
	readonly priority: Priority;
	readonly title: string;
	readonly meta: string;
	readonly time: string;
	readonly badges: readonly ActionBadge[];
	readonly domain: "trading" | "research" | "platform";
};

export type GetPendingActionsResponse = {
	readonly actions: readonly PendingAction[];
};

/** Home 告警 */
export type HomeAlert = {
	readonly id: string;
	readonly severity: Severity;
	readonly title: string;
	readonly desc: string;
	readonly time: string;
};

export type GetHomeAlertsResponse = {
	readonly alerts: readonly HomeAlert[];
};

/** 近期信号 */
export type RecentSignal = {
	readonly ticker: string;
	readonly action: SignalDirection;
	readonly strategy: string;
	readonly confidence: number;
	readonly time: string;
};

export type GetRecentSignalsResponse = {
	readonly signals: readonly RecentSignal[];
};

/** Agent 发现 */
export type AgentFinding = {
	readonly text: string;
	readonly source: string;
	readonly icon: "insight" | "warning" | "info";
	readonly summary?: string;
	readonly time?: string;
};

export type GetAgentFindingsResponse = {
	readonly findings: readonly AgentFinding[];
};

/** 数据健康 */
export type DataHealthProvider = {
	readonly label: string;
	readonly status: HealthStatus;
	readonly statusText: string;
	readonly lastUpdate: string;
};

export type GetDataHealthResponse = {
	readonly providers: readonly DataHealthProvider[];
};

/** 市场指数快照 */
export type MarketIndex = {
	readonly name: string;
	readonly code: string;
	readonly price: number;
	readonly change: number;
	readonly changePercent: number;
	readonly dir: "up" | "down";
};

export type GetMarketIndicesResponse = {
	readonly indices: readonly MarketIndex[];
};

/** 市场脉搏指标 */
export type MarketPulseMetric = {
	readonly label: string;
	readonly value: string;
	readonly change: string;
	readonly sparkline?: readonly number[];
};

export type GetMarketPulseMetricsResponse = {
	readonly metrics: readonly MarketPulseMetric[];
};
