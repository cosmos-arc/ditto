import { useBacktestResult } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { AreaChart } from "@/components/chart/area-chart";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

interface BacktestOverviewProps {
	readonly jobId: string;
}

export function BacktestOverview({ jobId }: BacktestOverviewProps) {
	const { data, isLoading, isError, refetch } = useBacktestResult(jobId);

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={6} />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex flex-col gap-(--section-gap)">
					<div data-info-level="l2" data-info-unit="nav-curve">
						<ContextSection title="净值曲线">
							<AreaChart
								data={data.navSeries.map((p) => ({
									time: p.date,
									value: p.nav,
								}))}
								height={200}
								showAxes
							/>
						</ContextSection>
					</div>

					<div data-info-level="l2" data-info-unit="current-holdings">
						<ContextSection title="当前持仓" count={data.holdings.length}>
							<div className="space-y-1">
								{data.holdings.map((h) => (
									<div
										key={h.code}
										data-info-level="l3"
										data-info-unit="holding-item"
										className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										<div className="flex items-center gap-3">
											<span className="font-medium">{h.name}</span>
											<span className="text-xs text-(--color-foreground-tertiary)">
												{h.code}
											</span>
										</div>
										<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
											<span>{(h.weight * 100).toFixed(0)}%</span>
											<span>{h.shares} 股</span>
										</div>
									</div>
								))}
							</div>
						</ContextSection>
					</div>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
