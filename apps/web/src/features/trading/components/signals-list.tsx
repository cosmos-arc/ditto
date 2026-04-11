import { useSignals } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const DIRECTION_VARIANT: Record<string, "trade" | "risk" | "research"> = {
	BUY: "trade",
	SELL: "risk",
	HOLD: "research",
};

const STATUS_VARIANT: Record<string, "healthy" | "warning" | "default" | "degraded"> = {
	pending: "warning",
	confirmed: "healthy",
	ignored: "default",
	ordered: "degraded",
};

export function SignalsList() {
	const { data, isLoading, isError, refetch } = useSignals({ tab: "pending" });

	return (
		<ContextSection title="信号队列" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((signal) => (
							<div
								key={signal.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<StatusBadge
										variant={DIRECTION_VARIANT[signal.direction] ?? "default"}
										label={signal.direction}
										size="sm"
									/>
									<span className="text-xs text-(--color-foreground-tertiary)">{signal.instrument}</span>
									<span className="font-medium">{signal.source}</span>
									<StatusBadge
										variant={STATUS_VARIANT[signal.status] ?? "default"}
										label={signal.status}
										size="sm"
									/>
								</div>
								<div className="flex items-center gap-3 text-(--color-foreground-tertiary)">
									<span>权重 {signal.weight.toFixed(2)}</span>
									<span className="font-medium">{(signal.confidence * 100).toFixed(0)}%</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
