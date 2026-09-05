import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ContextActions } from "@/providers";
import {
	fetchPortfolioComparison,
	type PortfolioComparison,
	type PortfolioComparisonIdentity,
	type PortfolioScenarioPreview,
	previewPortfolioScenario,
} from "../api/portfolio-comparison";
import { tradingKeys } from "../api/query-keys";

interface PortfolioComparisonWorkspaceProps {
	readonly identity?: PortfolioComparisonIdentity | undefined;
}

type PortfolioColumn = PortfolioComparison["model"];

const KIND_LABEL = {
	model: "MODEL",
	paper: "PAPER",
	manual: "MANUAL",
} as const;

const KIND_NOTE = {
	model: "策略目标 · 非账户事实",
	paper: "模拟成交 · 含执行摩擦",
	manual: "用户选择 · 追加式账本",
} as const;

function numberValue(value: string): number {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value: string | number): string {
	return new Intl.NumberFormat("zh-CN", {
		style: "currency",
		currency: "CNY",
		minimumFractionDigits: 2,
	}).format(typeof value === "number" ? value : numberValue(value));
}

function formatPercent(value: string | number): string {
	const numeric = typeof value === "number" ? value : numberValue(value);
	return `${(numeric * 100).toFixed(2)}%`;
}

function formatBps(value: string): string {
	return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(numberValue(value))} bps`;
}

function errorMessage(error: unknown): string {
	return error instanceof Error ? error.message : "未知错误";
}

function portfolioAgentContext(identity: PortfolioComparisonIdentity) {
	const contextId = [
		identity.strategy_id,
		identity.model_portfolio_id,
		identity.paper_account_id,
		identity.manual_account_id,
		identity.paper_session_id,
		identity.as_of,
	].join(":");
	const snapshots = identity.source_snapshot_ids.join(",");
	return {
		contextId,
		objective:
			"调用 portfolio_comparison_evidence 恰好一次并生成可追溯的 PortfolioDiagnostic；" +
			`strategy_id=${identity.strategy_id}，model_portfolio_id=${identity.model_portfolio_id}，` +
			`paper_account_id=${identity.paper_account_id}，manual_account_id=${identity.manual_account_id}，` +
			`paper_session_id=${identity.paper_session_id}，as_of=${identity.as_of}，` +
			`source_snapshot_ids=${snapshots}。只解释工具返回的事实，所有数值必须引用 evidence。`,
	};
}

function PortfolioColumnCard({ portfolio }: { readonly portfolio: PortfolioColumn }) {
	return (
		<section
			data-testid={`portfolio-column-${portfolio.portfolio_kind}`}
			className="min-w-0 overflow-hidden rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1)"
		>
			<header className="border-b border-(--color-border-subtle) px-4 py-3">
				<div className="flex items-start justify-between gap-3">
					<div>
						<p className="font-data text-xs font-semibold tracking-[0.18em] text-(--color-foreground-tertiary)">
							{KIND_LABEL[portfolio.portfolio_kind]}
						</p>
						<p className="mt-1 text-xs text-(--color-foreground-secondary)">{KIND_NOTE[portfolio.portfolio_kind]}</p>
					</div>
					<span className="rounded-full border border-(--color-border-subtle) px-2 py-1 font-data text-xs text-(--color-foreground-tertiary)">
						{portfolio.positions.length} 仓位
					</span>
				</div>
				<p className="mt-4 font-data text-2xl font-semibold tabular-nums text-(--color-foreground)">
					{formatMoney(portfolio.total_value)}
				</p>
				<p
					className="mt-1 truncate font-data text-[11px] text-(--color-foreground-tertiary)"
					title={portfolio.portfolio_id}
				>
					{portfolio.portfolio_id}
				</p>
			</header>
			<div className="grid grid-cols-3 divide-x divide-(--color-border-subtle) border-b border-(--color-border-subtle)">
				{[
					["持仓", formatPercent(portfolio.invested_weight)],
					["现金", formatPercent(portfolio.cash_weight)],
					["待处理", String(portfolio.pending_event_count)],
				].map(([label, value]) => (
					<div key={label} className="px-3 py-2.5">
						<p className="text-xs text-(--color-foreground-tertiary)">{label}</p>
						<p className="mt-1 font-data text-sm tabular-nums text-(--color-foreground)">{value}</p>
					</div>
				))}
			</div>
			<div className="divide-y divide-(--color-border-subtle)">
				{portfolio.positions.map((position) => (
					<div key={position.instrument_id} className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3 text-sm">
						<div className="min-w-0">
							<p className="font-data font-medium text-(--color-foreground)">#{position.instrument_id}</p>
							<p className="mt-0.5 truncate text-[11px] text-(--color-foreground-tertiary)">
								{position.industry ?? "未分类"} · {position.quantity} 股
							</p>
						</div>
						<div className="text-right">
							<p className="font-data tabular-nums text-(--color-foreground)">{formatPercent(position.weight)}</p>
							<p className="mt-0.5 font-data text-[11px] tabular-nums text-(--color-foreground-tertiary)">
								{formatMoney(position.market_value)}
							</p>
						</div>
					</div>
				))}
			</div>
			<footer className="grid grid-cols-3 gap-2 border-t border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-3 text-[11px]">
				<div>
					<p className="text-(--color-foreground-tertiary)">已实现</p>
					<p className="mt-1 font-data tabular-nums text-(--color-foreground)">{formatMoney(portfolio.realized_pnl)}</p>
				</div>
				<div>
					<p className="text-(--color-foreground-tertiary)">未实现</p>
					<p className="mt-1 font-data tabular-nums text-(--color-foreground)">
						{formatMoney(portfolio.unrealized_pnl)}
					</p>
				</div>
				<div>
					<p className="text-(--color-foreground-tertiary)">费用</p>
					<p className="mt-1 font-data tabular-nums text-(--color-foreground)">{formatMoney(portfolio.fees)}</p>
				</div>
			</footer>
		</section>
	);
}

function AttributionPanel({ comparison }: { readonly comparison: PortfolioComparison }) {
	const paper = comparison.model_vs_paper;
	const manual = comparison.model_vs_manual;
	return (
		<Panel>
			<PanelHeader title="Attribution / 差异归因" />
			<PanelBody className="grid gap-4 p-(--density-panel-padding) lg:grid-cols-2">
				<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
					<div className="flex items-center justify-between gap-3">
						<h3 className="text-sm font-semibold text-(--color-foreground)">MODEL → PAPER</h3>
						<span className="font-data text-xs tabular-nums text-(--color-foreground-secondary)">
							总漂移 {formatBps(paper.total_abs_drift_bps)}
						</span>
					</div>
					<div className="mt-3 flex flex-wrap gap-2 text-xs">
						<span className="rounded-full bg-(--color-surface-strip) px-2.5 py-1">
							未成交 {formatBps(paper.attribution.unfilled_bps)}
						</span>
						<span className="rounded-full bg-(--color-surface-strip) px-2.5 py-1">
							滑点 {formatMoney(paper.attribution.slippage_amount)}
						</span>
						<span className="rounded-full bg-(--color-surface-strip) px-2.5 py-1">
							费用 {formatMoney(paper.attribution.fee_amount)}
						</span>
						<span className="rounded-full bg-(--color-surface-strip) px-2.5 py-1">
							风险阻塞 {formatBps(paper.attribution.risk_blocked_bps)}
						</span>
					</div>
				</section>
				<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
					<div className="flex items-center justify-between gap-3">
						<h3 className="text-sm font-semibold text-(--color-foreground)">MODEL → MANUAL</h3>
						<span className="font-data text-xs tabular-nums text-(--color-foreground-secondary)">
							总漂移 {formatBps(manual.total_abs_drift_bps)}
						</span>
					</div>
					<p className="mt-3 text-xs leading-5 text-(--color-foreground-secondary)">
						用户选择 {formatBps(manual.attribution.user_choice_bps)}
						<span className="ml-2 text-(--color-foreground-tertiary)">不归因为系统执行失败</span>
					</p>
				</section>
			</PanelBody>
		</Panel>
	);
}

function ScenarioResult({ preview }: { readonly preview: PortfolioScenarioPreview }) {
	return (
		<div
			className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) p-3"
			aria-live="polite"
		>
			<div className="flex flex-wrap items-center justify-between gap-2">
				<h3 className="text-sm font-semibold text-(--color-foreground)">预演结果</h3>
				<span className="font-data text-xs tabular-nums text-(--color-foreground-secondary)">
					换手率 {formatPercent(preview.risk.turnover)}
				</span>
			</div>
			<div className="mt-3 grid grid-cols-2 gap-3 text-xs">
				<div className="rounded-(--radius-sm) bg-(--color-surface-strip) p-2.5">
					<p className="text-(--color-foreground-tertiary)">压力收益 · 前</p>
					<p className="mt-1 font-data text-base tabular-nums text-(--color-foreground)">
						{formatPercent(preview.risk.before.stressed_return)}
					</p>
				</div>
				<div className="rounded-(--radius-sm) bg-(--color-surface-strip) p-2.5">
					<p className="text-(--color-foreground-tertiary)">压力收益 · 后</p>
					<p className="mt-1 font-data text-base tabular-nums text-(--color-foreground)">
						{formatPercent(preview.risk.after.stressed_return)}
					</p>
				</div>
			</div>
			<div className="mt-3 flex flex-wrap gap-1.5">
				{preview.applied_constraints.map((constraint) => (
					<span
						key={constraint}
						className="rounded-full border border-(--color-border-subtle) px-2 py-1 font-data text-xs"
					>
						{constraint}
					</span>
				))}
			</div>
			<p className="mt-3 border-t border-(--color-border-subtle) pt-2 text-[11px] text-(--color-foreground-tertiary)">
				仅预演，不写入任何账户或 target
			</p>
		</div>
	);
}

function ScenarioPanel({ identity }: { readonly identity: PortfolioComparisonIdentity }) {
	const [baselineKind, setBaselineKind] = useState<"model" | "paper" | "manual">("model");
	const [maxPositionWeight, setMaxPositionWeight] = useState("0.30");
	const [cashReserveWeight, setCashReserveWeight] = useState("0.10");
	const [excludedIds, setExcludedIds] = useState("");
	const [marketShock, setMarketShock] = useState("-0.05");
	const scenario = useMutation({ mutationFn: previewPortfolioScenario });
	const fieldClass =
		"mt-1 h-9 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2.5 font-data text-sm text-(--color-foreground) outline-none focus:border-(--color-interaction-focus-ring)";

	return (
		<Panel>
			<PanelHeader title="Scenario / 仓位预演" />
			<PanelBody className="grid gap-4 p-(--density-panel-padding) xl:grid-cols-[minmax(0,1fr)_20rem]">
				<form
					className="grid grid-cols-2 gap-3 lg:grid-cols-5"
					onSubmit={(event) => {
						event.preventDefault();
						const parsedIds = excludedIds
							.split(/[，,\s]+/u)
							.map((value) => Number(value))
							.filter((value) => Number.isInteger(value) && value > 0);
						scenario.mutate({
							...identity,
							baseline_kind: baselineKind,
							excluded_instrument_ids: parsedIds,
							max_position_weight: maxPositionWeight,
							cash_reserve_weight: cashReserveWeight,
							market_shock: Number(marketShock),
							industry_shocks: {},
						});
					}}
				>
					<label className="text-xs text-(--color-foreground-secondary)">
						预演基线
						<select
							className={fieldClass}
							value={baselineKind}
							onChange={(event) => setBaselineKind(event.target.value as typeof baselineKind)}
						>
							<option value="model">MODEL</option>
							<option value="paper">PAPER</option>
							<option value="manual">MANUAL</option>
						</select>
					</label>
					<label className="text-xs text-(--color-foreground-secondary)">
						单仓上限
						<input
							className={fieldClass}
							inputMode="decimal"
							value={maxPositionWeight}
							onChange={(event) => setMaxPositionWeight(event.target.value)}
						/>
					</label>
					<label className="text-xs text-(--color-foreground-secondary)">
						现金保留
						<input
							className={fieldClass}
							inputMode="decimal"
							value={cashReserveWeight}
							onChange={(event) => setCashReserveWeight(event.target.value)}
						/>
					</label>
					<label className="text-xs text-(--color-foreground-secondary)">
						排除标的
						<input
							className={fieldClass}
							placeholder="600519, 510300"
							value={excludedIds}
							onChange={(event) => setExcludedIds(event.target.value)}
						/>
					</label>
					<label className="text-xs text-(--color-foreground-secondary)">
						市场冲击
						<input
							className={fieldClass}
							inputMode="decimal"
							value={marketShock}
							onChange={(event) => setMarketShock(event.target.value)}
						/>
					</label>
					<div className="col-span-2 flex items-center gap-3 lg:col-span-5">
						<Button type="submit" size="sm" disabled={scenario.isPending}>
							{scenario.isPending ? "计算中…" : "运行只读预演"}
						</Button>
						<span className="text-[11px] text-(--color-foreground-tertiary)">约束与压力由 host 确定性服务计算</span>
					</div>
					{scenario.isError && (
						<p role="alert" className="col-span-2 text-xs text-(--color-risk-critical-fg) lg:col-span-5">
							预演失败：{errorMessage(scenario.error)}
						</p>
					)}
				</form>
				{scenario.data ? (
					<ScenarioResult preview={scenario.data} />
				) : (
					<div className="flex min-h-32 items-center justify-center rounded-(--radius-sm) border border-dashed border-(--color-border-subtle) px-4 text-center text-xs text-(--color-foreground-tertiary)">
						调整约束后运行。结果只读，不生成订单。
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}

export function PortfolioComparisonWorkspace({ identity }: PortfolioComparisonWorkspaceProps = {}) {
	const comparison = useQuery({
		queryKey: identity
			? tradingKeys.portfolioComparison(identity)
			: [...tradingKeys.all, "portfolio-comparison", "identity-missing"],
		queryFn: () => fetchPortfolioComparison(identity as PortfolioComparisonIdentity),
		enabled: Boolean(identity),
	});

	if (!identity) {
		return (
			<div className="p-(--density-panel-padding)">
				<div
					role="alert"
					className="rounded-(--radius-md) border border-(--color-risk-warning-fg) bg-(--color-surface-1) p-4 text-sm"
				>
					<p className="font-semibold text-(--color-foreground)">缺少精确组合身份</p>
					<p className="mt-1 text-(--color-foreground-secondary)">
						必须同时提供 strategy、MODEL、PAPER、MANUAL、session、as_of、cutoff 和 source snapshot；不会回退到 latest。
					</p>
				</div>
			</div>
		);
	}

	if (comparison.isLoading) {
		return <LoadingSkeleton variant="panel" rows={8} />;
	}

	if (comparison.isError) {
		return (
			<div className="p-(--density-panel-padding)">
				<div
					role="alert"
					className="rounded-(--radius-md) border border-(--color-risk-critical-fg) bg-(--color-surface-1) p-4 text-sm"
				>
					<p className="font-semibold text-(--color-foreground)">三组合比较已 fail closed</p>
					<p className="mt-1 text-(--color-foreground-secondary)">{errorMessage(comparison.error)}</p>
					<Button className="mt-3" variant="outline" size="sm" onClick={() => void comparison.refetch()}>
						重试精确快照
					</Button>
				</div>
			</div>
		);
	}

	if (!comparison.data) return null;
	const agentContext = portfolioAgentContext(identity);

	return (
		<div className="min-w-0 bg-(--color-surface-canvas) p-(--density-panel-padding)">
			<header className="mb-4 flex flex-wrap items-end justify-between gap-4">
				<div>
					<p className="font-data text-xs font-semibold tracking-[0.2em] text-(--color-foreground-tertiary)">
						PORTFOLIO OVERVIEW
					</p>
					<h1 className="mt-1 text-xl font-semibold text-(--color-foreground)">MODEL / PAPER / MANUAL</h1>
					<p className="mt-1 text-xs text-(--color-foreground-secondary)">同价、同日、同快照的可解释组合对照</p>
				</div>
				<div className="flex max-w-full flex-col items-end gap-2 text-right text-xs text-(--color-foreground-tertiary)">
					<ContextActions
						contextType="portfolio"
						contextId={agentContext.contextId}
						evidenceLabel="请求组合诊断"
						evidenceObjective={agentContext.objective}
					/>
					<p className="font-data">AS OF {comparison.data.as_of}</p>
					<p className="mt-1 max-w-[34rem] truncate font-data" title={comparison.data.valuation_snapshot_id}>
						{comparison.data.valuation_snapshot_id}
					</p>
					<p className="mt-1 max-w-[34rem] truncate font-data" title={comparison.data.source_snapshot_ids.join(" + ")}>
						{comparison.data.source_snapshot_ids.join(" + ")}
					</p>
				</div>
			</header>
			<div className="grid min-w-0 gap-3 lg:grid-cols-3">
				<PortfolioColumnCard portfolio={comparison.data.model} />
				<PortfolioColumnCard portfolio={comparison.data.paper} />
				<PortfolioColumnCard portfolio={comparison.data.manual} />
			</div>
			<div className="mt-4 grid gap-4">
				<AttributionPanel comparison={comparison.data} />
				<ScenarioPanel identity={identity} />
			</div>
		</div>
	);
}
