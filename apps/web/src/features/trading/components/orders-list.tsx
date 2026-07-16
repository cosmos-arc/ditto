import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { cn } from "@/lib/utils";
import { useOrders } from "../hooks";

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

interface OrdersListProps {
	readonly onSelectOrder?: (orderId: string) => void;
}

export function OrdersList({ onSelectOrder }: OrdersListProps) {
	const { data, isLoading, refetch } = useOrders();

	return (
		<ContextSection title="订单台账" count={data?.total} data-info-level="l1" data-info-unit="orders-list">
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((order) => (
							<div
								key={order.id}
								className={cn(
									"flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)",
									onSelectOrder && "cursor-pointer",
								)}
								onClick={onSelectOrder ? () => onSelectOrder(order.id) : undefined}
								onKeyDown={
									onSelectOrder
										? (e) => {
												if (e.key === "Enter" || e.key === " ") {
													e.preventDefault();
													onSelectOrder(order.id);
												}
											}
										: undefined
								}
								role={onSelectOrder ? "button" : undefined}
								tabIndex={onSelectOrder ? 0 : undefined}
							>
								<div className="flex items-center gap-3">
									<StatusBadge variant={SIDE_VARIANT[order.side] ?? "default"} label={order.side} size="sm" />
									<span className="font-medium">{order.instrument}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">{order.qty.toLocaleString()} 股</span>
									<span className="text-xs text-(--color-foreground-tertiary)">@ {order.price.toFixed(2)}</span>
								</div>
								<div className="flex items-center gap-3">
									<span className="text-xs text-(--color-foreground-tertiary)">{order.type}</span>
									<StatusBadge variant={STATUS_VARIANT[order.status] ?? "default"} label={order.status} size="sm" />
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
