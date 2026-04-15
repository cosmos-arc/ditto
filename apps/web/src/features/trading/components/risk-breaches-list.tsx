import { useRiskBreaches } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { cn } from "@/lib/utils";

const BREACH_STATUS_VARIANT: Record<string, "healthy" | "warning" | "default" | "degraded"> = {
	active: "degraded",
	acknowledged: "warning",
	resolved: "healthy",
};

interface RiskBreachesListProps {
	readonly onSelectBreach?: (breachId: string) => void;
}

export function RiskBreachesList({ onSelectBreach }: RiskBreachesListProps) {
	const { data, isLoading, isError, refetch } = useRiskBreaches();

	return (
		<ContextSection title="风控告警" count={data?.total} data-info-level="l1" data-info-unit="risk-breaches-list">
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((breach) => (
							<div
								key={breach.id}
								className={cn(
									"flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)",
									onSelectBreach && "cursor-pointer",
								)}
								onClick={onSelectBreach ? () => onSelectBreach(breach.id) : undefined}
								onKeyDown={onSelectBreach ? (e) => {
									if (e.key === "Enter" || e.key === " ") {
										e.preventDefault();
										onSelectBreach(breach.id);
									}
								} : undefined}
								role={onSelectBreach ? "button" : undefined}
								tabIndex={onSelectBreach ? 0 : undefined}
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{breach.ruleName}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										阈值 {String(breach.threshold)}
									</span>
								</div>
								<div className="flex items-center gap-3">
									<span className="tabular-nums text-(--color-foreground-tertiary)">
										偏差 {breach.deviation.toFixed(1)}%
									</span>
									<StatusBadge
										variant={BREACH_STATUS_VARIANT[breach.status] ?? "default"}
										label={breach.status}
										size="sm"
									/>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
