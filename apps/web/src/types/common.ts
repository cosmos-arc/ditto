// === 通用枚举 ===

/** 交易阶段 */
export type MarketSession = "pre_market" | "call_auction" | "continuous" | "lunch" | "close" | "after_hours";

/** 告警严重度 */
export type Severity = "critical" | "warning" | "info";

/** 优先级 */
export type Priority = "critical" | "high" | "medium" | "low";

/** 排序方向 */
export type SortDirection = "asc" | "desc";

/** 排序字段 */
export type SortField = {
	readonly field: string;
	readonly direction: SortDirection;
};

/** 时间范围 */
export type TimeRange = {
	readonly from: string;
	readonly to: string;
};

/** 市场状态 */
export type MarketRegime = "risk_on" | "risk_off" | "mixed";

/** 信号方向 */
export type SignalDirection = "BUY" | "SELL" | "HOLD";

/** 订单方向 */
export type OrderSide = "BUY" | "SELL";

/** 订单类型 */
export type OrderType = "LIMIT" | "MARKET";

/** 订单状态 */
export type OrderStatus = "pending" | "submitted" | "partial" | "filled" | "failed" | "cancelled";

/** 信号状态 */
export type SignalStatus = "pending" | "confirmed" | "ignored" | "ordered";

/** 运行状态 */
export type RunStatus = "pending" | "running" | "completed" | "warning" | "failed" | "cancelled";

/** 健康状态 */
export type HealthStatus = "healthy" | "degraded" | "error";

/** 审批状态 */
export type ApprovalStatus = "pending" | "approved" | "rejected";

// === 通用数据结构 ===

/** 统一 API 响应包装 */
export type ApiResponse<T> = {
	readonly data: T;
	readonly meta?: {
		readonly timestamp: string;
		readonly requestId: string;
	};
};

/** 分页请求 */
export type PaginatedRequest = {
	readonly page?: number;
	readonly pageSize?: number;
};

/** 分页响应 */
export type PaginatedResponse<T> = {
	readonly items: readonly T[];
	readonly total: number;
	readonly page: number;
	readonly pageSize: number;
};

/** 筛选操作符 */
export type FilterOperator = "eq" | "gt" | "lt" | "gte" | "lte" | "in" | "contains";

/** 通用筛选条件 */
export type FilterCondition = {
	readonly field: string;
	readonly op: FilterOperator;
	readonly value: string | number | boolean | readonly string[];
};

/** Sparkline 数据点 */
export type SparklinePoint = {
	readonly time: string;
	readonly value: number;
};

/** 置信度区间 */
export type ConfidenceInterval = {
	readonly value: number;
	readonly confidence: number;
};

// === WebSocket 消息 ===

/** 行情推送 */
export type QuoteMessage = {
	readonly code: string;
	readonly price: number;
	readonly change: number;
	readonly volume: number;
	readonly bid: number;
	readonly ask: number;
};

/** 订单状态推送 */
export type OrderStatusMessage = {
	readonly orderId: string;
	readonly status: OrderStatus;
	readonly filledQty: number;
	readonly avgPrice: number;
};

/** Agent 状态推送 */
export type AgentStatusMessage = {
	readonly runId: string;
	readonly stage: string;
	readonly progress: number;
	readonly finding?: string;
};

/** 告警推送 */
export type AlertPushMessage = {
	readonly id: string;
	readonly severity: Severity;
	readonly title: string;
};
