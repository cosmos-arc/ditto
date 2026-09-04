import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { DailyDecisionV3ViewModel } from "../types/daily-decision-v3";

function percent(value: number | null, signed = false): string {
	if (value == null) return "—";
	const prefix = signed && value > 0 ? "+" : "";
	return `${prefix}${(value * 100).toFixed(2)}%`;
}

function valueOrDash(value: string | null): string {
	return value?.trim() ? value : "—";
}

function quantity(value: number | null): string {
	return value == null ? "—" : value.toLocaleString("en-US");
}

function Readiness({ decision }: { readonly decision: DailyDecisionV3ViewModel }) {
	const labels = {
		ready: "可执行",
		review: "需人工复核",
		blocked: "已阻塞",
	} as const;
	const variants = {
		ready: "healthy",
		review: "warning",
		blocked: "critical",
	} as const;

	return (
		<Panel data-slot="decision-readiness">
			<PanelHeader
				title="决策就绪度"
				actions={
					<StatusBadge label={labels[decision.readiness.status]} variant={variants[decision.readiness.status]} />
				}
			/>
			<PanelBody className="p-3">
				{decision.readiness.status === "blocked" ? (
					<div
						role="alert"
						className="rounded-(--radius-sm) border border-(--color-risk-critical-fg) bg-(--color-risk-critical-bg) p-3"
					>
						<p className="text-sm font-semibold text-(--color-risk-critical-fg)">交易动作关闭</p>
						<p className="mt-1 text-xs text-(--color-foreground-secondary)">
							修复全部阻塞证据并重新获取决策后，才能恢复交易复核。
						</p>
						<ul className="mt-2 flex flex-wrap gap-2">
							{decision.readiness.blockingReasons.map((reason) => (
								<li key={reason}>
									<code className="font-data text-xs text-(--color-risk-critical-fg)">{reason}</code>
								</li>
							))}
						</ul>
					</div>
				) : (
					<div className="flex flex-wrap items-center justify-between gap-3">
						<p className="text-sm text-(--color-foreground-secondary)">
							{decision.readiness.status === "ready"
								? "风险与 PIT 证据完整，可进入人工交易复核。"
								: "存在需要人工判断的证据，保持复核门禁。"}
						</p>
						<Button size="sm">进入交易复核</Button>
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}

export function DailyDecisionV3Workspace({ decision }: { readonly decision: DailyDecisionV3ViewModel }) {
	const isStale = decision.data.freshness === "stale";

	return (
		<section data-slot="decision-cockpit" className="flex flex-col gap-(--section-gap)">
			<div className="grid gap-(--section-gap) lg:grid-cols-[minmax(0,1.2fr)_minmax(16rem,0.8fr)]">
				<Readiness decision={decision} />
				<Panel>
					<PanelHeader
						title="风险头条"
						actions={isStale ? <StatusBadge label="数据已过期" variant="warning" /> : undefined}
					/>
					<PanelBody className="grid grid-cols-2 gap-3 p-3">
						<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
							<p className="text-xs text-(--color-foreground-tertiary)">Historical ES99</p>
							<p className="mt-1 font-data text-xl tabular-nums text-(--color-foreground)">
								{percent(decision.tailRisk.historicalEs99)}
							</p>
						</div>
						<div className="rounded-(--radius-sm) bg-(--color-surface-1) p-3">
							<p className="text-xs text-(--color-foreground-tertiary)">建议交易日</p>
							<p className="mt-1 font-data text-sm text-(--color-foreground)">
								{valueOrDash(decision.identity.tradeDate)}
							</p>
						</div>
					</PanelBody>
				</Panel>
			</div>

			{decision.completeness.status === "partial" && (
				<div
					role="status"
					className="rounded-(--radius-sm) border border-(--color-risk-warning-fg) bg-(--color-risk-warning-bg) px-3 py-2"
				>
					<p className="text-sm font-medium text-(--color-risk-warning-fg)">部分风险证据不可用</p>
					<div className="mt-1 flex flex-wrap gap-2">
						{decision.completeness.issues.map((issue) => (
							<code key={issue} className="font-data text-xs text-(--color-foreground-secondary)">
								{issue}
							</code>
						))}
					</div>
				</div>
			)}

			<Panel data-slot="decision-actions">
				<PanelHeader title="建议交易动作" count={decision.actions.length} />
				<PanelBody>
					<div className="overflow-x-auto">
						<table className="w-full min-w-240 text-left text-sm">
							<thead className="bg-(--color-surface-strip) text-xs text-(--color-foreground-tertiary)">
								<tr>
									<th className="px-3 py-2 font-medium">标的</th>
									<th className="px-3 py-2 font-medium">方向</th>
									<th className="px-3 py-2 font-medium">当前权重</th>
									<th className="px-3 py-2 font-medium">目标权重</th>
									<th className="px-3 py-2 font-medium">变化</th>
									<th className="px-3 py-2 font-medium">sizing readiness</th>
									<th className="px-3 py-2 font-medium">risk flags</th>
									<th className="px-3 py-2 font-medium">execution progress</th>
								</tr>
							</thead>
							<tbody className="divide-y divide-(--color-border-subtle)">
								{decision.actions.map((action) => (
									<tr key={action.intentId}>
										<td className="px-3 py-2 font-data text-(--color-foreground)">#{action.instrumentId}</td>
										<td className="px-3 py-2 text-(--color-foreground-secondary)">{action.direction ?? "—"}</td>
										<td className="px-3 py-2 font-data tabular-nums">{percent(action.currentWeight)}</td>
										<td className="px-3 py-2 font-data tabular-nums">{percent(action.targetWeight)}</td>
										<td className="px-3 py-2 font-data tabular-nums">{percent(action.deltaWeight, true)}</td>
										<td className="px-3 py-2 font-data text-xs">{action.sizingReadiness ?? "—"}</td>
										<td className="px-3 py-2">
											{action.riskFlags.length === 0 ? (
												<span className="text-xs text-(--color-foreground-tertiary)">无</span>
											) : (
												<ul className="flex flex-wrap gap-1" aria-label={`#${action.instrumentId} risk flags`}>
													{action.riskFlags.map((flag) => (
														<li key={flag}>
															<code className="rounded-(--radius-xs) bg-(--color-risk-warning-bg) px-1.5 py-0.5 font-data text-xs text-(--color-risk-warning-fg)">
																{flag}
															</code>
														</li>
													))}
												</ul>
											)}
										</td>
										<td className="px-3 py-2 text-xs">
											<p className="font-data tabular-nums text-(--color-foreground)">
												{quantity(action.filledQuantity)} / {quantity(action.suggestedQuantity)}
											</p>
											<p className="mt-0.5 font-data text-(--color-foreground-tertiary)">
												剩余 {quantity(action.remainingQuantity)} · {action.executionStatus ?? "—"}
											</p>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				</PanelBody>
			</Panel>

			<Panel>
				<PanelHeader title="决策身份与快照" />
				<PanelBody className="grid gap-3 p-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
					<div>
						<p className="text-(--color-foreground-tertiary)">策略 / 账户</p>
						<p className="mt-1 font-data text-(--color-foreground)">
							{decision.identity.strategyId} / {valueOrDash(decision.identity.accountId)}
						</p>
					</div>
					<div>
						<p className="text-(--color-foreground-tertiary)">freshness / DQ</p>
						<p className="mt-1 font-data text-(--color-foreground)">
							{valueOrDash(decision.data.freshness)} / {valueOrDash(decision.data.qualityState)}
						</p>
					</div>
					{Object.entries(decision.data.snapshotIds).map(([dataset, snapshotId]) => (
						<div key={dataset}>
							<p className="text-(--color-foreground-tertiary)">{dataset} snapshot</p>
							<p className="mt-1 break-all font-data text-(--color-foreground)">{snapshotId}</p>
						</div>
					))}
				</PanelBody>
			</Panel>
		</section>
	);
}
