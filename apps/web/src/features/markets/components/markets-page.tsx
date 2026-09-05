import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { ContextBar, ContextBarItem, ContextBarSep } from "@/components/indicator/context-bar";
import { Panel, PanelBody, PanelHeader, RadarLayout, StatusBar } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import type { MarketContext } from "../api/market-evidence";
import { MarketsOverviewOverlay, type MarketsOverviewOverlayId, marketsOverviewActions } from "./market-page-overlays";
import type { MarketCatalogInstrument, MarketCatalogQuery, MarketContextQuery } from "./market-view-contracts";

const CONTEXT_CATEGORIES = new Set(["global", "rates", "fx", "commodity", "macro"]);

function countBy(items: readonly MarketCatalogInstrument[], field: "asset_class" | "exchange") {
	const counts = new Map<string, number>();
	for (const item of items) counts.set(item[field], (counts.get(item[field]) ?? 0) + 1);
	return [...counts.entries()].sort(([left], [right]) => left.localeCompare(right));
}

function statusLabel(status?: MarketContext["status"]): string {
	if (status === "ready") return "Ready";
	if (status === "degraded") return "Degraded";
	if (status === "blocked") return "Blocked";
	return "Loading";
}

function regimeLabel(label?: MarketContext["regime_label"]): string {
	if (label === "risk_on") return "Risk On";
	if (label === "risk_off") return "Risk Off";
	if (label === "balanced") return "Balanced";
	return "No conclusion";
}

function formatMetric(value: number, unit: string): string {
	if (unit === "ratio") return `${(value * 100).toFixed(2)}%`;
	return `${value.toFixed(3)} ${unit}`;
}

function contextSummary(context?: MarketContext): string {
	if (!context) return "正在解析已认证数据产品与 exact source snapshots。";
	if (context.status === "blocked") {
		return `缺少 ${context.missing_inputs.length} 项核心输入，系统不会输出伪完整市场结论。`;
	}
	if (context.status === "degraded") {
		return "结论可用但存在缺失、冲突或不确定项；下游决策应降低置信度。";
	}
	return "结论由版本化公式计算，并保留 driver、影响链与 immutable evidence。";
}

function RegimePanel({ context }: { readonly context: MarketContext }) {
	return (
		<Panel data-info-level="l1" data-info-unit="market-regime">
			<PanelHeader title="Regime" subtitle={context.feature_version} />
			<PanelBody className="p-4">
				<div className="flex items-end justify-between gap-4">
					<div>
						<p className="text-xs uppercase tracking-[0.14em] text-(--color-foreground-tertiary)">Conclusion</p>
						<p className="mt-1 text-2xl font-semibold text-(--color-foreground)">{regimeLabel(context.regime_label)}</p>
					</div>
					<div className="text-right">
						<p className="font-data text-2xl tabular-nums text-(--color-foreground)">
							{context.regime_score === null ? "—" : context.regime_score.toFixed(3)}
						</p>
						<p className="text-xs text-(--color-foreground-tertiary)">normalized score</p>
					</div>
				</div>
				<div className="mt-4 border-t border-(--color-border-subtle) pt-3">
					<p className="text-xs text-(--color-foreground-tertiary)">{contextSummary(context)}</p>
				</div>
			</PanelBody>
		</Panel>
	);
}

function DriverPanel({ context }: { readonly context: MarketContext }) {
	return (
		<Panel data-info-level="l2" data-info-unit="regime-drivers">
			<PanelHeader title="Driver attribution" count={context.drivers.length} />
			<PanelBody className="p-3">
				{context.drivers.length === 0 ? (
					<p className="text-sm text-(--color-foreground-tertiary)">Blocked：没有可归因 driver。</p>
				) : (
					<div className="space-y-1.5">
						{context.drivers.map((driver) => (
							<div
								key={driver.name}
								className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-(--radius-sm) bg-(--color-surface-muted) px-3 py-2"
							>
								<div>
									<p className="font-code text-xs text-(--color-foreground)">{driver.name}</p>
									<p className="text-xs text-(--color-foreground-tertiary)">{driver.category}</p>
								</div>
								<span
									className={
										driver.direction === "supportive"
											? "font-data text-sm text-(--color-accent)"
											: driver.direction === "pressuring"
												? "font-data text-sm text-(--color-foreground-secondary)"
												: "font-data text-sm text-(--color-foreground-secondary)"
									}
								>
									{driver.contribution >= 0 ? "+" : ""}
									{driver.contribution.toFixed(3)}
								</span>
							</div>
						))}
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}

function FactsPanel({ context }: { readonly context: MarketContext }) {
	const metrics = context.metrics.filter((metric) => CONTEXT_CATEGORIES.has(metric.category));
	return (
		<Panel data-info-level="l2" data-info-unit="macro-cross-market">
			<PanelHeader title="Macro & Cross-Market" count={metrics.length} />
			<PanelBody>
				{metrics.length === 0 ? (
					<p className="p-4 text-sm text-(--color-foreground-tertiary)">没有通过 PIT cutoff 的宏观或跨市场事实。</p>
				) : (
					<div className="divide-y divide-(--color-border-subtle)">
						{metrics.map((metric) => (
							<div key={`${metric.category}:${metric.name}`} className="grid grid-cols-[1fr_auto] gap-4 px-4 py-3">
								<div className="min-w-0">
									<p className="font-code text-xs text-(--color-foreground)">{metric.name}</p>
									<p className="mt-0.5 truncate text-xs text-(--color-foreground-tertiary)">{metric.evidence_ref}</p>
								</div>
								<div className="text-right">
									<p className="font-data text-sm tabular-nums text-(--color-foreground)">
										{formatMetric(metric.value, metric.unit)}
									</p>
									<p className="text-xs text-(--color-foreground-tertiary)">
										{metric.category} · {metric.trend} · {metric.freshness}
									</p>
								</div>
							</div>
						))}
					</div>
				)}
			</PanelBody>
		</Panel>
	);
}

function ImpactPanel({ context }: { readonly context: MarketContext }) {
	return (
		<Panel data-info-level="l2" data-info-unit="market-impact-chain">
			<PanelHeader title="Downstream impact chain" count={context.impacts.length} />
			<PanelBody>
				<div className="divide-y divide-(--color-border-subtle)">
					{context.impacts.map((impact) => (
						<div
							key={`${impact.target_domain}:${impact.target}`}
							className="grid grid-cols-[6rem_1fr_auto] gap-3 px-4 py-3 text-sm"
						>
							<span className="font-code text-xs uppercase text-(--color-foreground-tertiary)">
								{impact.target_domain}
							</span>
							<span className="text-(--color-foreground)">{impact.target}</span>
							<span className="text-xs text-(--color-foreground-secondary)">
								{impact.direction} · {impact.rationale_driver}
							</span>
						</div>
					))}
					{context.impacts.length === 0 && (
						<p className="p-4 text-sm text-(--color-foreground-tertiary)">Blocked 状态不生成下游影响。</p>
					)}
				</div>
			</PanelBody>
		</Panel>
	);
}

function EvidenceRail({
	context,
	exchangeCounts,
}: {
	readonly context?: MarketContext | undefined;
	readonly exchangeCounts: [string, number][];
}) {
	return (
		<div className="space-y-3 p-3">
			<Panel data-info-level="l1" data-info-unit="market-context-evidence">
				<PanelHeader title="PIT evidence" subtitle={context?.feature_version} />
				<PanelBody className="p-3">
					{context ? (
						<div className="space-y-3">
							<div>
								<p className="text-xs text-(--color-foreground-tertiary)">as_of / knowledge / publication</p>
								<p className="mt-1 break-all font-code text-xs text-(--color-foreground-secondary)">{context.as_of}</p>
								<p className="break-all font-code text-xs text-(--color-foreground-tertiary)">
									{context.knowledge_cutoff}
								</p>
								<p className="break-all font-code text-xs text-(--color-foreground-tertiary)">
									{context.publication_cutoff}
								</p>
							</div>
							<div className="border-t border-(--color-border-subtle) pt-3">
								<p className="text-xs text-(--color-foreground-tertiary)">Exact source snapshots</p>
								<ul className="mt-1 space-y-1">
									{context.source_snapshot_ids.map((snapshotId) => (
										<li key={snapshotId} className="break-all font-code text-xs text-(--color-foreground-secondary)">
											{snapshotId}
										</li>
									))}
								</ul>
							</div>
							{context.uncertainties.length > 0 && (
								<div className="border-t border-(--color-border-subtle) pt-3">
									<p className="text-xs text-(--color-risk-warning)">{context.uncertainties.join(" · ")}</p>
								</div>
							)}
						</div>
					) : (
						<p className="text-sm text-(--color-foreground-tertiary)">等待 certification evidence。</p>
					)}
				</PanelBody>
			</Panel>
			<Panel data-info-level="l2" data-info-unit="exchange-coverage">
				<PanelHeader title="交易所覆盖" subtitle="metadata identities" />
				<PanelBody className="p-3">
					<div className="space-y-2">
						{exchangeCounts.map(([exchange, count]) => (
							<div
								key={exchange}
								className="flex items-center justify-between rounded-md bg-(--color-surface-muted) px-3 py-2"
							>
								<span className="font-mono text-sm">{exchange}</span>
								<span className="font-data text-sm text-(--color-foreground-tertiary)">{count}</span>
							</div>
						))}
					</div>
				</PanelBody>
			</Panel>
		</div>
	);
}

export function MarketsPage({
	catalogQuery,
	contextQuery,
}: {
	readonly catalogQuery: MarketCatalogQuery;
	readonly contextQuery: MarketContextQuery;
}) {
	const [activeOverlay, setActiveOverlay] = useState<MarketsOverviewOverlayId | null>(null);
	const items = catalogQuery.data?.items ?? [];
	const exchangeCounts = countBy(items, "exchange");
	const assetCounts = countBy(items, "asset_class");
	const context = contextQuery.data;

	return (
		<>
			<RadarLayout
				className="pb-(--height-status-bar)"
				contextBar={
					<ContextBar>
						<ContextBarItem
							label="市场状态"
							value={statusLabel(context?.status)}
							color="muted"
							className={
								context?.status === "ready"
									? "[&>span:last-child]:text-(--color-system-healthy)"
									: context?.status === "blocked"
										? "[&>span:last-child]:text-(--color-system-down)"
										: context?.status === "degraded"
											? "[&>span:last-child]:text-(--color-risk-warning)"
											: undefined
							}
						/>
						<ContextBarSep />
						<ContextBarItem label="Regime" value={regimeLabel(context?.regime_label)} />
						<ContextBarSep />
						<ContextBarItem label="Snapshots" value={context?.source_snapshot_ids.length ?? 0} />
						<ContextBarSep />
						<ContextBarItem
							label="标的覆盖"
							value={catalogQuery.data ? `${catalogQuery.data.total} 个标的` : "加载中"}
						/>
					</ContextBar>
				}
				scopeStrip={
					<div
						data-info-level="l1"
						data-info-unit="market-boundary"
						className="border-l-2 border-l-(--color-accent) bg-(--color-surface-1) px-4 py-2"
					>
						<div className="flex flex-wrap items-center gap-3">
							<div className="min-w-0 flex-1">
								<p className="text-sm font-medium text-(--color-foreground)">市场覆盖</p>
								<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">
									{contextSummary(context)} 当前仍未加载价格、涨跌、资金流或相关性，不会把缺失事实包装成市场解读。
								</p>
							</div>
							<PageActionBar ariaLabel="市场页面操作" actions={marketsOverviewActions} onOpen={setActiveOverlay} />
						</div>
					</div>
				}
				main={
					<div className="flex min-h-[42rem] flex-col gap-(--section-gap) p-(--density-panel-padding)">
						{contextQuery.isLoading && <LoadingSkeleton variant="table" rows={5} />}
						{contextQuery.isError && (
							<Panel data-info-level="l1" data-info-unit="market-context-error">
								<PanelHeader title="MarketContext blocked" />
								<PanelBody className="p-4">
									<p role="alert" className="text-sm text-(--color-system-down)">
										无法解析已认证 exact source snapshots；没有回退到 latest 数据。
									</p>
								</PanelBody>
							</Panel>
						)}
						{context && (
							<>
								<div className="grid gap-(--section-gap) xl:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
									<RegimePanel context={context} />
									<DriverPanel context={context} />
								</div>
								<FactsPanel context={context} />
								<ImpactPanel context={context} />
							</>
						)}
						{catalogQuery.isLoading && <LoadingSkeleton variant="table" rows={5} />}
						{catalogQuery.isError && <ErrorState onRetry={() => void catalogQuery.refetch()} />}
						{catalogQuery.data && (
							<ContextSection
								title="标的身份目录"
								count={catalogQuery.data.total}
								data-info-level="l3"
								data-info-unit="instrument-directory"
							>
								<div className="overflow-x-auto">
									<table className="w-full text-sm">
										<thead className="text-left text-xs text-(--color-foreground-tertiary)">
											<tr>
												{["名称", "代码", "资产类别", "交易所", "状态"].map((label) => (
													<th key={label} className="px-3 py-2 font-medium">
														{label}
													</th>
												))}
											</tr>
										</thead>
										<tbody>
											{items.map((item) => (
												<tr
													key={item.instrument_id}
													data-info-level="l3"
													data-info-unit="instrument-row"
													className="border-t border-(--color-border-subtle)"
												>
													<td className="px-3 py-2 font-medium">{item.name}</td>
													<td className="px-3 py-2 font-mono text-(--color-foreground-secondary)">{item.ticker}</td>
													<td className="px-3 py-2">{item.asset_class}</td>
													<td className="px-3 py-2">{item.exchange}</td>
													<td className="px-3 py-2">{item.is_active ? "活跃" : "非活跃"}</td>
												</tr>
											))}
										</tbody>
									</table>
								</div>
							</ContextSection>
						)}
					</div>
				}
				rightRail={<EvidenceRail context={context} exchangeCounts={exchangeCounts} />}
			/>
			<StatusBar />
			<MarketsOverviewOverlay
				active={activeOverlay}
				assetSummary={assetCounts.map(([name, count]) => `${name} ${count}`).join(" · ")}
				exchangeSummary={exchangeCounts.map(([name, count]) => `${name} ${count}`).join(" · ")}
				onClose={() => setActiveOverlay(null)}
				total={catalogQuery.data?.total ?? 0}
			/>
		</>
	);
}
