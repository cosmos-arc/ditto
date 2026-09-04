import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useOrders } from "../hooks";

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
		<section data-info-level="l1" data-info-unit="orders-list">
			<span className="sr-only">订单台账</span>
			{isLoading && (
				<div className="p-3">
					<LoadingSkeleton variant="table" rows={5} />
				</div>
			)}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="overflow-x-auto">
						<table className="w-full min-w-[760px] table-fixed border-collapse text-left text-[12px] leading-[18px]">
							<colgroup>
								<col className="w-20" />
								<col className="w-28" />
								<col className="w-16" />
								<col className="w-16" />
								<col className="w-22" />
								<col className="w-22" />
								<col className="w-16" />
								<col className="w-30" />
								<col />
							</colgroup>
							<thead>
								<tr className="h-[27px] border-b border-(--color-border-subtle) text-(--color-foreground-tertiary)">
									<th className="px-3 font-medium">订单ID</th>
									<th className="px-3 font-medium">标的</th>
									<th className="px-3 font-medium">方向</th>
									<th className="px-3 text-right font-medium">数量</th>
									<th className="px-3 text-right font-medium">委托价</th>
									<th className="px-3 text-right font-medium">成交价</th>
									<th className="px-3 font-medium">类型</th>
									<th className="px-3 font-medium">状态</th>
									<th className="px-3 font-medium">时间</th>
								</tr>
							</thead>
							<tbody>
								{data.items.map((order) => (
									<tr
										key={order.id}
										className="h-[31px] border-b border-(--color-border-subtle) hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<td className="px-3 font-data uppercase text-(--color-foreground-secondary)">
											{order.id.startsWith("intent-") ? (
												<>
													<span>{order.id.slice(0, 6)}</span>
													<span>{order.id.slice(6)}</span>
												</>
											) : (
												order.id
											)}
										</td>
										<td className="p-0">
											{onSelectOrder ? (
												<button
													type="button"
													className="h-[30px] w-full px-3 text-left font-medium text-(--color-foreground)"
													aria-label={`查看订单 ${order.instrument}`}
													onClick={() => onSelectOrder(order.id)}
												>
													{order.instrument}
												</button>
											) : (
												<span className="px-3 font-medium">{order.instrument}</span>
											)}
										</td>
										<td
											className={`px-3 font-medium ${order.side === "BUY" ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}
										>
											<span aria-hidden="true" className="text-[.7em]">
												{order.side === "BUY" ? "▲ " : "▼ "}
											</span>
											{order.side}
										</td>
										<td className="px-3 text-right font-data">{order.qty.toLocaleString()}</td>
										<td className="px-3 text-right font-data">{order.price.toFixed(2)}</td>
										<td className="px-3 text-right font-data text-(--color-foreground-tertiary)">
											{order.filledQty > 0 ? order.price.toFixed(2) : "—"}
										</td>
										<td className="px-3">
											<span className="rounded-sm bg-(--color-surface-panel-elevated) px-1 text-xs leading-[inherit]">
												{order.type === "LIMIT" ? "限价" : "市价"}
											</span>
										</td>
										<td className="px-3">
											<StatusBadge variant={STATUS_VARIANT[order.status] ?? "default"} label={order.status} size="sm" />
										</td>
										<td className="px-3 font-data">{order.updatedAt.slice(11, 19)}</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</DittoErrorBoundary>
		</section>
	);
}
