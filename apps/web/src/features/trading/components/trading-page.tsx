import { DecisionBanner } from "@/components/domain/decision-banner";
import type { BadgeVariant } from "@/components/status";
import { AnalyticalLayout, StatusBar } from "@/features/shell";
import { resolveTradingExecutionScope, type TradingExecutionScope } from "../api/execution-scope";
import { mapReadinessStatus } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV2 } from "../hooks";
import { DailyDecisionWorkspace } from "./daily-decision-workspace";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";
import { TradingOverviewOrdersPanel } from "./trading-overview-orders-panel";
import { TradingOverviewSignalsPanel } from "./trading-overview-signals-panel";
import { TradingSessionStrip } from "./trading-session-strip";

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

function stringField(value: unknown, fallback: string): string {
	return typeof value === "string" && value.length > 0 ? value : fallback;
}

function stringList(value: unknown): string[] {
	return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function ExecutionScopeForm({ scope }: { readonly scope: TradingExecutionScope }) {
	return (
		<form
			id="trading-execution-scope"
			aria-label="执行范围"
			action="/trading"
			method="get"
			className="grid gap-3 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-3 sm:grid-cols-2 lg:grid-cols-[minmax(12rem,2fr)_minmax(10rem,1fr)_minmax(10rem,1fr)_auto] lg:items-end"
		>
			<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
				<span>策略 ID</span>
				<input
					name="strategy_id"
					required
					defaultValue={scope.strategyId}
					className="min-w-0 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
				/>
			</label>
			<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
				<span>账户 ID</span>
				<input
					name="account_id"
					required
					defaultValue={scope.accountId ?? ""}
					placeholder="必填，不猜测账户"
					className="min-w-0 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
				/>
			</label>
			<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
				<span>信号日期</span>
				<input
					type="date"
					name="trade_date"
					defaultValue={scope.tradeDate ?? ""}
					className="min-w-0 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
				/>
			</label>
			<button
				type="submit"
				className="rounded-(--radius-sm) bg-(--color-accent) px-3 py-2 text-xs font-medium text-(--color-accent-foreground)"
			>
				加载决策
			</button>
		</form>
	);
}

/* ── Page Component ── */

export function TradingPage() {
	const liveMode = !shouldUsePrototypeMocks();
	const executionScope = resolveTradingExecutionScope();
	const {
		data: dailyDecision,
		isLoading,
		isError,
		refetch,
	} = useDailyDecisionV2(undefined, undefined, {
		enabled: liveMode,
	});
	const readinessStatus = stringField(dailyDecision?.readiness.status, "blocked");
	const readiness = mapReadinessStatus(
		readinessStatus === "ready" || readinessStatus === "review" ? readinessStatus : "blocked",
	);
	const reasons = stringList(dailyDecision?.readiness.reason_codes);
	const tradeDate = stringField(dailyDecision?.identity.intended_trade_date, "日期待确认");
	const outcome = stringField(dailyDecision?.run_package.outcome, "missing");
	const decisionBannerProps = !liveMode
		? DECISION_BANNER_PROPS
		: isLoading
			? {
					primary: { label: "Daily Decision", value: "加载中", sub: "正在读取持久化决策包" },
					judgment: { text: "正在核对数据、账户与运行证据。", metrics: [] },
				}
			: isError
				? {
						primary: { label: "Daily Decision", value: "加载失败", sub: "未使用原型数据替代" },
						judgment: {
							text: "真实后端暂时不可用，请重试。交易动作保持关闭。",
							regime: { label: "连接错误", variant: "error" as const },
							metrics: [],
						},
						actions: [{ label: "重试", variant: "secondary" as const, onClick: () => void refetch() }],
					}
				: dailyDecision
					? {
							primary: {
								label: "Daily Decision",
								value: readiness.label,
								sub: tradeDate,
							},
							judgment: {
								text: `${readiness.summary}：${reasons[0] ?? "所有必要证据已齐备"}`,
								regime: {
									label: readiness.label,
									variant: READINESS_BADGE_VARIANT[readiness.tone] ?? "default",
								},
								metrics: [
									{
										label: "Actions",
										value: readinessStatus === "blocked" ? "关闭" : `${dailyDecision.actions.length} 条`,
									},
									{
										label: "Package",
										value: outcome,
									},
									{
										label: "Evidence",
										value: `${reasons.length} 项提示`,
									},
								],
							},
							actions: [],
						}
					: {
							primary: { label: "Daily Decision", value: "暂无决策", sub: "未使用原型数据替代" },
							judgment: { text: "尚未返回可验证的决策包。", metrics: [] },
						};

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
					<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding) md:h-full md:overflow-y-auto">
						{liveMode && <ExecutionScopeForm scope={executionScope} />}
						{liveMode && dailyDecision && <DailyDecisionWorkspace report={dailyDecision} />}
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
