import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ErrorState } from "@/lib/error-boundary";
import type { MarketCalendarStatusQuery } from "./market-view-contracts";

function latestStatusLabel(status: string | null): string {
	if (status === "success") return "成功";
	if (status === "failed") return "失败";
	if (status === null) return "未报告";
	return status;
}

export function MarketCalendarList({ query }: { readonly query: MarketCalendarStatusQuery }) {
	if (query.isLoading) return <LoadingSkeleton variant="table" rows={6} />;
	if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;
	if (!query.data) return null;

	const status = query.data;
	const failed = status.latest_status === "failed";

	return (
		<div data-info-level="l1" data-info-unit="calendar-content" className="flex flex-col gap-4 p-4">
			<ContextSection title="最新摄取" data-info-level="l2" data-info-unit="latest-ingestion">
				<div className="grid gap-3 sm:grid-cols-2">
					<div
						data-info-level="l3"
						data-info-unit="latest-ingested-date"
						className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
					>
						<p className="text-xs text-(--color-foreground-tertiary)">最新成功日期</p>
						<p className="mt-2 font-mono text-base font-semibold">{status.latest_date ?? "未报告"}</p>
					</div>
					<div
						data-info-level="l3"
						data-info-unit="latest-ingestion-status"
						className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
					>
						<p className="text-xs text-(--color-foreground-tertiary)">最新状态</p>
						<p className={`mt-2 font-mono text-base font-semibold ${failed ? "text-(--color-risk-warning)" : ""}`}>
							{latestStatusLabel(status.latest_status)}
						</p>
					</div>
				</div>
			</ContextSection>
			<ContextSection title="目录规模与新鲜度" data-info-level="l2" data-info-unit="catalog-freshness">
				<div className="grid gap-3 sm:grid-cols-2">
					<div
						data-info-level="l3"
						data-info-unit="record-count"
						className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
					>
						<p className="text-xs text-(--color-foreground-tertiary)">记录数</p>
						<p className="mt-2 font-data text-2xl font-semibold">{status.record_count.toLocaleString()}</p>
					</div>
					<div
						data-info-level="l3"
						data-info-unit="catalog-freshness-at"
						className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
					>
						<p className="text-xs text-(--color-foreground-tertiary)">Catalog 新鲜度</p>
						<p className="mt-2 break-all font-mono text-base font-semibold">
							{status.catalog_freshness_at ?? "未报告"}
						</p>
					</div>
				</div>
			</ContextSection>
		</div>
	);
}
