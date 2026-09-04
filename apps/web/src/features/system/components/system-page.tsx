import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { OpsConsoleLayout, Panel, PanelBody, PanelHeader, StatusBar } from "@/features/shell";
import type {
	SystemFallbackSummary,
	SystemPromotionReadiness,
	SystemSourceHealthSummary,
} from "../api/system-overview";
import { useSystemOverview } from "../hooks/use-system-overview";
import { type SystemOverlayId, SystemOverlays, systemActions } from "./system-overlays";

const ASSET_VISIBLE_LIMIT = 8;
const REMEDIATION_VISIBLE_LIMIT = 6;

function today(): string {
	return new Date().toISOString().slice(0, 10);
}

function compactHash(value: string): string {
	return value.length > 14 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function formatTimestamp(value: string): string {
	const date = new Date(value);
	return Number.isNaN(date.getTime())
		? value
		: new Intl.DateTimeFormat("zh-CN", {
				month: "2-digit",
				day: "2-digit",
				hour: "2-digit",
				minute: "2-digit",
				hour12: false,
			}).format(date);
}

function errorMessage(error: Error | null): string {
	return error?.message ?? "unknown error";
}

function severityVariant(value: string): "critical" | "warning" | "idle" {
	if (value === "critical" || value === "high") return "critical";
	if (value === "warning" || value === "medium") return "warning";
	return "idle";
}

function SystemHealthStrip({
	assetCount,
	isLoading,
	remediationCount,
	sourceHealth,
}: {
	readonly assetCount: number;
	readonly isLoading: boolean;
	readonly remediationCount: number;
	readonly sourceHealth: SystemSourceHealthSummary | undefined;
}) {
	if (isLoading) {
		return (
			<div className="grid h-9 grid-cols-4 items-center gap-3 px-4" role="status" aria-label="正在加载平台治理摘要">
				{["assets", "attention", "remediation", "failover"].map((key) => (
					<LoadingSkeleton key={key} variant="metric" />
				))}
			</div>
		);
	}

	const metrics = [
		{ label: "Catalog assets", value: assetCount, tone: "text-(--color-accent)" },
		{
			label: "需要关注",
			value: sourceHealth?.attentionRequiredCount ?? 0,
			tone:
				(sourceHealth?.attentionRequiredCount ?? 0) > 0
					? "text-(--color-risk-warning-fg)"
					: "text-(--color-system-healthy-fg)",
		},
		{
			label: "Remediation",
			value: remediationCount,
			tone: remediationCount > 0 ? "text-(--color-risk-critical-fg)" : "text-(--color-system-healthy-fg)",
		},
		{
			label: "自动切源",
			value: sourceHealth?.failoverCount ?? 0,
			tone:
				(sourceHealth?.failoverCount ?? 0) > 0
					? "text-(--color-system-degraded-fg)"
					: "text-(--color-system-healthy-fg)",
		},
	] as const;

	return (
		<div
			className="grid h-9 grid-cols-2 items-center divide-x divide-(--color-border-subtle) px-2 sm:grid-cols-4"
			role="status"
		>
			{metrics.map((metric) => (
				<div key={metric.label} className="flex min-w-0 items-baseline justify-between gap-2 px-3">
					<span className="truncate text-xs text-(--color-foreground-tertiary)">{metric.label}</span>
					<strong className={`font-data text-sm tabular-nums ${metric.tone}`}>{metric.value}</strong>
				</div>
			))}
		</div>
	);
}

function SourceHealthCard({
	data,
	error,
}: {
	readonly data: SystemSourceHealthSummary | undefined;
	readonly error: Error | null;
}) {
	return (
		<Panel data-info-level="l2" data-info-unit="source-health">
			<PanelHeader
				title="Source health"
				count={data?.totalReports}
				actions={
					<StatusBadge
						label={error ? "unavailable" : (data?.attentionRequiredCount ?? 0) > 0 ? "attention" : "healthy"}
						variant={error ? "critical" : (data?.attentionRequiredCount ?? 0) > 0 ? "warning" : "healthy"}
						size="sm"
					/>
				}
			/>
			<PanelBody className="p-3">
				{error ? (
					<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
						{errorMessage(error)}
					</p>
				) : (
					<>
						<div className="grid grid-cols-3 gap-2 text-center">
							{[
								["attention", data?.attentionRequiredCount ?? 0],
								["no fallback", data?.noFallbackSourceCount ?? 0],
								["revoked", data?.revokedPromotionCount ?? 0],
							].map(([label, value]) => (
								<div key={label} className="rounded-(--radius-sm) bg-(--color-surface-strip) p-2">
									<strong className="block font-data text-base">{value}</strong>
									<span className="text-xs text-(--color-foreground-tertiary)">{label}</span>
								</div>
							))}
						</div>
						<ul className="mt-3 space-y-2" aria-label="需要关注的来源健康项">
							{data?.attentionItems.slice(0, 4).map((item) => (
								<li
									key={`${item.datasetId}-${item.selectedSource}`}
									className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2"
								>
									<div className="flex items-center justify-between gap-2">
										<code className="truncate font-data text-xs">{item.datasetId}</code>
										<StatusBadge label={item.severity} variant={severityVariant(item.severity)} size="sm" />
									</div>
									<p className="mt-1 truncate font-data text-xs text-(--color-foreground-tertiary)">
										{item.selectedSource} · {item.reasons.join(" · ") || item.status}
									</p>
								</li>
							))}
						</ul>
					</>
				)}
			</PanelBody>
		</Panel>
	);
}

function FallbackCard({
	data,
	error,
}: {
	readonly data: SystemFallbackSummary | undefined;
	readonly error: Error | null;
}) {
	return (
		<Panel data-info-level="l2" data-info-unit="fallback">
			<PanelHeader title="Fallback control" count={data?.totalPreviews} />
			<PanelBody className="p-3">
				{error ? (
					<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
						{errorMessage(error)}
					</p>
				) : (
					<>
						<p className="text-xs text-(--color-foreground-secondary)">
							需审批 <strong className="font-data text-(--color-foreground)">{data?.approvalRequiredCount ?? 0}</strong>{" "}
							· 可执行{" "}
							<strong className="font-data text-(--color-foreground)">{data?.executionAllowedCount ?? 0}</strong>
						</p>
						<ul className="mt-3 space-y-2">
							{data?.previews.slice(0, 3).map((item) => (
								<li key={item.datasetId} className="rounded-(--radius-sm) bg-(--color-surface-strip) p-2">
									<div className="flex items-center justify-between gap-2">
										<code className="font-data text-xs">{item.datasetId}</code>
										<StatusBadge label={item.policyStatus} variant="idle" size="sm" />
									</div>
									<p className="mt-1 font-data text-xs text-(--color-foreground-tertiary)">
										{item.defaultSource} → {item.recommendedSource ?? item.selectedSource}
									</p>
								</li>
							))}
						</ul>
					</>
				)}
			</PanelBody>
		</Panel>
	);
}

function PromotionCard({
	data,
	error,
}: {
	readonly data: SystemPromotionReadiness | undefined;
	readonly error: Error | null;
}) {
	return (
		<Panel data-info-level="l2" data-info-unit="promotion">
			<PanelHeader title="Promotion readiness" count={data?.datasetCount} />
			<PanelBody className="p-3">
				{error ? (
					<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
						{errorMessage(error)}
					</p>
				) : (
					<>
						<div className="flex items-center justify-between text-xs text-(--color-foreground-secondary)">
							<span>Ready {data?.promotableCount ?? 0}</span>
							<span>Active {data?.activePromotionCount ?? 0}</span>
						</div>
						<ul className="mt-3 space-y-2">
							{data?.datasets.slice(0, 4).map((item) => (
								<li
									key={item.datasetId}
									className="flex items-start justify-between gap-2 border-t border-(--color-border-subtle) pt-2 first:border-0 first:pt-0"
								>
									<div className="min-w-0">
										<code className="font-data text-xs">{item.datasetId}</code>
										<p className="truncate text-xs text-(--color-foreground-tertiary)">
											{item.currentMaturity ?? "maturity unknown"} ·{" "}
											{item.missingCriteria.join(" · ") || "criteria complete"}
										</p>
									</div>
									<StatusBadge
										label={item.status}
										variant={item.status === "ready" ? "healthy" : "warning"}
										size="sm"
									/>
								</li>
							))}
						</ul>
					</>
				)}
			</PanelBody>
		</Panel>
	);
}

export function SystemPage() {
	const [tradeDate, setTradeDate] = useState(today);
	const [activeOverlay, setActiveOverlay] = useState<SystemOverlayId | null>(null);
	const overview = useSystemOverview(tradeDate);
	const assets = overview.assets.data ?? [];
	const overviewQueries = [overview.remediation, overview.sourceHealth, overview.fallback, overview.promotion];
	const isOverviewLoading = overviewQueries.some((query) => query.isLoading);
	const isRefreshing = [overview.assets, ...overviewQueries].some(
		(query) => query.isFetching && query.data !== undefined,
	);
	const focusedTask = overview.remediation.data?.items[0];

	function refresh(): void {
		void overview.assets.refetch();
		for (const query of overviewQueries) void query.refetch();
	}

	return (
		<>
			<OpsConsoleLayout
				className="pb-(--height-status-bar) [&_[data-slot='detail']]:border-l [&_[data-slot='detail']]:border-(--color-border-subtle) [&_[data-slot='detail']]:bg-(--color-surface-1) [&_[data-slot='health']]:border-b [&_[data-slot='health']]:border-(--color-border-subtle) [&_[data-slot='health']]:bg-(--color-surface-strip)"
				health={
					<SystemHealthStrip
						assetCount={assets.length}
						isLoading={overview.assets.isLoading || isOverviewLoading}
						remediationCount={overview.remediation.data?.totalItems ?? 0}
						sourceHealth={overview.sourceHealth.data}
					/>
				}
				main={
					<main className="flex h-full min-h-0 flex-col" aria-label="平台治理总览">
						<div className="flex min-h-11 flex-wrap items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2">
							<div className="min-w-0 flex-1">
								<p className="text-xs font-medium text-(--color-foreground)">Catalog-backed operations</p>
								<p className="truncate text-xs text-(--color-foreground-tertiary)">
									{overview.datasetIds.length} datasets · exact trade date scope
								</p>
							</div>
							<label className="flex items-center gap-2 text-xs text-(--color-foreground-secondary)">
								<span>交易日</span>
								<input
									type="date"
									value={tradeDate}
									onChange={(event) => setTradeDate(event.currentTarget.value)}
									className="h-7 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 font-data text-xs text-(--color-foreground)"
								/>
							</label>
							{isRefreshing && <StatusBadge label="refreshing" variant="idle" size="sm" />}
							<Button type="button" variant="outline" size="xs" onClick={refresh}>
								刷新证据
							</Button>
							<PageActionBar ariaLabel="平台治理操作" actions={systemActions} onOpen={setActiveOverlay} />
						</div>

						<div className="min-h-0 flex-1 overflow-y-auto p-(--density-panel-padding)">
							{overview.assets.isLoading && (
								<div role="status" aria-label="正在加载 Catalog assets">
									<LoadingSkeleton variant="table" rows={6} />
								</div>
							)}
							{overview.assets.isError && (
								<Panel>
									<PanelHeader title="Catalog API 不可用" />
									<PanelBody className="p-4">
										<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
											{errorMessage(overview.assets.error)}
										</p>
										<Button
											className="mt-3"
											type="button"
											variant="outline"
											size="sm"
											onClick={() => void overview.assets.refetch()}
										>
											重试
										</Button>
									</PanelBody>
								</Panel>
							)}
							{overview.assets.isSuccess && assets.length === 0 && (
								<Panel>
									<PanelHeader title="Catalog assets" count={0} />
									<PanelBody className="p-4">
										<p role="status" className="text-sm text-(--color-foreground-secondary)">
											尚无 catalog asset。总览不会用 prototype fixture 伪造 provider、任务或资源指标。
										</p>
									</PanelBody>
								</Panel>
							)}
							{assets.length > 0 && (
								<div className="space-y-(--section-gap)">
									<Panel data-info-level="l1" data-info-unit="catalog-assets">
										<PanelHeader
											title="Catalog assets"
											count={assets.length}
											subtitle="freshness · schema · storage evidence"
										/>
										<PanelBody className="overflow-x-auto">
											<table className="w-full min-w-[44rem] text-left text-xs" aria-label="Catalog assets">
												<thead className="bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
													<tr>
														{["Dataset", "Namespace", "Source", "Freshness", "Rows", "Schema"].map((label) => (
															<th key={label} className="px-3 py-2 font-medium">
																{label}
															</th>
														))}
													</tr>
												</thead>
												<tbody className="divide-y divide-(--color-border-subtle)">
													{assets.slice(0, ASSET_VISIBLE_LIMIT).map((asset) => (
														<tr
															key={`${asset.namespace}:${asset.datasetId}:${asset.source}`}
															className="hover:bg-(--color-interaction-hover-subtle-bg)"
														>
															<td className="px-3 py-2 font-data text-(--color-foreground)">{asset.datasetId}</td>
															<td className="px-3 py-2 text-(--color-foreground-secondary)">{asset.namespace}</td>
															<td className="px-3 py-2">
																<StatusBadge label={asset.source} variant="idle" size="sm" />
															</td>
															<td className="px-3 py-2 font-data text-(--color-foreground-secondary)">
																{formatTimestamp(asset.freshnessAt)}
															</td>
															<td className="px-3 py-2 font-data tabular-nums text-(--color-foreground-secondary)">
																{asset.rowCount?.toLocaleString() ?? "—"}
															</td>
															<td
																className="px-3 py-2 font-data text-(--color-foreground-tertiary)"
																title={asset.schemaHash}
															>
																{compactHash(asset.schemaHash)}
															</td>
														</tr>
													))}
												</tbody>
											</table>
										</PanelBody>
									</Panel>

									<Panel data-info-level="l1" data-info-unit="remediation">
										<PanelHeader title="Remediation backlog" count={overview.remediation.data?.totalItems} />
										<PanelBody className="p-3">
											{overview.remediation.isLoading && <LoadingSkeleton variant="table" rows={3} />}
											{overview.remediation.isError && (
												<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
													{errorMessage(overview.remediation.error)}
												</p>
											)}
											{overview.remediation.data?.items.length === 0 && (
												<p role="status" className="text-sm text-(--color-foreground-secondary)">
													当前交易日没有 remediation item。
												</p>
											)}
											<ul className="grid gap-2 xl:grid-cols-2">
												{overview.remediation.data?.items.slice(0, REMEDIATION_VISIBLE_LIMIT).map((item) => (
													<li
														key={item.itemId}
														className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3"
													>
														<div className="flex items-center justify-between gap-2">
															<code className="truncate font-data text-xs">{item.datasetId}</code>
															<StatusBadge label={item.severity} variant={severityVariant(item.severity)} size="sm" />
														</div>
														<p className="mt-2 truncate text-xs text-(--color-foreground-secondary)">
															{item.source} · {item.reasons.join(" · ") || "reason unavailable"}
														</p>
														<p className="mt-1 truncate font-data text-xs text-(--color-foreground-tertiary)">
															{item.suggestedActions.join(" · ") || "manual review"}
														</p>
													</li>
												))}
											</ul>
										</PanelBody>
									</Panel>
								</div>
							)}
						</div>
					</main>
				}
				detail={
					<aside
						className="flex h-full flex-col gap-(--section-gap) overflow-y-auto p-(--density-panel-padding)"
						aria-label="治理证据"
					>
						<SourceHealthCard data={overview.sourceHealth.data} error={overview.sourceHealth.error} />
						<FallbackCard data={overview.fallback.data} error={overview.fallback.error} />
						<PromotionCard data={overview.promotion.data} error={overview.promotion.error} />
					</aside>
				}
			/>
			<StatusBar spanRail />
			<SystemOverlays
				active={activeOverlay}
				datasetId={focusedTask?.datasetId ?? ""}
				onClose={() => setActiveOverlay(null)}
				onRefresh={refresh}
				reasons={focusedTask?.reasons.join(" · ") ?? ""}
				suggestedActions={focusedTask?.suggestedActions.join(" · ") ?? ""}
				tradeDate={tradeDate}
			/>
		</>
	);
}
