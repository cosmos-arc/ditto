import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { DecisionBanner } from "@/components/domain/decision-banner";
import type { BadgeVariant } from "@/components/status";
import { TradingSessionStrip } from "./trading-session-strip";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";
import { TradingOverviewOrdersPanel } from "./trading-overview-orders-panel";
import { TradingOverviewSignalsPanel } from "./trading-overview-signals-panel";
import { mapReadinessStatus } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecision } from "../hooks";

/* ── Mock Data: Decision Banner ── */

const DECISION_BANNER_PROPS = {
	primary: {
		label: "组合净值",
		value: "1.0842",
		sub: "今日 +1.24%",
		trend: "up" as const,
		sparkline: [1.02, 1.04, 1.03, 1.05, 1.06, 1.07, 1.08],
	},
	judgment: {
		text: "当前市场风险偏好上升，建议适度加仓。杠杆率 1.2x，最大回撤 -2.3%。",
		regime: { label: "Risk-On", variant: "regime-on" as const },
		metrics: [
			{ label: "IVIX", value: "18.5", trend: "down" as const },
			{ label: "北向资金", value: "+3.2亿", trend: "up" as const },
		],
	},
	actions: [
		{ label: "执行调仓", variant: "primary" as const },
		{ label: "查看详情", variant: "secondary" as const },
	],
};

const READINESS_BADGE_VARIANT: Record<string, BadgeVariant> = {
	ready: "healthy",
	review: "warning",
	blocked: "critical",
	failed: "error",
};

function maxDeviationBps(
	items: readonly { readonly deviation_bps?: number | null }[] | undefined,
): number | null {
	if (!items || items.length === 0) return null;

	return items.reduce<number | null>((max, item) => {
		if (item.deviation_bps == null) return max;
		const value = Math.abs(item.deviation_bps);
		if (max == null) return value;
		return Math.max(max, value);
	}, null);
}

/* ── Page Component ── */

export function TradingPage() {
	const liveMode = !shouldUsePrototypeMocks();
	const { data: dailyDecision } = useDailyDecision(undefined, undefined, {
		enabled: liveMode,
	});
	const readiness = dailyDecision ? mapReadinessStatus(dailyDecision.readiness.status) : null;
	const deviationBps = maxDeviationBps(dailyDecision?.deviation?.items);
	const decisionBannerProps =
		liveMode && dailyDecision && readiness
			? {
					primary: {
						label: "Daily Decision",
						value: readiness.label,
						sub: dailyDecision.trade_date ?? "latest",
						trend:
							dailyDecision.readiness.status === "ready"
								? ("up" as const)
								: ("down" as const),
					},
					judgment: {
						text: `${readiness.summary}：${
							dailyDecision.readiness.reasons[0] ?? "无额外阻塞原因"
						}`,
						regime: {
							label: readiness.label,
							variant: READINESS_BADGE_VARIANT[readiness.tone] ?? "default",
						},
						metrics: [
							{
								label: "Signals",
								value: `信号 ${dailyDecision.signal_intents.length} 条`,
							},
							{
								label: "Positions",
								value: `持仓 ${dailyDecision.positions.length} 个`,
							},
							{
								label: "Deviation",
								value: deviationBps == null ? "偏差 —" : `偏差 ${deviationBps} bps`,
							},
						],
					},
					actions: [
						{ label: "打开信号", variant: "primary" as const },
						{ label: "查看组合", variant: "secondary" as const },
					],
				}
			: DECISION_BANNER_PROPS;

	return (
		<>
		<AnalyticalLayout
			className="pb-(--height-status-bar)"
			strip={<TradingSessionStrip />}
			banner={
				<div className="p-(--density-panel-padding) pb-0" data-info-level="l1" data-info-unit="decision-banner">
					<DecisionBanner {...decisionBannerProps} data-primary-answer={liveMode ? "true" : undefined} />
				</div>
			}
			main={
				<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding)">
					<EquityPnlBlock />
					<PositionsSummary />
					<RiskAlertsBlock />
					<TradingOverviewOrdersPanel />
				</div>
			}
			activity={<TradingOverviewSignalsPanel />}
		/>
		<StatusBar />
		</>
	);
}
