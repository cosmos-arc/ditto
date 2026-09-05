import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useFillLedger, useOrdersSummary, useSignalsQueue } from "../hooks";

function distributionFlex(count: number, total: number): string {
	if (count === 0) return "flex-[0.2]";
	const share = total > 0 ? count / total : 0;
	if (share <= 0.1) return "flex-[1]";
	if (share <= 0.25) return "flex-[2]";
	if (share <= 0.5) return "flex-[4]";
	return "flex-[8]";
}

export function SignalToOrderPipelineStrip() {
	const signalsQuery = useSignalsQueue();
	const ordersQuery = useOrdersSummary();
	const ledgerQuery = useFillLedger();
	const signals = signalsQuery.data;
	const orders = ordersQuery.data;
	const ledger = ledgerQuery.data;
	const filledCount = Math.max(orders?.filled ?? 0, ledger?.fills.length ?? 0);
	const isError = signalsQuery.isError || ordersQuery.isError || ledgerQuery.isError;
	const isLoading = !isError && (signalsQuery.isLoading || ordersQuery.isLoading || ledgerQuery.isLoading);

	function retryPipeline() {
		void Promise.all([signalsQuery.refetch(), ordersQuery.refetch(), ledgerQuery.refetch()]);
	}

	const stages = [
		{
			label: "信号池",
			count: signals ? signals.pending + signals.confirmed + signals.ignored + signals.ordered : 0,
		},
		{ label: "待复核", count: signals?.pending ?? 0 },
		{ label: "已下单", count: orders ? orders.submitted + orders.partial : 0 },
		{ label: "成交", count: filledCount },
	] as const;
	const orderCounts: readonly [number, number, number, number, number] = orders
		? [orders.pending, orders.submitted, orders.partial, orders.filled, orders.failed]
		: [0, 0, 0, 0, 0];
	const totalOrders = orderCounts.reduce((total, count) => total + count, 0);
	const fillRate = totalOrders > 0 ? (filledCount / totalOrders) * 100 : 0;
	const effectiveFills = ledger?.fills.filter((fill) => fill.state === "effective") ?? [];
	const averageSlippage =
		effectiveFills.length > 0
			? effectiveFills.reduce((total, fill) => total + fill.slippage, 0) / effectiveFills.length
			: 0;
	const filledTurnover = effectiveFills.reduce((total, fill) => total + fill.quantity * fill.fillPrice, 0);
	const compactTurnover =
		filledTurnover >= 1_000_000
			? `${(filledTurnover / 1_000_000).toFixed(2)}M`
			: filledTurnover >= 1_000
				? `${(filledTurnover / 1_000).toFixed(2)}K`
				: filledTurnover.toFixed(2);

	return (
		<section
			aria-label="Signal-to-Order Pipeline"
			className="flex min-h-12 flex-col gap-2 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2 sm:h-12 sm:flex-row sm:items-center sm:gap-4 sm:py-0"
			data-info-level="l2"
			data-info-unit="signal-to-order-pipeline"
		>
			<span className="sr-only">Signal-to-Order Pipeline</span>
			<span className="sr-only">manual / paper</span>
			{isLoading && (
				<div role="status" aria-label="Pipeline 加载中">
					<LoadingSkeleton variant="panel" rows={2} />
				</div>
			)}
			{isError && (
				<div
					role="alert"
					className="flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
				>
					<span>信号到订单流水线加载失败</span>
					<Button variant="outline" size="sm" onClick={retryPipeline}>
						重试
					</Button>
				</div>
			)}
			{!isLoading && !isError && (
				<>
					<div role="status" aria-label="Pipeline 数据" className="sr-only grid-cols-1 sm:grid-cols-4">
						{stages.map((stage) => (
							<span key={stage.label}>
								<span>{stage.label}</span> {stage.count}
							</span>
						))}
					</div>
					<div className="flex w-[103px] shrink-0 items-center gap-2">
						<div>
							<p className="font-data text-[16px] leading-none font-semibold">{totalOrders}</p>
							<p className="mt-1 text-xs leading-[15px] tracking-[.03em] text-(--color-foreground-secondary)">
								今日订单
							</p>
						</div>
						<svg viewBox="0 0 56 24" className="h-6 w-14 shrink-0" aria-hidden="true">
							<polyline
								points="0,18 8,14 16,16 24,10 32,12 40,6 48,8 56,4"
								fill="none"
								stroke="var(--color-accent)"
								strokeWidth="1.5"
								strokeLinecap="round"
								strokeLinejoin="round"
								opacity=".6"
							/>
						</svg>
					</div>
					<i aria-hidden="true" className="h-6 w-px shrink-0 bg-(--color-border-subtle)" />
					<div className="flex w-[101px] shrink-0 items-center">
						<div>
							<p className="font-data text-[16px] leading-none font-semibold">¥{compactTurnover}</p>
							<p className="mt-1 text-xs leading-[15px] tracking-[.03em] text-(--color-foreground-secondary)">成交额</p>
						</div>
					</div>
					<i aria-hidden="true" className="h-6 w-px shrink-0 bg-(--color-border-subtle)" />
					<div className="flex w-[108px] shrink-0 items-center gap-2">
						<div>
							<p className="font-data text-[16px] leading-none font-semibold">
								{fillRate.toFixed(1)}
								<span className="text-xs leading-[inherit]">%</span>
							</p>
							<p className="mt-1 text-xs leading-[15px] tracking-[.03em] text-(--color-foreground-secondary)">成交率</p>
						</div>
						<svg viewBox="0 0 56 24" className="h-6 w-14 shrink-0" aria-hidden="true">
							<polyline
								points="0,12 8,10 16,14 24,8 32,6 40,9 48,5 56,3"
								fill="none"
								stroke="var(--color-market-up-fg)"
								strokeWidth="1.5"
								strokeLinecap="round"
								strokeLinejoin="round"
								opacity=".6"
							/>
						</svg>
					</div>
					<i aria-hidden="true" className="h-6 w-px shrink-0 bg-(--color-border-subtle)" />
					<div className="w-20 shrink-0">
						<p className="font-data text-[16px] leading-none font-semibold">{averageSlippage.toFixed(2)}</p>
						<p className="mt-1 text-xs leading-[15px] tracking-[.03em] text-(--color-foreground-secondary)">平均滑点</p>
					</div>
					<i aria-hidden="true" className="h-6 w-px shrink-0 bg-(--color-border-subtle)" />
					<div className="min-w-[120px] flex-1">
						<p className="text-xs leading-[15px] tracking-[.03em] text-(--color-foreground-secondary)">状态分布</p>
						<div
							className="mt-1 flex h-1.5 max-w-36 overflow-hidden rounded-sm"
							role="img"
							aria-label={`待提交 ${orderCounts[0]}，已提交 ${orderCounts[1]}，部分成交 ${orderCounts[2]}，已成交 ${orderCounts[3]}，失败 ${orderCounts[4]}`}
						>
							<i className={`bg-(--color-risk-medium-fg) ${distributionFlex(orderCounts[0], totalOrders)}`} />
							<i className={`bg-(--color-accent) ${distributionFlex(orderCounts[1], totalOrders)}`} />
							<i className={`bg-(--color-risk-warning-fg) ${distributionFlex(orderCounts[2], totalOrders)}`} />
							<i className={`bg-(--color-status-healthy-fg) ${distributionFlex(orderCounts[3], totalOrders)}`} />
							<i className={`bg-(--color-risk-critical-fg) ${distributionFlex(orderCounts[4], totalOrders)}`} />
						</div>
					</div>
				</>
			)}
		</section>
	);
}
