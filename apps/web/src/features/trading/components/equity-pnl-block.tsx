import { useEquity } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function EquityPnlBlock() {
	const { data, isLoading, isError, refetch } = useEquity();

	return (
		<ContextSection title="权益 & 盈亏" data-info-level="l1" data-info-unit="equity-pnl">
			{isLoading && <LoadingSkeleton variant="chart" />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="flex flex-col gap-3">
						<div className="flex gap-4">
							{data.series.length > 0 && (() => {
								const latest = data.series[data.series.length - 1];
								return (
									<>
										<Metric
											variant="equity"
											label="总权益"
											value={`¥${latest.equity.toLocaleString()}`}
											sub={`日盈亏 ¥${latest.pnl.toLocaleString()}`}
											trend={latest.pnl >= 0 ? "up" : "down"}
										/>
										<Metric
											variant="standard"
											label="累计收益率"
											value={`${latest.pnlPercent.toFixed(2)}%`}
											trend={latest.pnlPercent >= 0 ? "up" : "down"}
										/>
									</>
								);
							})()}
						</div>
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
