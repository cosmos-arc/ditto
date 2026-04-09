import { useFactors } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const HEALTH_VARIANT: Record<string, "healthy" | "warning" | "error"> = {
	completed: "healthy",
	running: "healthy",
	pending: "default",
	failed: "error",
	warning: "warning",
	cancelled: "default",
};

export function FactorTable() {
	const { data, isLoading, isError, refetch } = useFactors();

	return (
		<ContextSection title="因子监控" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((factor) => (
							<div
								key={factor.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-surface-hover)"
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{factor.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										{factor.family}
									</span>
									<StatusBadge
										variant={HEALTH_VARIANT[factor.healthStatus] ?? "default"}
										label={factor.healthStatus}
										size="sm"
									/>
								</div>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span>IC {factor.ic.toFixed(3)}</span>
									<span>IR {factor.ir.toFixed(2)}</span>
									<span>覆盖 {((factor.coverage ?? 0) * 100).toFixed(0)}%</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
