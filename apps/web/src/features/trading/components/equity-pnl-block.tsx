import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { shouldUsePrototypeMocks } from "../api/runtime";
import { useEquity } from "../hooks";

export function EquityPnlBlock() {
	const usePrototypeMocks = shouldUsePrototypeMocks();
	const { data, isLoading, refetch } = useEquity({ enabled: usePrototypeMocks });

	return (
		<ContextSection title="权益 & 盈亏" data-info-level="l1" data-info-unit="equity-pnl">
			{!usePrototypeMocks && (
				<div className="flex flex-col gap-2 py-2">
					<StatusBadge label="权益曲线不可用" variant="idle" size="sm" />
					<span className="text-sm text-(--color-foreground-secondary)">当前公开合同未提供权益时序</span>
				</div>
			)}
			{isLoading && <LoadingSkeleton variant="chart" />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{usePrototypeMocks && data && (
					<div className="flex flex-col gap-3">
						<div className="flex gap-4">
							{data.series.length > 0 &&
								(() => {
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
