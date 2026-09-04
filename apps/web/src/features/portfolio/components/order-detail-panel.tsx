import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { OrderSide } from "@/types";
import { useOrderDetail, useUpdateIntentStatus } from "../hooks";

interface OrderDetailPanelProps {
	readonly orderId: string;
}

const SIDE_LABEL: Record<OrderSide, string> = {
	BUY: "买入",
	SELL: "卖出",
};

export function OrderDetailPanel({ orderId }: OrderDetailPanelProps) {
	const { data, isLoading, isError, refetch } = useOrderDetail(orderId);
	const updateIntentStatus = useUpdateIntentStatus();
	const [command, setCommand] = useState<"cancel" | "retry" | null>(null);
	const [commandResult, setCommandResult] = useState<string | null>(null);

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
	const canCancel = order && (order.status === "pending" || order.status === "submitted" || order.status === "partial");
	const canRetry = order && (order.status === "failed" || order.status === "cancelled");

	function submitIntentCommand() {
		if (!order || !command) return;
		updateIntentStatus.mutate(
			{ intentId: order.id, status: command === "cancel" ? "cancelled" : "pending" },
			{
				onSuccess: () => {
					setCommandResult(command === "cancel" ? "取消命令已提交" : "意图已重新排队；仍需人工执行");
					setCommand(null);
				},
			},
		);
	}

	return (
		<>
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
										<li key={`${step.time}-${step.event}`} className="flex items-start gap-2 text-(length:--text-sm)">
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
										<li
											key={`${log.time}-${log.event}`}
											className="text-(length:--text-sm) text-(--color-foreground-tertiary)"
										>
											<span className="font-medium text-(--color-foreground-secondary)">{log.event}</span>
											{log.detail && ` — ${log.detail}`}
										</li>
									))}
								</ol>
							</section>
						)}
						{commandResult && (
							<p role="status" className="text-sm text-(--color-system-healthy-fg)">
								{commandResult}
							</p>
						)}
						{updateIntentStatus.isError && (
							<p role="alert" className="text-sm text-(--color-risk-critical-fg)">
								命令结果未确认；请刷新后核对意图状态，再决定是否重试。
							</p>
						)}
						{(canCancel || canRetry) && (
							<section className="flex gap-2">
								{canCancel && (
									<Button type="button" variant="destructive" size="sm" onClick={() => setCommand("cancel")}>
										取消意图
									</Button>
								)}
								{canRetry && (
									<Button type="button" variant="outline" size="sm" onClick={() => setCommand("retry")}>
										重新排队
									</Button>
								)}
							</section>
						)}
					</div>
				</PanelBody>
			</Panel>
			<Dialog
				open={command !== null}
				onOpenChange={(open) => !updateIntentStatus.isPending && !open && setCommand(null)}
			>
				<DialogContent aria-describedby="intent-command-description">
					<DialogHeader>
						<DialogTitle>{command === "retry" ? "确认重试订单" : "确认取消订单"}</DialogTitle>
						<DialogDescription id="intent-command-description">
							{command === "retry"
								? "只把 Manual 本地意图恢复为 pending；不会创建 Paper 订单或成交。"
								: "只取消 Manual 本地意图；不会改写既有 Paper/Manual 账本事件。"}
						</DialogDescription>
					</DialogHeader>
					<p className="font-data text-sm text-(--color-foreground-secondary)">{order?.id}</p>
					<DialogFooter>
						<Button
							type="button"
							variant="outline"
							disabled={updateIntentStatus.isPending}
							onClick={() => setCommand(null)}
						>
							返回
						</Button>
						<Button
							type="button"
							variant={command === "cancel" ? "destructive" : "default"}
							disabled={updateIntentStatus.isPending}
							onClick={submitIntentCommand}
						>
							{updateIntentStatus.isPending ? "提交中" : command === "retry" ? "确认重试" : "确认取消"}
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</>
	);
}
