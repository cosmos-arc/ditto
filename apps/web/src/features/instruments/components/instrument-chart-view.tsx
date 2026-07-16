import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ErrorState } from "@/lib/error-boundary";
import { useInstrumentChart } from "../hooks/use-instrument-chart";

interface InstrumentChartViewProps {
	readonly id: string;
}

export function InstrumentChartView({ id }: InstrumentChartViewProps) {
	const { data, isLoading, isError, refetch } = useInstrumentChart(id);

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={10} />;
	}

	if (isError) {
		return <ErrorState onRetry={() => void refetch()} />;
	}

	if (!data?.bars.length) {
		return null;
	}

	const firstBar = data.bars[0];

	return (
		<ContextSection title="价格走势">
			<div className="p-[var(--density-panel-padding)]">
				{/* Header row */}
				<div className="grid grid-cols-6 gap-(--section-gap) text-(--color-foreground-tertiary) text-xs font-medium pb-2 border-b border-(--color-border-primary)">
					<span>时间</span>
					<span>开</span>
					<span>高</span>
					<span>低</span>
					<span>收</span>
					<span>量</span>
				</div>

				{/* Latest bar */}
				<div className="grid grid-cols-6 gap-(--section-gap) py-1.5 text-sm hover:bg-(--color-interaction-hover-subtle-bg) transition-colors">
					<span>{firstBar.time}</span>
					<span>{firstBar.open.toFixed(1)}</span>
					<span>{firstBar.high.toFixed(1)}</span>
					<span>{firstBar.low.toFixed(1)}</span>
					<span>{firstBar.close.toFixed(1)}</span>
					<span>{firstBar.volume.toLocaleString()}</span>
				</div>
			</div>
		</ContextSection>
	);
}
