import type {
	FilterCondition,
	OrderSide,
	OrderStatus,
	OrderType,
	PaginatedRequest,
	PaginatedResponse,
	SignalDirection,
	SignalStatus,
} from "./common";

// === Request Types ===

export type GetTradingSessionRequest = undefined;

export type GetEquityRequest = {
	readonly timeframe: string;
};

export type GetPositionsRequest = undefined;

export type GetRiskSummaryRequest = undefined;

export type GetSignalsQueueRequest = undefined;

export type GetOrdersSummaryRequest = undefined;

export type GetAttributionRequest = undefined;

export type GetTradingHealthCheckRequest = undefined;

export type PostTradingPauseRequest = {
	readonly reason: string;
};

export type GetSignalsRequest = {
	readonly tab: SignalStatus;
	readonly page?: number;
	readonly limit?: number;
} & PaginatedRequest;

export type GetSignalDetailRequest = {
	readonly id: string;
};

export type ConfirmSignalRequest = undefined;

export type IgnoreSignalRequest = {
	readonly reason: string;
};

export type BatchConfirmSignalsRequest = {
	readonly signalIds: readonly string[];
};

export type ValidateOrderRequest = {
	readonly instrument: string;
	readonly side: OrderSide;
	readonly qty: number;
	readonly price: number;
	readonly type: OrderType;
};

export type SubmitOrderRequest = {
	readonly instrument: string;
	readonly side: OrderSide;
	readonly qty: number;
	readonly price: number;
	readonly type: OrderType;
	readonly signalId?: string;
};

export type GetSignalAiInterpretationRequest = {
	readonly id: string;
};

export type GetOrdersRequest = {
	readonly tab: OrderStatus;
	readonly page?: number;
	readonly limit?: number;
	readonly sort?: string;
} & PaginatedRequest;

export type GetOrderDetailRequest = {
	readonly id: string;
};

export type CancelOrderRequest = undefined;

export type RetryOrderRequest = undefined;

export type GetRiskVarRequest = undefined;

export type GetRiskDrawdownRequest = undefined;

export type GetRiskExposureRequest = undefined;

export type GetRiskBreachesRequest = PaginatedRequest;

export type PostRiskStressTestRequest = {
	readonly scenario: string;
	readonly positions?: readonly string[];
};

export type GetRiskIncidentsRequest = PaginatedRequest;

export type PutRiskRuleRequest = {
	readonly id: string;
	readonly threshold: number;
	readonly action: string;
	readonly enabled: boolean;
};

// === Response Types ===

/** 交易会话 */
export type MarginData = {
	readonly totalMargin: number;
	readonly usedMargin: number;
	readonly availableMargin: number;
	readonly maintenanceRatio: number;
};

export type RouteHealth = {
	readonly name: string;
	readonly status: string;
	readonly latency: number;
};

export type TradingSessionResponse = {
	readonly phase: string;
	readonly cashBalance: number;
	readonly margin: MarginData;
	readonly riskBudget: number;
	readonly routeHealth: RouteHealth;
	readonly marginData: MarginData;
};

/** 权益曲线 */
export type EquityPoint = {
	readonly time: string;
	readonly equity: number;
	readonly pnl: number;
	readonly pnlPercent: number;
};

export type GetEquityResponse = {
	readonly series: readonly EquityPoint[];
};

/** 持仓 */
export type Position = {
	readonly code: string;
	readonly name: string;
	readonly qty: number;
	readonly availableQty: number;
	readonly avgCost: number;
	readonly currentPrice: number;
	readonly pnl: number;
	readonly pnlPercent: number;
	readonly weight: number;
	readonly frozenQty: number;
	readonly sparkline7d?: readonly number[];
};

export type GetPositionsResponse = {
	readonly positions: readonly Position[];
};

/** 风险概览 */
export type RiskSummaryResponse = {
	readonly var: number;
	readonly maxDD: number;
	readonly beta: number;
	readonly grossExposure: number;
	readonly netExposure: number;
	readonly nearLimit: boolean;
	readonly breachCount: number;
};

/** 信号队列计数 */
export type SignalsQueueResponse = {
	readonly pending: number;
	readonly confirmed: number;
	readonly ignored: number;
	readonly ordered: number;
};

/** 订单汇总计数 */
export type OrdersSummaryResponse = {
	readonly pending: number;
	readonly submitted: number;
	readonly partial: number;
	readonly filled: number;
	readonly failed: number;
};

/** 归因分析 */
export type AttributionSector = {
	readonly sector: string;
	readonly contribution: number;
	readonly weight: number;
};

export type AttributionStock = {
	readonly code: string;
	readonly name: string;
	readonly contribution: number;
	readonly weight: number;
};

export type AttributionFactor = {
	readonly factor: string;
	readonly contribution: number;
	readonly exposure: number;
};

export type GetAttributionResponse = {
	readonly sectors: readonly AttributionSector[];
	readonly stocks: readonly AttributionStock[];
	readonly factors: readonly AttributionFactor[];
};

/** 健康检查 */
export type HealthCheckItem = {
	readonly name: string;
	readonly status: string;
	readonly detail: string;
};

export type GetTradingHealthCheckResponse = {
	readonly checks: readonly HealthCheckItem[];
};

/** 信号 */
export type Signal = {
	readonly id: string;
	readonly time: string;
	readonly instrument: string;
	readonly source: string;
	readonly direction: SignalDirection;
	readonly weight: number;
	readonly confidence: number;
	readonly status: SignalStatus;
	readonly limitUpDownCheck: {
		readonly limitUp: boolean;
		readonly limitDown: boolean;
		readonly days: number;
	};
};

export type GetSignalsResponse = PaginatedResponse<Signal>;

/** 信号详情 */
export type RiskCheck = {
	readonly name: string;
	readonly status: "pass" | "warn" | "fail";
	readonly message: string;
};

export type PortfolioImpact = {
	readonly concentrationChange: number;
	readonly sectorExposure: number;
	readonly riskChange: number;
};

export type SignalAction = {
	readonly type: string;
	readonly label: string;
	readonly enabled: boolean;
};

export type GetSignalDetailResponse = {
	readonly explanation: string;
	readonly riskChecks: readonly RiskCheck[];
	readonly portfolioImpact: PortfolioImpact;
	readonly actions: readonly SignalAction[];
};

/** 信号确认响应 */
export type ConfirmSignalResponse = {
	readonly orderId: string;
};

/** AI 信号解读 */
export type SimilarHistory = {
	readonly date: string;
	readonly instrument: string;
	readonly action: SignalDirection;
	readonly outcome: number;
};

export type GetSignalAiInterpretationResponse = {
	readonly interpretation: string;
	readonly similarHistory: readonly SimilarHistory[];
	readonly riskAssessment: string;
};

/** 订单校验 */
export type ValidateOrderResponse = {
	readonly valid: boolean;
	readonly instrumentStatus: string;
	readonly estimatedFee: number;
	readonly warnings: readonly string[];
};

/** 订单提交 */
export type SubmitOrderResponse = {
	readonly orderId: string;
	readonly status: OrderStatus;
};

/** 订单 */
export type Order = {
	readonly id: string;
	readonly instrument: string;
	readonly side: OrderSide;
	readonly qty: number;
	readonly price: number;
	readonly filledQty: number;
	readonly type: OrderType;
	readonly status: OrderStatus;
	readonly account: string;
	readonly createdAt: string;
	readonly updatedAt: string;
};

export type GetOrdersResponse = PaginatedResponse<Order>;

/** 订单追踪 */
export type OrderTrace = {
	readonly time: string;
	readonly event: string;
	readonly detail?: string;
};

export type GetOrderDetailResponse = {
	readonly order: Order;
	readonly trace: readonly OrderTrace[];
	readonly rejectReason?: string;
	readonly fees: number;
	readonly slippage: number;
	readonly routeLog: readonly OrderTrace[];
};

/** VaR 时序 */
export type VarPoint = {
	readonly date: string;
	readonly var95: number;
	readonly var99: number;
};

export type GetRiskVarResponse = {
	readonly series: readonly VarPoint[];
};

/** 回撤时序 */
export type DrawdownPoint = {
	readonly date: string;
	readonly drawdown: number;
	readonly maxDD: number;
};

export type GetRiskDrawdownResponse = {
	readonly series: readonly DrawdownPoint[];
};

/** 敞口 */
export type ExposureByDimension = {
	readonly name: string;
	readonly long: number;
	readonly short: number;
	readonly net: number;
};

export type GetRiskExposureResponse = {
	readonly grossExposure: number;
	readonly netExposure: number;
	readonly bySector: readonly ExposureByDimension[];
	readonly byStyle: readonly ExposureByDimension[];
	readonly byFactor: readonly ExposureByDimension[];
};

/** 风控违规 */
export type RiskBreach = {
	readonly id: string;
	readonly ruleName: string;
	readonly currentValue: number;
	readonly threshold: number;
	readonly deviation: number;
	readonly affectedPositions: readonly string[];
	readonly status: "active" | "acknowledged" | "resolved";
};

export type GetRiskBreachesResponse = PaginatedResponse<RiskBreach>;

/** 压力测试 */
export type StressTestResult = {
	readonly scenario: string;
	readonly impactPnl: number;
	readonly maxLoss: number;
	readonly affectedPositions: readonly string[];
};

export type PostRiskStressTestResponse = StressTestResult;

/** 风控事件 */
export type RiskIncident = {
	readonly id: string;
	readonly severity: "critical" | "warning" | "info";
	readonly status: "active" | "investigating" | "resolved";
	readonly handler: string;
	readonly resolution: string;
	readonly createdAt: string;
};

export type GetRiskIncidentsResponse = PaginatedResponse<RiskIncident>;
