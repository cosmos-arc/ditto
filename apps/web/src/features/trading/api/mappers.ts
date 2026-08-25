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
import type { DailyDecisionReadiness, DailyDecisionV3ViewModel } from "../types/daily-decision-v3";

type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
type DailyDecisionV3Response = components["schemas"]["DailyDecisionV3Response"];
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

function nullableString(value: string | null | undefined): string | null {
	return typeof value === "string" && value.length > 0 ? value : null;
}

function nullableNumber(value: number | null | undefined): number | null {
	return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function unique(values: readonly string[]): string[] {
	return [...new Set(values)];
}

export function mapDailyDecisionV3(report: DailyDecisionV3Response): DailyDecisionV3ViewModel {
	const provenance = report.provenance;
	const sourceSnapshotIds = provenance.source_snapshot_ids.filter((value) => value.length > 0);
	const provenanceComplete = Boolean(
		provenance.decision_time &&
			provenance.knowledge_cutoff &&
			provenance.publication_cutoff &&
			provenance.generated_at &&
			sourceSnapshotIds.length > 0,
	);
	const hardIssues: string[] = [];
	const partialIssues: string[] = [];
	if (!provenanceComplete) hardIssues.push("PIT_PROVENANCE_INCOMPLETE");
	if ([report.tail_risk.historical_es99, report.tail_risk.historical_var99].every((value) => value == null)) {
		hardIssues.push("TAIL_RISK_UNAVAILABLE");
	}
	if (["failed", "blocked", "unavailable"].includes(report.portfolio_construction.status.toLowerCase())) {
		hardIssues.push(report.portfolio_construction.failure_code ?? "PORTFOLIO_CONSTRUCTION_FAILED");
	}
	if (!["matched", "reconciled", "ok"].includes(report.reconciliation.status.toLowerCase())) {
		hardIssues.push("RECONCILIATION_MISMATCH");
	}
	if (report.factor_risk.availability !== "available") {
		partialIssues.push(`FACTOR_RISK_${report.factor_risk.availability.toUpperCase()}`);
	}
	const unavailableScenarios = report.stress_tests.unavailable_scenarios ?? [];
	if (unavailableScenarios.length > 0) partialIssues.push("STRESS_SCENARIOS_UNAVAILABLE");

	const reportedStatus: DailyDecisionReadiness = report.readiness;
	const status: DailyDecisionReadiness = hardIssues.length > 0 ? "blocked" : reportedStatus;
	const blockingReasons = unique([...report.blocking_reasons, ...hardIssues]);
	const issues = unique([...hardIssues, ...partialIssues]);
	const identity = report.v2.identity;
	const account = report.v2.account_positions;

	return {
		identity: {
			strategyId: identity.strategy_id,
			strategyVersion: nullableString(identity.strategy_version),
			signalDate: nullableString(identity.signal_date),
			tradeDate: nullableString(identity.intended_trade_date) ?? nullableString(identity.signal_date),
			accountId: nullableString(identity.account_id),
			sleeveId: nullableString(identity.sleeve_id),
		},
		readiness: { status, reportedStatus, blockingReasons },
		data: {
			freshness: nullableString(report.v2.data.freshness),
			qualityState: nullableString(report.v2.data.dq_state),
			snapshotIds: report.v2.data.snapshot_ids,
		},
		account: {
			asOf: nullableString(account.as_of),
			baselineId: nullableString(account.baseline_id),
			cashAvailable: nullableNumber(account.cash_available),
			totalValue: nullableNumber(account.total_value),
			exposure: nullableNumber(account.exposure),
			positions: account.positions.map((position) => ({
				instrumentId: position.instrument_id,
				quantity: position.quantity,
				availableQuantity: nullableNumber(position.available_quantity),
				marketValue: nullableNumber(position.market_value),
			})),
		},
		actions: report.v2.actions.map((action) => ({
			intentId: action.intent_id,
			instrumentId: action.instrument_id,
			direction: nullableString(action.direction),
			currentWeight: nullableNumber(action.current_weight),
			targetWeight: action.target_weight,
			deltaWeight: nullableNumber(action.delta_weight),
			suggestedQuantity: nullableNumber(action.suggested_quantity),
			filledQuantity: nullableNumber(action.filled_quantity),
			remainingQuantity: nullableNumber(action.remaining_quantity),
			sizingReadiness: nullableString(action.sizing_readiness),
			executionStatus: nullableString(action.intent_status),
			riskFlags: action.risk_flags,
		})),
		portfolioConstruction: {
			status: report.portfolio_construction.status,
			solver: nullableString(report.portfolio_construction.solver),
			solverVersion: nullableString(report.portfolio_construction.solver_version),
			mode: nullableString(report.portfolio_construction.mode),
			solverStatus: nullableString(report.portfolio_construction.solver_status),
			durationMs: nullableNumber(report.portfolio_construction.duration_ms),
			policyDigest: nullableString(report.portfolio_construction.policy_digest),
			failureCode: nullableString(report.portfolio_construction.failure_code),
		},
		tailRisk: {
			historicalEs99: nullableNumber(report.tail_risk.historical_es99),
			historicalVar99: nullableNumber(report.tail_risk.historical_var99),
			parametricVar99: nullableNumber(report.tail_risk.parametric_var99),
			monteCarloVar99: nullableNumber(report.tail_risk.monte_carlo_var99),
			monteCarloSeed: nullableNumber(report.tail_risk.monte_carlo_seed),
		},
		factorRisk: {
			availability: report.factor_risk.availability,
			totalRisk: nullableNumber(report.factor_risk.total_risk),
			marginalContributions: report.factor_risk.marginal_contributions,
			percentageContributions: report.factor_risk.percentage_contributions,
			eulerResidual: nullableNumber(report.factor_risk.euler_residual),
		},
		stressTests: {
			catalogVersion: report.stress_tests.catalog_version,
			losses: report.stress_tests.losses,
			unavailableScenarios,
		},
		reconciliation: {
			status: report.reconciliation.status,
			differences: report.reconciliation.differences,
			alertIdempotencyKey: nullableString(report.reconciliation.alert_idempotency_key),
		},
		provenance: {
			decisionTime: nullableString(provenance.decision_time),
			knowledgeCutoff: nullableString(provenance.knowledge_cutoff),
			publicationCutoff: nullableString(provenance.publication_cutoff),
			sourceSnapshotIds,
			generatedAt: nullableString(provenance.generated_at),
			complete: provenanceComplete,
		},
		completeness: {
			status: hardIssues.length > 0 ? "blocked" : partialIssues.length > 0 ? "partial" : "complete",
			issues,
		},
	};
}

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
			{ name: "流动性检查", status: "warn", message: "当前决策合同未提供逐项流动性结论，需人工确认" },
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
