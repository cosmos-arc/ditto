import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { OrderSide } from "@/types";
import { useOrderDetail } from "../hooks/use-order-detail";

interface OrderDetailPanelProps {
	readonly orderId: string;
}

const SIDE_LABEL: Record<OrderSide, string> = {
	BUY: "买入",
	SELL: "卖出",
};

export function OrderDetailPanel({ orderId }: OrderDetailPanelProps) {
	const { data, isLoading, isError, refetch } = useOrderDetail(orderId);

	if (isLoading) {
		return (
			<Panel>
				<PanelHeader title="订单详情" />
				<PanelBody>
					<div className="p-3">
						<LoadingSkeleton variant="panel" rows={6} />
					</div>
				</PanelBody>
			</Panel>
		);
	}

	if (isError) {
		return (
			<Panel>
				<PanelHeader title="订单详情" />
				<PanelBody>
					<DittoErrorBoundary
						fallbackProps={{
							title: "订单详情加载失败",
							onRetry: () => void refetch(),
						}}
					>
						<div />
					</DittoErrorBoundary>
				</PanelBody>
			</Panel>
		);
	}

	const order = data?.order;

	return (
		<Panel>
			<PanelHeader title="订单详情" />
			<PanelBody>
				<div className="flex flex-col gap-(--density-gutter) p-3">
					{order && (
						<section>
							<div className="mb-2 flex items-baseline gap-2">
								<span className="font-data text-(length:--text-md) font-semibold text-(--color-foreground)">
									{order.instrument}
								</span>
								<span className="text-(length:--text-sm) text-(--color-foreground-tertiary)">
									{SIDE_LABEL[order.side as OrderSide] ?? order.side} · {order.type}
								</span>
							</div>
							<div className="grid grid-cols-2 gap-x-4 gap-y-1 text-(length:--text-sm)">
								<div>
									<span className="text-(--color-foreground-tertiary)">数量</span>
									<div className="font-data text-(--color-foreground)">{order.qty.toLocaleString()}</div>
								</div>
								<div>
									<span className="text-(--color-foreground-tertiary)">价格</span>
									<div className="font-data text-(--color-foreground)">¥{order.price.toFixed(2)}</div>
								</div>
								<div>
									<span className="text-(--color-foreground-tertiary)">已成交</span>
									<div className="font-data text-(--color-foreground)">{order.filledQty.toLocaleString()}</div>
								</div>
								<div>
									<span className="text-(--color-foreground-tertiary)">状态</span>
									<div className="text-(--color-foreground)">{order.status}</div>
								</div>
							</div>
						</section>
					)}

					{data && (
						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">费用</h4>
							<div className="grid grid-cols-2 gap-2 text-(length:--text-sm)">
								<div>
									<span className="text-(--color-foreground-tertiary)">手续费</span>
									<div className="font-data text-(--color-foreground)">¥{data.fees.toFixed(2)}</div>
								</div>
								<div>
									<span className="text-(--color-foreground-tertiary)">滑点</span>
									<div className="font-data text-(--color-foreground)">
										{data.slippage > 0 ? "+" : ""}
										{data.slippage.toFixed(2)}
									</div>
								</div>
							</div>
						</section>
					)}

					{data?.trace && data.trace.length > 0 && (
						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">执行追踪</h4>
							<ol className="flex flex-col gap-1">
								{data.trace.map((step) => (
									<li key={step.time} className="flex items-start gap-2 text-(length:--text-sm)">
										<span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-(--color-accent)" />
										<div className="min-w-0 flex-1">
											<span className="font-medium text-(--color-foreground)">{step.event}</span>
											{step.detail && <p className="text-(--color-foreground-tertiary)">{step.detail}</p>}
										</div>
									</li>
								))}
							</ol>
						</section>
					)}

					{data?.routeLog && data.routeLog.length > 0 && (
						<section>
							<h4 className="mb-1 text-xs font-medium text-(--color-foreground-secondary)">路由日志</h4>
							<ol className="flex flex-col gap-1">
								{data.routeLog.map((log) => (
									<li key={log.time} className="text-(length:--text-sm) text-(--color-foreground-tertiary)">
										<span className="font-medium text-(--color-foreground-secondary)">{log.event}</span>
										{log.detail && ` — ${log.detail}`}
									</li>
								))}
							</ol>
						</section>
					)}
				</div>
			</PanelBody>
		</Panel>
	);
}
