import { DecisionBanner } from "@/components/domain/decision-banner";
import { type BadgeVariant, StatusBadge } from "@/components/status";
import { AnalyticalLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";
import { resolveTradingExecutionScope, type TradingExecutionScope } from "../api/execution-scope";
import { mapReadinessStatus } from "../api/mappers";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useDailyDecisionV3 } from "../hooks";
import { DailyDecisionV3Workspace } from "./daily-decision-v3-workspace";
import { DecisionBriefing } from "./decision-briefing";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PortfolioOverviewOrdersPanel } from "./portfolio-overview-orders-panel";
import { PortfolioOverviewSignalsPanel } from "./portfolio-overview-signals-panel";
import { PortfolioSessionStrip } from "./portfolio-session-strip";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";

/* ── Mock Data: Decision Banner ── */

const DECISION_BANNER_PROPS = {
	primary: {
		label: "今日盈亏",
		value: "+¥86,472.50",
		sub: "+0.34% · 总权益 ¥25,432,180 · 较昨日 +¥21,400",
		trend: "up" as const,
	},
	judgment: {
		text: "先复核贵州茅台卖出信号，再决定 2 笔待成交订单是否执行。",
		regime: { label: "震荡市", variant: "warning" as const },
		metrics: [
			{ label: "待处理信号", value: "4" },
			{ label: "待成交订单", value: "2" },
		],
	},
	actions: [
		{ label: "复核信号", variant: "primary" as const },
		{ label: "查看持仓", variant: "secondary" as const },
		{ label: "查看风控", variant: "secondary" as const },
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
			action="/portfolio"
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

function DecisionBriefingUnavailable({
	liveMode,
	isLoading,
	isError,
}: {
	readonly liveMode: boolean;
	readonly isLoading: boolean;
	readonly isError: boolean;
}) {
	const message = isLoading
		? "正在等待 Daily Decision V3，shadow opinion 尚未查询。"
		: isError
			? "Decision Briefing unavailable；V3 readiness 与交易动作保持关闭。"
			: liveMode
				? "尚无可验证的 V3 exact identity，shadow opinion 未查询。"
				: "Agent shadow opinion 独立于 Daily Decision V3；不可用时不改变 readiness、actions 或执行状态。";

	return (
		<Panel data-slot="decision-briefing" aria-label="Decision Briefing" className="h-full">
			<PanelHeader title="Decision Briefing" actions={<StatusBadge label="SHADOW ONLY" variant="warning" />} />
			<PanelBody className="flex items-center justify-between gap-4 p-3 text-xs text-(--color-foreground-secondary)">
				<span>{message}</span>
				<span className="shrink-0 font-data text-(--color-foreground-tertiary)">
					provenance: exact PIT identity · status: unavailable
				</span>
			</PanelBody>
		</Panel>
	);
}

/* ── Page Component ── */

export function PortfolioOverviewPage() {
	const liveMode = !shouldUsePrototypeMocks();
	const executionScope = resolveTradingExecutionScope();
	const {
		data: dailyDecision,
		isLoading,
		isError,
		refetch,
	} = useDailyDecisionV3(undefined, {
		enabled: liveMode,
	});
	const readinessStatus = stringField(dailyDecision?.readiness.status, "blocked");
	const readiness = mapReadinessStatus(
		readinessStatus === "ready" || readinessStatus === "review" ? readinessStatus : "blocked",
	);
	const reasons = stringList(dailyDecision?.readiness.blockingReasons);
	const tradeDate = stringField(dailyDecision?.identity.tradeDate, "日期待确认");
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
										label: "Risk Evidence",
										value: dailyDecision.completeness.status,
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
				className="pb-(--height-status-bar) [--height-analysis-band:var(--height-portfolio-analysis-band)]"
				strip={<PortfolioSessionStrip />}
				banner={
					<div
						className="p-(--density-panel-padding) pb-0 min-[1440px]:h-[130.6875px] max-[1439px]:h-[147.875px] max-[1439px]:px-4 max-[1439px]:pt-0"
						data-info-level="l1"
						data-info-unit="decision-banner"
					>
						<DecisionBanner
							{...decisionBannerProps}
							className="[&_[data-slot='decision-actions']>div]:flex-row [&_[data-slot='decision-actions']>div]:gap-1 max-[1439px]:h-[132px] max-[1439px]:rounded-[8px] max-[1439px]:border max-[1439px]:border-(--color-border-subtle) max-[1439px]:border-l max-[1439px]:bg-(--color-surface-panel-base) max-[1439px]:py-5 max-[1439px]:[&_[data-slot='decision-actions']]:pt-[18px] max-[1439px]:[&_[data-slot='decision-judgment']]:grid max-[1439px]:[&_[data-slot='decision-judgment']]:grid-cols-[auto_1fr] max-[1439px]:[&_[data-slot='decision-judgment']]:gap-x-2 max-[1439px]:[&_[data-slot='decision-judgment']]:gap-y-2 max-[1439px]:[&_[data-slot='decision-metrics']]:col-span-2"
							data-primary-answer={liveMode ? "true" : undefined}
						/>
					</div>
				}
				main={
					<div className="flex flex-col gap-(--section-gap) p-(--density-panel-padding) md:h-full md:overflow-y-auto">
						{liveMode && <ExecutionScopeForm scope={executionScope} />}
						{liveMode && dailyDecision && <DailyDecisionV3Workspace decision={dailyDecision} />}
						{!liveMode && <EquityPnlBlock />}
						<PositionsSummary />
						<RiskAlertsBlock />
						<PortfolioOverviewOrdersPanel />
					</div>
				}
				activity={<PortfolioOverviewSignalsPanel />}
				analysis={
					<div className="h-full overflow-y-auto p-(--density-panel-padding) pt-0">
						{liveMode && dailyDecision ? (
							<DecisionBriefing decision={dailyDecision} />
						) : (
							<DecisionBriefingUnavailable liveMode={liveMode} isLoading={isLoading} isError={isError} />
						)}
					</div>
				}
			/>
			<StatusBar reserveRightRail />
		</>
	);
}
