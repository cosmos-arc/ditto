import { useState } from "react";
import { ApiError } from "@/api";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useStrategyActive, useStrategyVersion, useStrategyVersions } from "../hooks";
import type { StrategyGovernanceActionsRenderer } from "./governance-actions";

export interface StrategyVersionsViewProps {
	readonly id: string;
	readonly renderGovernanceActions: StrategyGovernanceActionsRenderer;
}

export function StrategyVersionsView({ id, renderGovernanceActions }: StrategyVersionsViewProps) {
	const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
	const { data, isLoading, refetch } = useStrategyVersions(id);
	const detail = useStrategyVersion(id, selectedVersion);
	const active = useStrategyActive(id);
	const pointerRevision = active.data?.pointer_revision ?? null;
	const currentActiveVersion = active.data?.active_version ?? null;
	const versions = data ?? [];

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={5} />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{versions.length > 0 && (
				<div className="flex flex-col gap-(--section-gap) p-4">
					<ContextSection title="版本历史" count={versions.length}>
						<div className="space-y-1">
							{versions.map((ver) => (
								<div
									key={ver.version}
									className="flex items-center justify-between rounded-(--radius-sm) px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex flex-col gap-1">
										<div className="flex items-center gap-3">
											<span className="font-medium">v{ver.version}</span>
											<span className="text-(--color-foreground-tertiary)">{ver.reviewOutcome}</span>
										</div>
										{renderGovernanceActions({
											strategyId: id,
											version: ver,
											expectedPointerRevision: pointerRevision,
											currentActiveVersion,
										})}
									</div>
									<div className="flex items-center gap-3">
										<span className="text-xs text-(--color-foreground-tertiary)">
											{new Date(ver.createdAt).toLocaleDateString("zh-CN")}
										</span>
										<button
											type="button"
											aria-label={`查看 v${ver.version} canonical 版本`}
											onClick={() => setSelectedVersion(ver.version)}
											className="rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-1 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
										>
											查看
										</button>
									</div>
								</div>
							))}
						</div>
					</ContextSection>
					{selectedVersion !== null && (
						<ContextSection title="Canonical Spec">
							{detail.isLoading ? (
								<LoadingSkeleton variant="panel" />
							) : detail.error ? (
								<div className="flex flex-col gap-2 p-(--density-panel-padding) text-sm text-(--color-led-danger)">
									<p>
										{detail.error instanceof ApiError
											? `${detail.error.status} ${detail.error.errorCode ?? "VERSION_DETAIL_ERROR"}: ${detail.error.message}`
											: detail.error.message}
									</p>
									<button type="button" className="self-start underline" onClick={() => void detail.refetch()}>
										重试版本详情
									</button>
								</div>
							) : detail.data ? (
								<div className="flex flex-col gap-2 p-(--density-panel-padding)">
									<div className="grid gap-1 text-xs text-(--color-foreground-tertiary) sm:grid-cols-3">
										<span>v{detail.data.version}</span>
										<span>{detail.data.state}</span>
										<span className="font-data break-all">{detail.data.specHash}</span>
									</div>
									<pre className="max-h-80 overflow-auto rounded-(--radius-sm) bg-(--color-surface-muted) p-(--density-panel-padding) text-xs">
										<code>{JSON.stringify(detail.data.canonicalSpec, null, 2)}</code>
									</pre>
								</div>
							) : null}
						</ContextSection>
					)}
				</div>
			)}
		</DittoErrorBoundary>
	);
}
