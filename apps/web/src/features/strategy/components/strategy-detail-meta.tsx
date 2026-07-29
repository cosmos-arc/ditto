import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { StrategyLifecycleState } from "@/types/strategy";
import { useStrategy } from "../hooks";

interface StrategyDetailMetaProps {
	readonly id: string;
}

const LIFECYCLE_VARIANT: Record<StrategyLifecycleState, "healthy" | "warning" | "error" | "default"> = {
	published: "healthy",
	approved: "healthy",
	draft: "default",
	review: "warning",
	deprecated: "default",
	unknown: "default",
};

export function StrategyDetailMeta({ id }: StrategyDetailMetaProps) {
	const { data, isLoading, refetch } = useStrategy(id);

	if (isLoading) {
		return <LoadingSkeleton variant="panel" className="h-16" />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex items-center gap-4 px-4 py-3">
					<div className="flex flex-col">
						<span className="text-lg font-bold">{data.name}</span>
						<span className="text-xs text-(--color-foreground-tertiary)">
							v{data.version} · {data.spec.universe}
						</span>
					</div>
					<StatusBadge variant={LIFECYCLE_VARIANT[data.lifecycleState]} label={data.lifecycleState} size="sm" />
					<div className="flex gap-2">
						{data.tags.map((tag) => (
							<span
								key={tag}
								className="rounded-full bg-(--color-surface-1) px-2 py-0.5 text-xs text-(--color-foreground-secondary)"
							>
								{tag}
							</span>
						))}
					</div>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
