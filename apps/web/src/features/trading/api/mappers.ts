import type {
	GetOrdersSummaryResponse,
	GetPositionsResponse,
	GetSignalDetailResponse,
	GetSignalsQueueResponse,
	GetSignalsRequest,
	GetSignalsResponse,
	Position,
	RiskCheck,
	Signal,
	SignalDirection,
	SignalExecutionIntent,
	SignalStatus,
} from "@/types";
import type { components } from "@/types/generated/api";

type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
type DailyDecisionActionResponse = Omit<components["schemas"]["DailyDecisionActionResponse"], "intent_status"> & {
	readonly intent_status?: string | null;
};
type TradeIntentResponse = components["schemas"]["TradeIntentResponse"];
type TradeIntentWithProgress = TradeIntentResponse & {
	readonly filled_quantity?: number | null;
	readonly remaining_quantity?: number | null;
};
type PositionSnapshotResponse = components["schemas"]["PositionSnapshotResponse"];
type SignalDeviationItem = components["schemas"]["SignalDeviationItem"];

type ReadinessState = DailyDecisionReportResponse["readiness"]["status"] | "failed";

type ReadinessView = {
	readonly label: string;
	readonly tone: "ready" | "review" | "blocked" | "failed";
	readonly summary: string;
};

const READINESS_VIEW: Record<ReadinessState, ReadinessView> = {
	ready: {
		label: "可执行",
		tone: "ready",
		summary: "交易驾驶舱已就绪",
	},
	review: {
		label: "需复核",
		tone: "review",
		summary: "存在需要人工确认的信号",
	},
	blocked: {
		label: "阻塞",
		tone: "blocked",
		summary: "当前缺少可执行信号或必要数据",
	},
	failed: {
		label: "加载失败",
		tone: "failed",
		summary: "无法读取真实后端数据",
	},
};

const INTENT_STATUS_TO_SIGNAL_STATUS: Record<string, SignalStatus> = {
	pending: "pending",
	filled: "ordered",
	partially_filled: "pending",
	cancelled: "ignored",
	expired: "ignored",
};

function parseV2Intent(
	action: DailyDecisionActionResponse,
	strategyId: string,
	signalDate: string,
): TradeIntentWithProgress | null {
	const direction = normalizeDirection(action.direction);
	if (!direction) return null;

	return {
		intent_id: action.intent_id,
		strategy_id: strategyId,
		signal_date: signalDate,
		instrument_id: action.instrument_id,
		direction,
		target_weight: action.target_weight,
		current_weight: action.current_weight,
		delta_weight: action.delta_weight,
		quantity: action.suggested_quantity ?? null,
		filled_quantity: action.filled_quantity,
		remaining_quantity: action.remaining_quantity ?? null,
		status: action.intent_status ?? "pending",
	};
}

function normalizeDirection(value: string | null): "buy" | "sell" | "hold" | null {
	const normalized = value?.toLowerCase();
	return normalized === "buy" || normalized === "sell" || normalized === "hold" ? normalized : null;
}

export function mapDailyDecisionV2ToLegacy(report: DailyDecisionV2Response): DailyDecisionReportResponse {
	const strategyId = report.identity.strategy_id;
	const signalDate = report.identity.signal_date ?? "";
	const intendedTradeDate = report.identity.intended_trade_date ?? signalDate;
	const signalIntents = report.actions
		.map((action) => parseV2Intent(action, strategyId, intendedTradeDate))
		.filter((intent): intent is TradeIntentWithProgress => intent !== null);

	return {
		strategy_id: strategyId,
		trade_date: signalDate || null,
		readiness: {
			status: report.readiness.status,
			reasons: [...report.readiness.reason_codes],
		},
		signal_intents: signalIntents,
		positions: report.account_positions.positions,
		deviation: report.execution_review.deviation ?? null,
		pnl: report.execution_review.pnl ?? null,
	};
}

function instrumentLabel(instrumentId: number): string {
	return `#${instrumentId}`;
}

function mapDirection(direction: string): SignalDirection | null {
	const normalized = direction.toUpperCase();
	if (normalized === "BUY" || normalized === "SELL" || normalized === "HOLD") {
		return normalized;
	}
	return null;
}

function mapFillDirection(direction: string): SignalExecutionIntent["direction"] {
	return direction.toLowerCase() === "sell" ? "sell" : "buy";
}

function mapIntentStatus(status: string): SignalStatus {
	return INTENT_STATUS_TO_SIGNAL_STATUS[status] ?? "pending";
}

function findDeviationItem(report: DailyDecisionReportResponse, instrumentId: number): SignalDeviationItem | undefined {
	return report.deviation?.items.find((item) => item.instrument_id === instrumentId);
}

function deviationRiskCheck(item?: SignalDeviationItem): RiskCheck {
	if (!item || item.deviation_bps == null) {
		return {
			name: "成交偏差证据",
			status: "warn",
			message: "暂无后端成交偏差证据",
		};
	}

	return {
		name: "成交偏差证据",
		status: "warn",
		message: `后端偏差证据 ${item.deviation_bps} bps；未提供风险阈值结论`,
	};
}

function mapIntentToSignal(intent: TradeIntentResponse): Signal | null {
	const direction = mapDirection(intent.direction);
	if (direction == null) return null;
	return {
		id: intent.intent_id,
		time: `${intent.signal_date}T09:30:00Z`,
		instrument: instrumentLabel(intent.instrument_id),
		source: `目标权重 ${(intent.target_weight * 100).toFixed(1)}%`,
		direction,
		weight: intent.target_weight,
		confidence: null,
		status: mapIntentStatus(intent.status),
		limitUpDownCheck: {
			limitUp: false,
			limitDown: false,
			days: 0,
		},
	};
}

export function mapReadinessStatus(status: ReadinessState): ReadinessView {
	return READINESS_VIEW[status];
}

export function mapDailyDecisionToSignalsResponse(
	report: DailyDecisionReportResponse,
	params: Pick<GetSignalsRequest, "tab" | "page" | "limit" | "pageSize"> = { tab: "pending" },
): GetSignalsResponse {
	const page = params.page ?? 1;
	const pageSize = params.limit ?? params.pageSize ?? 20;
	const tab = params.tab ?? "pending";
	const filtered = report.signal_intents
		.map(mapIntentToSignal)
		.filter((signal): signal is Signal => signal !== null)
		.filter((signal) => signal.status === tab);
	const start = (page - 1) * pageSize;

	return {
		items: filtered.slice(start, start + pageSize),
		total: filtered.length,
		page,
		pageSize,
	};
}

export function mapDailyDecisionToSignalsQueue(report: DailyDecisionReportResponse): GetSignalsQueueResponse {
	let pending = 0;
	let confirmed = 0;
	let ignored = 0;
	let ordered = 0;

	for (const intent of report.signal_intents) {
		const status = mapIntentStatus(intent.status);
		if (status === "confirmed") confirmed += 1;
		else if (status === "ignored") ignored += 1;
		else if (status === "ordered") ordered += 1;
		else pending += 1;
	}

	return { pending, confirmed, ignored, ordered };
}

export function mapDailyDecisionToOrdersSummary(report: DailyDecisionReportResponse): GetOrdersSummaryResponse {
	let pending = 0;
	let partial = 0;
	let filled = 0;
	let failed = 0;

	for (const intent of report.signal_intents) {
		if (intent.status === "filled") filled += 1;
		else if (intent.status === "partially_filled") partial += 1;
		else if (intent.status === "cancelled" || intent.status === "expired") failed += 1;
		else pending += 1;
	}

	return { pending, submitted: 0, partial, filled, failed };
}

function mapPosition(position: PositionSnapshotResponse): Position {
	const currentPrice = position.quantity === 0 ? position.average_cost : position.market_value / position.quantity;
	const pnl = position.unrealized_pnl + position.realized_pnl;

	return {
		code: instrumentLabel(position.instrument_id),
		name: instrumentLabel(position.instrument_id),
		qty: position.quantity,
		availableQty: position.available_quantity,
		avgCost: position.average_cost,
		currentPrice,
		pnl,
		pnlPercent:
			position.average_cost === 0 ? 0 : ((currentPrice - position.average_cost) / position.average_cost) * 100,
		weight: 0,
		frozenQty: Math.max(position.quantity - position.available_quantity, 0),
	};
}

export function mapPositionsResponse(report: DailyDecisionReportResponse): GetPositionsResponse {
	const totalMarketValue = report.positions.reduce((sum, position) => sum + position.market_value, 0);

	return {
		positions: report.positions.map((position) => {
			const mapped = mapPosition(position);
			return {
				...mapped,
				weight: totalMarketValue === 0 ? 0 : position.market_value / totalMarketValue,
			};
		}),
	};
}

export function mapDailyDecisionToSignalDetail(
	report: DailyDecisionReportResponse,
	intentId: string,
): GetSignalDetailResponse {
	const intent = report.signal_intents.find((item) => item.intent_id === intentId);

	if (!intent) {
		return {
			explanation: "未找到所选信号意图。请返回队列重新选择。",
			riskChecks: [
				{ name: "信号存在性", status: "fail", message: `intent_id=${intentId} 不存在` },
				{ name: "涨跌停检查", status: "warn", message: "未获取到标的状态" },
				{ name: "集中度检查", status: "warn", message: "未获取到目标权重" },
				{ name: "流动性检查", status: "warn", message: "后端暂未提供流动性端点" },
				deviationRiskCheck(),
			],
			portfolioImpact: {
				concentrationChange: 0,
				sectorExposure: 0,
				riskChange: 0,
			},
			actions: [],
		};
	}

	const deviation = findDeviationItem(report, intent.instrument_id);
	const direction = mapDirection(intent.direction);
	if (direction == null) {
		return {
			explanation: `intent_id=${intent.intent_id} 的方向字段无效，交易动作保持关闭。`,
			riskChecks: [
				{
					name: "方向契约",
					status: "fail",
					message: `未知方向：${intent.direction}`,
				},
			],
			actions: [],
		};
	}
	const remainingQuantity = (intent as TradeIntentWithProgress).remaining_quantity ?? null;
	const filledQuantity = (intent as TradeIntentWithProgress).filled_quantity ?? null;
	const canRecordFill = report.readiness.status !== "blocked" && (remainingQuantity ?? intent.quantity ?? 0) > 0;

	return {
		explanation: `${instrumentLabel(intent.instrument_id)} ${direction} 信号来自 ${report.strategy_id}，目标权重 ${(
			intent.target_weight * 100
		).toFixed(1)}%，当前权重 ${(intent.current_weight * 100).toFixed(1)}%，调整 ${
			intent.delta_weight >= 0 ? "+" : ""
		}${(intent.delta_weight * 100).toFixed(1)}%。`,
		riskChecks: [
			{ name: "涨跌停检查", status: "warn", message: "V2 未提供逐项涨跌停检查证据" },
			{
				name: "集中度检查",
				status: "warn",
				message: `后端目标权重证据 ${(intent.target_weight * 100).toFixed(1)}%，未返回检查结论`,
			},
			{ name: "流动性检查", status: "warn", message: "V1a 后端暂未提供流动性端点，需人工确认" },
			deviationRiskCheck(deviation),
		],
		actions: [
			{
				type: "record_fill",
				label: "录入手工成交",
				enabled: canRecordFill,
			},
		],
		execution: {
			intentId: intent.intent_id,
			strategyId: intent.strategy_id,
			tradeDate: intent.signal_date,
			instrumentId: intent.instrument_id,
			direction: mapFillDirection(intent.direction),
			quantity: intent.quantity ?? 0,
			filledQuantity,
			remainingQuantity,
			reviewReasons: report.readiness.reasons,
			status: intent.status,
		},
	};
}
