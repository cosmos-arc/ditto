import type {
	GetPositionsResponse,
	GetSignalDetailResponse,
	GetSignalsRequest,
	GetSignalsQueueResponse,
	GetSignalsResponse,
	GetOrdersSummaryResponse,
	Position,
	RiskCheck,
	Signal,
	SignalDirection,
	SignalExecutionIntent,
	SignalStatus,
} from "@/types";
import type { components } from "@/types/generated/api";

type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
type TradeIntentResponse = components["schemas"]["TradeIntentResponse"];
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
	partially_filled: "ordered",
	cancelled: "ignored",
	expired: "ignored",
};

function instrumentLabel(instrumentId: number): string {
	return `#${instrumentId}`;
}

function mapDirection(direction: string): SignalDirection {
	const normalized = direction.toUpperCase();
	if (normalized === "SELL") return "SELL";
	if (normalized === "HOLD") return "HOLD";
	return "BUY";
}

function mapFillDirection(direction: string): SignalExecutionIntent["direction"] {
	return direction.toLowerCase() === "sell" ? "sell" : "buy";
}

function mapIntentStatus(status: string): SignalStatus {
	return INTENT_STATUS_TO_SIGNAL_STATUS[status] ?? "pending";
}

function confidenceFromIntent(intent: TradeIntentResponse): number {
	const magnitude = Math.min(Math.abs(intent.delta_weight) / 0.2, 1);
	return Math.max(0.55, Math.round((0.65 + magnitude * 0.3) * 100) / 100);
}

function findDeviationItem(
	report: DailyDecisionReportResponse,
	instrumentId: number,
): SignalDeviationItem | undefined {
	return report.deviation?.items.find((item) => item.instrument_id === instrumentId);
}

function deviationRiskCheck(item?: SignalDeviationItem): RiskCheck {
	if (!item || item.deviation_bps == null) {
		return {
			name: "价格合理性",
			status: "pass",
			message: "暂无成交偏差，等待手工成交回填",
		};
	}

	const absBps = Math.abs(item.deviation_bps);
	const status: RiskCheck["status"] = absBps >= 250 ? "fail" : absBps >= 100 ? "warn" : "pass";
	const message =
		status === "pass"
			? `信号与成交偏差 ${item.deviation_bps} bps，在容忍区间内`
			: `信号与成交偏差 ${item.deviation_bps} bps，需复核执行价格`;

	return {
		name: "价格合理性",
		status,
		message,
	};
}

function mapIntentToSignal(intent: TradeIntentResponse): Signal {
	const direction = mapDirection(intent.direction);
	return {
		id: intent.intent_id,
		time: `${intent.signal_date}T09:30:00Z`,
		instrument: instrumentLabel(intent.instrument_id),
		source: `目标权重 ${(intent.target_weight * 100).toFixed(1)}%`,
		direction,
		weight: intent.target_weight,
		confidence: confidenceFromIntent(intent),
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
	const filtered = report.signal_intents.map(mapIntentToSignal).filter((signal) => signal.status === tab);
	const start = (page - 1) * pageSize;

	return {
		items: filtered.slice(start, start + pageSize),
		total: filtered.length,
		page,
		pageSize,
	};
}

export function mapDailyDecisionToSignalsQueue(
	report: DailyDecisionReportResponse,
): GetSignalsQueueResponse {
	return report.signal_intents.reduce<GetSignalsQueueResponse>(
		(counts, intent) => {
			const status = mapIntentStatus(intent.status);
			return {
				...counts,
				[status]: counts[status] + 1,
			};
		},
		{ pending: 0, confirmed: 0, ignored: 0, ordered: 0 },
	);
}

export function mapDailyDecisionToOrdersSummary(
	report: DailyDecisionReportResponse,
): GetOrdersSummaryResponse {
	return report.signal_intents.reduce<GetOrdersSummaryResponse>(
		(counts, intent) => {
			if (intent.status === "filled") {
				return { ...counts, filled: counts.filled + 1 };
			}
			if (intent.status === "partially_filled") {
				return { ...counts, partial: counts.partial + 1 };
			}
			if (intent.status === "cancelled" || intent.status === "expired") {
				return { ...counts, failed: counts.failed + 1 };
			}
			return { ...counts, pending: counts.pending + 1 };
		},
		{ pending: 0, submitted: 0, partial: 0, filled: 0, failed: 0 },
	);
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
		pnlPercent: position.average_cost === 0 ? 0 : ((currentPrice - position.average_cost) / position.average_cost) * 100,
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

	return {
		explanation: `${instrumentLabel(intent.instrument_id)} ${direction} 信号来自 ${report.strategy_id}，目标权重 ${(
			intent.target_weight * 100
		).toFixed(1)}%，当前权重 ${(intent.current_weight * 100).toFixed(1)}%，调整 ${
			intent.delta_weight >= 0 ? "+" : ""
		}${(intent.delta_weight * 100).toFixed(1)}%。`,
		riskChecks: [
			{ name: "涨跌停检查", status: "pass", message: "后端未报告涨跌停阻塞" },
			{
				name: "集中度检查",
				status: Math.abs(intent.target_weight) > 0.3 ? "warn" : "pass",
				message: `目标权重 ${(intent.target_weight * 100).toFixed(1)}%`,
			},
			{ name: "组合影响", status: report.readiness.status === "ready" ? "pass" : "warn", message: mapReadinessStatus(report.readiness.status).summary },
			{ name: "流动性检查", status: "warn", message: "V1a 后端暂未提供流动性端点，需人工确认" },
			deviationRiskCheck(deviation),
		],
		portfolioImpact: {
			concentrationChange: intent.delta_weight,
			sectorExposure: intent.target_weight,
			riskChange: Math.abs(intent.delta_weight) / 2,
		},
		actions: [
			{ type: "record_fill", label: "录入手工成交", enabled: true },
			{ type: "update_status", label: "更新意图状态", enabled: true },
			{ type: "ai_interpret", label: "AI 解读", enabled: false },
		],
		execution: {
			intentId: intent.intent_id,
			strategyId: intent.strategy_id,
			tradeDate: intent.signal_date,
			instrumentId: intent.instrument_id,
			direction: mapFillDirection(intent.direction),
			quantity: intent.quantity ?? 0,
			status: intent.status,
		},
	};
}
