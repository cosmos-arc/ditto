import { StatusBadge } from "@/components/status";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DailyDecisionV3ViewModel } from "../types/daily-decision-v3";

function percent(value: number | null, signed = false): string {
	if (value == null) return "—";
	const prefix = signed && value > 0 ? "+" : "";
	return `${prefix}${(value * 100).toFixed(2)}%`;
}

function money(value: number | null): string {
	return value == null
		? "—"
		: `¥${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function shareOfTotal(value: number | null, total: number | null): string {
	return value == null || total == null || total === 0 ? "—" : percent(value / total);
}

function blockingReasonsHref(decision: DailyDecisionV3ViewModel): string {
	const search = new URLSearchParams();
	search.set("strategy_id", decision.identity.strategyId);
	if (decision.identity.accountId) search.set("account_id", decision.identity.accountId);
	if (decision.identity.tradeDate) search.set("trade_date", decision.identity.tradeDate);
	return `/portfolio/model?${search.toString()}`;
}

export function PortfolioConstructionEvidence({ decision }: { readonly decision: DailyDecisionV3ViewModel }) {
	const evidence = decision.portfolioConstruction;
	const failed = evidence.status === "failed" || evidence.failureCode != null;

	return (
		<Panel data-slot="portfolio-construction">
			<PanelHeader
				title="组合构建证据"
				actions={
					<StatusBadge label={failed ? "求解失败" : evidence.status} variant={failed ? "critical" : "healthy"} />
				}
			/>
			<PanelBody className="flex flex-col gap-4 p-3">
				{failed && (
					<div
						role="alert"
						className="flex flex-wrap items-center justify-between gap-3 rounded-(--radius-sm) border border-(--color-risk-critical-fg) bg-(--color-risk-critical-bg) p-3"
					>
						<div>
							<p className="text-sm font-medium text-(--color-risk-critical-fg)">组合求解未产生可用目标</p>
							<code className="font-data text-xs text-(--color-foreground-secondary)">
								{evidence.failureCode ?? evidence.solverStatus ?? "SOLVER_FAILED"}
							</code>
						</div>
						<a
							className="text-xs font-medium text-(--color-accent) hover:underline"
							href={blockingReasonsHref(decision)}
						>
							查看阻塞原因
						</a>
					</div>
				)}

				<dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">总敞口</dt>
						<dd className="mt-1 font-data text-sm tabular-nums text-(--color-foreground)">
							{money(decision.account.exposure)} ·{" "}
							{shareOfTotal(decision.account.exposure, decision.account.totalValue)}
						</dd>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">现金基线</dt>
						<dd className="mt-1 font-data text-sm tabular-nums text-(--color-foreground)">
							{money(decision.account.cashAvailable)} ·{" "}
							{shareOfTotal(decision.account.cashAvailable, decision.account.totalValue)}
						</dd>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">组合总值</dt>
						<dd className="mt-1 font-data text-sm tabular-nums text-(--color-foreground)">
							{money(decision.account.totalValue)}
						</dd>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">baseline / as of</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">
							{decision.account.baselineId ?? "—"} / {decision.account.asOf ?? "—"}
						</dd>
					</div>
				</dl>

				<dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">solver</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">{evidence.solver ?? "—"}</dd>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">version / status</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">
							{evidence.solverVersion ?? "—"} / {evidence.solverStatus ?? "—"}
						</dd>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">mode / duration</dt>
						<dd className="mt-1 font-data text-sm text-(--color-foreground)">
							{evidence.mode ?? "—"} / {evidence.durationMs == null ? "—" : `${evidence.durationMs} ms`}
						</dd>
					</div>
					<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
						<dt className="text-(--color-foreground-tertiary)">policy digest</dt>
						<dd className="mt-1 break-all font-data text-sm text-(--color-foreground)">
							{evidence.policyDigest ?? "—"}
						</dd>
					</div>
				</dl>

				<div className="text-xs text-(--color-foreground-tertiary)">
					<p>当前契约仅提供 policy digest</p>
					<p className="mt-1">不推测未返回的约束明细。</p>
				</div>

				<div className="overflow-x-auto">
					<table className="w-full min-w-140 text-left text-sm">
						<thead className="bg-(--color-surface-strip) text-xs text-(--color-foreground-tertiary)">
							<tr>
								<th className="px-3 py-2 font-medium">标的</th>
								<th className="px-3 py-2 font-medium">当前</th>
								<th className="px-3 py-2 font-medium">目标</th>
								<th className="px-3 py-2 font-medium">变化</th>
								<th className="px-3 py-2 font-medium">sizing</th>
							</tr>
						</thead>
						<tbody className="divide-y divide-(--color-border-subtle)">
							{decision.actions.map((action) => (
								<tr key={action.intentId}>
									<td className="px-3 py-2 font-data">#{action.instrumentId}</td>
									<td className="px-3 py-2 font-data tabular-nums">{percent(action.currentWeight)}</td>
									<td className="px-3 py-2 font-data tabular-nums">{percent(action.targetWeight)}</td>
									<td className="px-3 py-2 font-data tabular-nums">{percent(action.deltaWeight, true)}</td>
									<td className="px-3 py-2 font-data text-xs">{action.sizingReadiness ?? "—"}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</PanelBody>
		</Panel>
	);
}
