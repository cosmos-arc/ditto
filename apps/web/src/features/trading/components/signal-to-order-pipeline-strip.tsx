import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Button } from "@/components/ui/button";
import { useFillLedger, useOrdersSummary, useSignalsQueue } from "../hooks";

type PipelineStage = {
	readonly label: string;
	readonly count: number;
};

function StagePill({ label, count }: PipelineStage) {
	return (
		<div className="flex min-w-0 flex-1 items-center justify-between rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-2">
			<span className="truncate text-xs font-medium text-(--color-foreground-secondary)">{label}</span>
			<span className="font-data text-sm tabular-nums text-(--color-foreground)">{count}</span>
		</div>
	);
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

	const stages: readonly PipelineStage[] = [
		{
			label: "信号池",
			count: signals ? signals.pending + signals.confirmed + signals.ignored + signals.ordered : 0,
		},
		{ label: "待复核", count: signals?.pending ?? 0 },
		{ label: "已下单", count: orders ? orders.submitted + orders.partial : 0 },
		{ label: "成交", count: filledCount },
	];

	return (
		<section
			aria-label="Signal-to-Order Pipeline"
			className="flex flex-col gap-2 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-3"
			data-info-level="l2"
			data-info-unit="signal-to-order-pipeline"
		>
			<div className="flex items-center justify-between">
				<h2 className="text-sm font-medium text-(--color-foreground)">Signal-to-Order Pipeline</h2>
				<span className="text-xs text-(--color-foreground-tertiary)">manual / paper</span>
			</div>
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
				<div role="status" aria-label="Pipeline 数据" className="grid grid-cols-1 gap-2 sm:grid-cols-4">
					{stages.map((stage) => (
						<StagePill key={stage.label} {...stage} />
					))}
				</div>
			)}
		</section>
	);
}
