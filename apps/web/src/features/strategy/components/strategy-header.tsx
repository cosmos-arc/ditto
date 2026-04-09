import { useStrategy } from "../hooks";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

interface StrategyHeaderProps {
	readonly id: string;
}

const STATUS_VARIANT: Record<string, "healthy" | "warning" | "error" | "default"> = {
	completed: "healthy",
	running: "healthy",
	pending: "default",
	failed: "error",
	warning: "warning",
	cancelled: "default",
};

export function StrategyHeader({ id }: StrategyHeaderProps) {
	const { data, isLoading, isError, refetch } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton variant="panel" className="h-16" />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex items-center gap-4 px-4 py-3">
					<div className="flex flex-col">
						<span className="text-lg font-bold">{data.name}</span>
						<span className="text-xs text-(--color-foreground-tertiary)">v{data.version} · {data.universe}</span>
					</div>
					<StatusBadge
						variant={STATUS_VARIANT[data.status] ?? "default"}
						label={data.status}
						size="sm"
					/>
					<div className="flex gap-2">
						{data.factors.map((f) => (
							<span
								key={f}
								className="rounded-full bg-(--color-surface-base) px-2 py-0.5 text-xs text-(--color-foreground-secondary)"
							>
								{f}
							</span>
						))}
					</div>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
