import { useOrders } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const SIDE_VARIANT: Record<string, "trade" | "risk"> = {
	BUY: "trade",
	SELL: "risk",
};

const STATUS_VARIANT: Record<string, "healthy" | "warning" | "default" | "degraded"> = {
	pending: "warning",
	submitted: "default",
	partial: "degraded",
	filled: "healthy",
};

export function OrdersList() {
	const { data, isLoading, isError, refetch } = useOrders();

	return (
		<ContextSection title="订单台账" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((order) => (
							<div
								key={order.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-surface-hover)"
							>
								<div className="flex items-center gap-3">
									<StatusBadge
										variant={SIDE_VARIANT[order.side] ?? "default"}
										label={order.side}
										size="sm"
									/>
									<span className="font-medium">{order.instrument}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										{order.qty.toLocaleString()} 股
									</span>
									<span className="text-xs text-(--color-foreground-tertiary)">
										@ {order.price.toFixed(2)}
									</span>
								</div>
								<div className="flex items-center gap-3">
									<span className="text-xs text-(--color-foreground-tertiary)">
										{order.type}
									</span>
									<StatusBadge
										variant={STATUS_VARIANT[order.status] ?? "default"}
										label={order.status}
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
