import type {
	DecisionBannerResponse,
	GetDataHealthResponse,
	GetHomeAgentFindingsResponse,
	GetHomeAlertsResponse,
	GetMarketPulseMetricsResponse,
	GetPendingActionsResponse,
	GetRecentSignalsResponse,
	HomePulseResponse,
	PendingAction,
	RecentSignal,
} from "@/types";
import type { components } from "@/types/generated/api";

type DailyDecisionV3Response = components["schemas"]["DailyDecisionV3Response"];

export type HomeLiveProjection = {
	readonly pulse: HomePulseResponse;
	readonly decisionBanner: DecisionBannerResponse;
	readonly pendingActions: GetPendingActionsResponse;
	readonly alerts: GetHomeAlertsResponse;
	readonly recentSignals: GetRecentSignalsResponse;
	readonly agentFindings: GetHomeAgentFindingsResponse;
	readonly dataHealth: GetDataHealthResponse;
	readonly marketPulse: GetMarketPulseMetricsResponse;
};

const TERMINAL_INTENT_STATUSES = new Set(["filled", "cancelled", "expired", "superseded"]);

function finite(value: number | null | undefined): number | null {
	return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isReconciled(status: string): boolean {
	return ["matched", "reconciled", "ok"].includes(status.toLowerCase());
}

function hasCompleteProvenance(report: DailyDecisionV3Response): boolean {
	const provenance = report.provenance;
	return Boolean(
		provenance.decision_time &&
			provenance.knowledge_cutoff &&
			provenance.publication_cutoff &&
			provenance.generated_at &&
			provenance.source_snapshot_ids.length > 0,
	);
}

function toSignalDirection(direction: string | null | undefined): RecentSignal["action"] | null {
	const normalized = direction?.toUpperCase();
	return normalized === "BUY" || normalized === "SELL" || normalized === "HOLD" ? normalized : null;
}

function pendingActions(report: DailyDecisionV3Response): readonly PendingAction[] {
	const decisionTime = report.provenance.decision_time ?? "时间未提供";
	const actions: PendingAction[] = [];

	for (const action of report.v2.actions) {
		if (TERMINAL_INTENT_STATUSES.has(action.intent_status?.toLowerCase() ?? "")) continue;
		const direction = action.direction?.toUpperCase() ?? "方向未提供";
		const riskEvidence = action.risk_flags.length > 0 ? action.risk_flags.join("、") : "无额外风险标记";
		actions.push({
			id: action.intent_id,
			priority: action.risk_flags.length > 0 ? "critical" : "high",
			title: `#${action.instrument_id} ${direction} 建议待人工复核`,
			meta: `目标权重 ${(action.target_weight * 100).toFixed(2)}%；建议数量 ${action.suggested_quantity ?? "未提供"}；${riskEvidence}`,
			time: decisionTime,
			badges: [
				{ type: "signal", label: "交易" },
				{ type: "priority", label: action.risk_flags.length > 0 ? "P1" : "P2" },
			],
			domain: "trading",
		});
	}

	for (const [index, reason] of report.blocking_reasons.entries()) {
		actions.push({
			id: `decision-blocker-${index}`,
			priority: "critical",
			title: reason,
			meta: "Daily Decision V3 阻断原因；需先消除证据缺口再继续执行。",
			time: decisionTime,
			badges: [
				{ type: "risk", label: "风控" },
				{ type: "priority", label: "P1" },
			],
			domain: "trading",
		});
	}

	return actions;
}

function recentSignals(report: DailyDecisionV3Response): readonly RecentSignal[] {
	return report.v2.actions.flatMap((action) => {
		const direction = toSignalDirection(action.direction);
		if (!direction) return [];
		return [
			{
				ticker: `#${action.instrument_id}`,
				action: direction,
				strategy: report.v2.identity.strategy_id,
				confidence: null,
				time: report.provenance.decision_time ?? "时间未提供",
			},
		];
	});
}

export function mapDailyDecisionV3ToHomeProjection(report: DailyDecisionV3Response): HomeLiveProjection {
	const pnl = finite(report.v2.execution_review.pnl?.net_pnl);
	const totalEquity = finite(report.v2.account_positions.total_value);
	const exposure = finite(report.v2.account_positions.exposure);
	const pnlPercent = pnl != null && totalEquity != null && totalEquity !== 0 ? (pnl / totalEquity) * 100 : null;
	const leverage = exposure != null && totalEquity != null && totalEquity !== 0 ? exposure / totalEquity : null;
	const actions = pendingActions(report);
	const provenanceComplete = hasCompleteProvenance(report);
	const reconciled = isReconciled(report.reconciliation.status);
	const decisionTime = report.provenance.decision_time ?? "";
	const alerts = [
		...report.blocking_reasons.map((reason, index) => ({
			id: `decision-blocker-${index}`,
			severity: "critical" as const,
			title: reason,
			desc: reason,
			time: decisionTime || "时间未提供",
		})),
		...(reconciled
			? []
			: [
					{
						id: "execution-reconciliation",
						severity: "critical" as const,
						title: "执行对账不一致",
						desc: report.reconciliation.differences.join("；") || report.reconciliation.status,
						time: decisionTime || "时间未提供",
					},
				]),
	];
	const riskLevel = report.readiness === "blocked" ? "阻断" : report.readiness === "review" ? "需复核" : "就绪";
	const suggestion =
		report.readiness === "blocked"
			? `决策已阻断：${report.blocking_reasons.join("；") || "后端未提供阻断原因"}`
			: report.readiness === "review"
				? "Daily Decision V3 要求人工复核后再形成执行意图。"
				: "Daily Decision V3 已就绪；执行仍需人工确认。";

	return {
		pulse: {
			date: report.v2.identity.intended_trade_date ?? report.v2.identity.signal_date ?? "日期未提供",
			session: null,
			pendingActions: actions.length,
			criticalAlerts: alerts.length,
			runningJobs: null,
			pnlToday: pnl,
			pnlPercent,
			riskLevel,
			regimeType: "市场环境未提供",
		},
		decisionBanner: {
			totalEquity,
			dailyPnl: pnl,
			dailyPnlPercent: pnlPercent,
			riskUtilization: null,
			leverage,
			maxDrawdown: null,
			ivix: null,
			northboundFlow: null,
			equitySparkline: [],
			marketRegime: null,
			regimeType: "市场环境未提供",
			suggestion,
		},
		pendingActions: { actions },
		alerts: { alerts },
		recentSignals: { signals: recentSignals(report) },
		agentFindings: { findings: [] },
		dataHealth: {
			providers: [
				{
					label: "决策数据",
					status: report.v2.data.freshness === "ready" && report.v2.data.dq_state === "passed" ? "healthy" : "degraded",
					statusText: `${report.v2.data.freshness ?? "unknown"} / ${report.v2.data.dq_state ?? "unknown"}`,
					lastUpdate: report.provenance.generated_at ?? "",
				},
				{
					label: "PIT 证据",
					status: provenanceComplete ? "healthy" : "error",
					statusText: provenanceComplete ? "完整" : "缺失",
					lastUpdate: report.provenance.generated_at ?? "",
				},
				{
					label: "执行对账",
					status: reconciled ? "healthy" : "error",
					statusText: report.reconciliation.status,
					lastUpdate: report.provenance.generated_at ?? "",
				},
			],
		},
		marketPulse: {
			metrics: [{ label: "市场行情", value: "不可用", change: "Daily Decision V3 未提供行情投影" }],
		},
	};
}
