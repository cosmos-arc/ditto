import { useBacktestResult } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

interface BacktestReturnsViewProps {
	readonly jobId: string;
}

export function BacktestReturnsView({ jobId }: BacktestReturnsViewProps) {
	const { data, isLoading, isError, refetch } = useBacktestResult(jobId);

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={6} />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<ContextSection title="月度收益" count={data.monthlyReturns.length}>
					<div className="space-y-1">
						<div className="flex items-center justify-between px-3 py-1 text-xs text-(--color-foreground-tertiary)">
							<span>月份</span>
							<div className="flex items-center gap-4">
								<span>策略</span>
								<span>基准</span>
							</div>
						</div>
						{data.monthlyReturns.map((mr) => (
							<div
								key={mr.month}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span className="font-medium">{mr.month}</span>
								<div className="flex items-center gap-4">
									<span
										className={
											mr.return >= 0
												? "text-(--color-led-success)"
												: "text-(--color-led-error)"
										}
									>
										{mr.return.toFixed(1)}%
									</span>
									<span
										className={
											mr.benchmarkReturn >= 0
												? "text-(--color-led-success)"
												: "text-(--color-led-error)"
										}
									>
										{mr.benchmarkReturn.toFixed(1)}%
									</span>
								</div>
							</div>
						))}
					</div>
				</ContextSection>
			)}
		</DittoErrorBoundary>
	);
}
