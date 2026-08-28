import { useMemo, useState } from "react";
import { StatusBadge } from "@/components/status";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { useDataProductOperations } from "../hooks";
import { DataProductGovernanceActions } from "./data-product-governance-actions";

interface DataProductOperationsProps {
	readonly datasetId: string;
	readonly initialTradeDate?: string;
}

const REMEDIATION_PAGE_SIZE = 5;

function today(): string {
	return new Date().toISOString().slice(0, 10);
}

function errorMessage(error: Error | null): string {
	return error?.message ?? "unknown error";
}

function CodeList({ values }: { readonly values: readonly string[] }) {
	if (values.length === 0) return <span className="text-(--color-foreground-tertiary)">none</span>;
	return (
		<ul className="flex flex-wrap gap-1">
			{values.map((value) => (
				<li key={value}>
					<code className="rounded-(--radius-xs) bg-(--color-surface-strip) px-1.5 py-0.5 font-data text-xs">
						{value}
					</code>
				</li>
			))}
		</ul>
	);
}

export function DataProductOperations({ datasetId, initialTradeDate = today() }: DataProductOperationsProps) {
	const [tradeDate, setTradeDate] = useState(initialTradeDate);
	const scopeIdentity = `${datasetId}:${tradeDate}`;
	const [remediationSelection, setRemediationSelection] = useState({ itemId: "", page: 0, scopeIdentity });
	const selectedRemediationItemId =
		remediationSelection.scopeIdentity === scopeIdentity ? remediationSelection.itemId : "";
	const remediationPage = remediationSelection.scopeIdentity === scopeIdentity ? remediationSelection.page : 0;
	const scope = useMemo(() => ({ datasetId, tradeDate }), [datasetId, tradeDate]);
	const queries = useDataProductOperations(scope, selectedRemediationItemId);
	const queryEntries = Object.entries(queries);
	const errors = queryEntries
		.filter((entry) => entry[1].isError)
		.map(([name, query]) => `${name}: ${errorMessage(query.error)}`);
	const isInitialLoading = queryEntries.every((entry) => entry[1].isLoading);
	const isStale = queryEntries.some((entry) => entry[1].isPlaceholderData);
	const successfulProjectionCount = queryEntries.filter((entry) => entry[1].data !== undefined).length;
	const allUnavailable = errors.length > 0 && successfulProjectionCount === 0;
	const sourceHealth = queries.sourceHealth.data;
	const fallbackPreview = queries.fallbackPreview.data;
	const activeFallback = queries.fallbackPolicies.data?.find((policy) => policy.status === "active");
	const promotion = queries.promotion.data;
	const remediationDetail = queries.remediationDetail.data;
	const remediationItems = queries.remediation.data?.items ?? [];
	const remediationPageCount = Math.max(1, Math.ceil(remediationItems.length / REMEDIATION_PAGE_SIZE));
	const currentRemediationPage = Math.min(remediationPage, remediationPageCount - 1);
	const visibleRemediationItems = remediationItems.slice(
		currentRemediationPage * REMEDIATION_PAGE_SIZE,
		(currentRemediationPage + 1) * REMEDIATION_PAGE_SIZE,
	);
	const effectiveRemediationItemId =
		remediationItems.find((item) => item.itemId === selectedRemediationItemId)?.itemId ??
		remediationItems[0]?.itemId ??
		"";
	const isEmpty =
		queries.remediation.data?.totalItems === 0 &&
		(queries.fallbackPolicies.data?.length ?? 0) === 0 &&
		promotion === null;

	return (
		<Panel data-slot="data-product-operations">
			<PanelHeader
				title="运营治理"
				subtitle={`${datasetId} · ${tradeDate}`}
				actions={
					errors.length > 0 ? (
						<StatusBadge
							label={allUnavailable ? "error" : "partial"}
							variant={allUnavailable ? "critical" : "warning"}
						/>
					) : isStale ? (
						<StatusBadge label="stale" variant="warning" />
					) : undefined
				}
			/>
			<PanelBody className="flex flex-col gap-4 p-3">
				<label className="flex max-w-56 flex-col gap-1 text-xs text-(--color-foreground-secondary)">
					<span>治理交易日</span>
					<input
						type="date"
						value={tradeDate}
						onChange={(event) => setTradeDate(event.currentTarget.value)}
						className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground)"
					/>
				</label>

				{isInitialLoading && <div role="status">正在读取运营投影…</div>}
				{isEmpty && (
					<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3" role="status">
						<p className="text-sm font-medium">运营投影为空</p>
						<p className="mt-1 text-xs text-(--color-foreground-secondary)">
							当前数据产品与交易日没有修复、fallback 或晋级治理记录。
						</p>
					</div>
				)}
				{errors.length > 0 && (
					<div
						role="status"
						className="rounded-(--radius-sm) border border-(--color-risk-warning-fg) bg-(--color-risk-warning-bg) p-3"
					>
						<p className="text-sm font-medium text-(--color-risk-warning-fg)">
							{allUnavailable ? "运营治理不可用" : "部分运营投影不可用"}
						</p>
						<ul className="mt-1 space-y-1 font-data text-xs text-(--color-foreground-secondary)">
							{errors.map((error) => (
								<li key={error}>{error}</li>
							))}
						</ul>
					</div>
				)}

				<div className="grid gap-3 lg:grid-cols-2">
					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3" aria-label="修复待办">
						<div className="flex items-center justify-between gap-2">
							<h3 className="text-sm font-medium">Remediation backlog</h3>
							<StatusBadge label={`${queries.remediation.data?.totalItems ?? 0} items`} variant="idle" size="sm" />
						</div>
						{queries.remediation.data?.items.length === 0 && (
							<p className="mt-3 text-sm text-(--color-foreground-secondary)">remediation empty</p>
						)}
						<ul className="mt-3 space-y-2">
							{visibleRemediationItems.map((item) => (
								<li key={item.itemId}>
									<button
										type="button"
										aria-pressed={item.itemId === effectiveRemediationItemId}
										onClick={() =>
											setRemediationSelection({ itemId: item.itemId, page: currentRemediationPage, scopeIdentity })
										}
										className="w-full rounded-(--radius-xs) bg-(--color-surface-1) p-2 text-left aria-pressed:ring-1 aria-pressed:ring-(--color-accent)"
									>
										<div className="flex items-center justify-between gap-2">
											<code className="font-data text-xs">{item.itemId}</code>
											<StatusBadge label={item.severity} variant="warning" size="sm" />
										</div>
										<p className="mt-1 text-xs text-(--color-foreground-secondary)">
											{item.source} · {item.suggestedActions.join(" · ") || "manual review"}
										</p>
									</button>
								</li>
							))}
						</ul>
						{remediationItems.length > REMEDIATION_PAGE_SIZE && (
							<nav className="mt-3 flex items-center justify-between gap-2 text-xs" aria-label="Remediation 分页">
								<button
									type="button"
									disabled={currentRemediationPage === 0}
									onClick={() =>
										setRemediationSelection({
											itemId: selectedRemediationItemId,
											page: Math.max(0, currentRemediationPage - 1),
											scopeIdentity,
										})
									}
									className="rounded-(--radius-xs) border border-(--color-border-subtle) px-2 py-1 disabled:opacity-40"
								>
									上一页 remediation
								</button>
								<span>
									第 {currentRemediationPage + 1} / {remediationPageCount} 页
								</span>
								<button
									type="button"
									disabled={currentRemediationPage >= remediationPageCount - 1}
									onClick={() =>
										setRemediationSelection({
											itemId: selectedRemediationItemId,
											page: Math.min(remediationPageCount - 1, currentRemediationPage + 1),
											scopeIdentity,
										})
									}
									className="rounded-(--radius-xs) border border-(--color-border-subtle) px-2 py-1 disabled:opacity-40"
								>
									下一页 remediation
								</button>
							</nav>
						)}
						{remediationDetail && (
							<div className="mt-3 border-t border-(--color-border-subtle) pt-3 text-xs text-(--color-foreground-secondary)">
								<p>{remediationDetail.summary}</p>
								<ul className="mt-2 space-y-1" aria-label="修复证据要求">
									{remediationDetail.evidenceRequirements.map((requirement) => (
										<li key={requirement.requirementId}>
											<code className="font-data">{requirement.requirementId}</code> · {requirement.status} ·{" "}
											{requirement.description}
										</li>
									))}
								</ul>
							</div>
						)}
					</section>

					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3" aria-label="来源健康">
						<div className="flex items-center justify-between gap-2">
							<h3 className="text-sm font-medium">Source health</h3>
							<StatusBadge
								label={sourceHealth?.failoverFromDefault ? "source degraded" : (sourceHealth?.status ?? "unavailable")}
								variant={sourceHealth?.failoverFromDefault ? "warning" : "healthy"}
								size="sm"
							/>
						</div>
						<p className="mt-3 font-data text-sm">
							{sourceHealth?.defaultSource ?? "—"} → {sourceHealth?.selectedSource ?? "—"}
						</p>
						<div className="mt-2">
							<CodeList values={sourceHealth?.blockers ?? []} />
						</div>
						<ul className="mt-3 space-y-1 text-xs text-(--color-foreground-secondary)" aria-label="来源健康证据">
							{sourceHealth?.sources.map((source) => (
								<li key={source.source}>
									<code className="font-data">{source.source}</code> · {source.freshnessStatus} ·{" "}
									{source.freshnessAt ?? "no freshness timestamp"}
								</li>
							))}
						</ul>
						<div className="mt-2">
							<CodeList
								values={
									queries.sourceHealthSummary.data?.attentionReasons.map((item) => `${item.reason}:${item.count}`) ?? []
								}
							/>
						</div>
					</section>

					<section
						className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3"
						aria-label="来源回退策略"
					>
						<div className="flex items-center justify-between gap-2">
							<h3 className="text-sm font-medium">Source fallback</h3>
							<StatusBadge
								label={activeFallback ? "fallback active" : (fallbackPreview?.policyStatus ?? "unavailable")}
								variant={activeFallback ? "warning" : "idle"}
								size="sm"
							/>
						</div>
						<p className="mt-3 font-data text-sm">
							{activeFallback?.policyId ?? "preview"} · {fallbackPreview?.defaultSource ?? "—"} →{" "}
							{fallbackPreview?.selectedSource ?? "—"}
						</p>
						<p className="mt-1 text-xs text-(--color-foreground-secondary)">
							approval {fallbackPreview?.approvalRequired ? "required" : "not required"} · execution{" "}
							{fallbackPreview?.executionAllowed ? "allowed" : "blocked"}
						</p>
						<div className="mt-2">
							<CodeList
								values={[...(fallbackPreview?.reasonCodes ?? []), ...(fallbackPreview?.recommendedActions ?? [])]}
							/>
						</div>
						{activeFallback && (
							<p className="mt-2 break-all font-data text-xs text-(--color-foreground-tertiary)">
								authority {activeFallback.authorityHash}
							</p>
						)}
					</section>

					<section className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3" aria-label="晋级准备度">
						<div className="flex items-center justify-between gap-2">
							<h3 className="text-sm font-medium">Promotion readiness</h3>
							<StatusBadge
								label={promotion?.status === "blocked" ? "promotion blocked" : (promotion?.status ?? "unavailable")}
								variant={promotion?.status === "blocked" ? "critical" : "healthy"}
								size="sm"
							/>
						</div>
						<div className="mt-3">
							<CodeList values={[...(promotion?.missingCriteria ?? []), ...(promotion?.rejectedCriteria ?? [])]} />
						</div>
						<p className="mt-2 text-xs text-(--color-foreground-secondary)">
							{queries.promotionHistory.data?.length ?? 0} history events · maturity {promotion?.currentMaturity ?? "—"}
						</p>
						<ul className="mt-2 space-y-1 text-xs text-(--color-foreground-secondary)" aria-label="晋级证据历史">
							{queries.promotionHistory.data?.map((event) => (
								<li key={`${event.actionAt ?? "unknown"}-${event.action}-${event.actor}-${event.nextMaturity}`}>
									{event.action} · {event.actor} · {event.evidenceUri ?? "no evidence URI"}
								</li>
							))}
						</ul>
					</section>
				</div>

				<DataProductGovernanceActions
					approvals={queries.approvals.data ?? []}
					datasetId={datasetId}
					fallbackPolicies={queries.fallbackPolicies.data ?? []}
					fallbackPreview={fallbackPreview}
					promotion={promotion}
					remediationDetail={queries.remediationDetail.data}
					tradeDate={tradeDate}
				/>
			</PanelBody>
		</Panel>
	);
}
