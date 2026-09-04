import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useFactorDetail } from "../hooks";

const HEALTH_VARIANT: Record<string, "healthy" | "warning" | "error" | "default"> = {
	completed: "healthy",
	running: "healthy",
	pending: "default",
	failed: "error",
	warning: "warning",
	cancelled: "default",
};

interface FactorDetailHeaderProps {
	readonly id: string;
}

export function FactorDetailHeader({ id }: FactorDetailHeaderProps) {
	const { data, isLoading, refetch } = useFactorDetail(id);

	if (isLoading) {
		return <LoadingSkeleton variant="panel" className="h-16" />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex items-center gap-4 px-4 py-3">
					<div className="flex flex-col">
						<span className="text-lg font-bold">{data.factor.name}</span>
						<span className="text-xs text-(--color-foreground-tertiary)">{data.factor.family}</span>
					</div>
					<StatusBadge
						variant={HEALTH_VARIANT[data.factor.healthStatus] ?? "default"}
						label={data.factor.healthStatus}
						size="sm"
					/>
					<div className="flex items-center gap-4 text-sm text-(--color-foreground-tertiary)">
						<span>IC {data.factor.ic.toFixed(3)}</span>
						<span>IR {data.factor.ir.toFixed(2)}</span>
						<span>覆盖 {((data.factor.coverage ?? 0) * 100).toFixed(0)}%</span>
					</div>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
