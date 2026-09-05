import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ErrorState } from "@/lib/error-boundary";
import type { MarketCalendarCoverageQuery } from "./market-view-contracts";

export function MarketCalendarList({ query }: { readonly query: MarketCalendarCoverageQuery }) {
	if (query.isLoading) return <LoadingSkeleton variant="table" rows={6} />;
	if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;
	if (!query.data) return null;

	const coverage = query.data;
	const milestones = [
		["原始覆盖起点", coverage.raw_from ?? "未报告"],
		["完整覆盖起点", coverage.complete_from ?? "未报告"],
		["认证覆盖起点", coverage.certified_from ?? "未报告"],
	] as const;

	return (
		<div data-info-level="l1" data-info-unit="calendar-content" className="flex flex-col gap-4 p-4">
			<ContextSection title="交易日历覆盖" data-info-level="l2" data-info-unit="coverage-milestones">
				<div className="grid gap-3 sm:grid-cols-3">
					{milestones.map(([label, value]) => (
						<div
							key={label}
							data-info-level="l3"
							data-info-unit="coverage-milestone"
							className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4"
						>
							<p className="text-xs text-(--color-foreground-tertiary)">{label}</p>
							<p className="mt-2 font-mono text-base font-semibold">{value}</p>
						</div>
					))}
				</div>
			</ContextSection>
			<ContextSection title="分区完整性" data-info-level="l2" data-info-unit="partition-integrity">
				<div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.6fr)]">
					<div className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4">
						<div className="flex items-end justify-between">
							<div>
								<p className="text-xs text-(--color-foreground-tertiary)">实际 / 预期分区</p>
								<p className="mt-1 font-data text-2xl font-semibold">
									{coverage.actual_partitions.toLocaleString()} / {coverage.expected_partitions.toLocaleString()}
								</p>
							</div>
							<span
								className={
									coverage.unapproved_gaps.length > 0 ? "text-(--color-risk-warning)" : "text-(--color-system-healthy)"
								}
							>
								{coverage.unapproved_gaps.length > 0
									? `存在 ${coverage.unapproved_gaps.length} 个未批准缺口`
									: "无未批准缺口"}
							</span>
						</div>
					</div>
					<div className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4">
						<p className="text-xs text-(--color-foreground-tertiary)">阻断分区</p>
						{coverage.unapproved_gaps.length === 0 ? (
							<p className="mt-2 text-sm">无</p>
						) : (
							<ul className="mt-2 space-y-1 font-mono text-sm text-(--color-risk-warning)">
								{coverage.unapproved_gaps.map((gap) => (
									<li key={gap}>{gap}</li>
								))}
							</ul>
						)}
					</div>
				</div>
			</ContextSection>
		</div>
	);
}
