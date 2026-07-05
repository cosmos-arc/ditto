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
	const { data: signals } = useSignalsQueue();
	const { data: orders } = useOrdersSummary();
	const { data: ledger } = useFillLedger();
	const filledCount = Math.max(orders?.filled ?? 0, ledger?.fills.length ?? 0);

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
			<div className="grid grid-cols-4 gap-2">
				{stages.map((stage) => (
					<StagePill key={stage.label} {...stage} />
				))}
			</div>
		</section>
	);
}
