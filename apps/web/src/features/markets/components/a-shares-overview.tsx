import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useAShares } from "../hooks";

function formatVolume(volume: number): string {
	if (volume >= 1e12) return `${(volume / 1e12).toFixed(1)}万亿`;
	if (volume >= 1e8) return `${(volume / 1e8).toFixed(0)}亿`;
	return volume.toString();
}

export function ASharesOverview() {
	const { data, isLoading, refetch } = useAShares();

	if (isLoading) {
		return (
			<div className="flex flex-col gap-4">
				<ContextSection title="指数概览">
					<LoadingSkeleton variant="table" rows={5} columns={4} />
				</ContextSection>
				<ContextSection title="板块涨幅">
					<LoadingSkeleton variant="table" rows={5} columns={3} />
				</ContextSection>
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div data-info-level="l2" data-info-unit="overview-container" className="flex flex-col gap-4">
					<ContextSection title="指数概览" data-info-level="l1" data-info-unit="index-overview">
						{data.summary.map((idx) => (
							<div
								key={idx.index}
								className="flex items-center justify-between py-2 border-b border-(--color-border) last:border-b-0"
							>
								<div className="flex flex-col gap-0.5">
									<span className="text-sm font-medium text-(--color-foreground)">{idx.index}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">成交 {formatVolume(idx.volume)}</span>
								</div>
								<div className="text-right flex flex-col gap-0.5">
									<span className="text-sm font-data text-(--color-foreground)">{idx.price.toLocaleString()}</span>
									<span
										className={`text-xs font-data ${idx.changePercent >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}`}
									>
										{idx.changePercent > 0 ? "+" : ""}
										{idx.changePercent}%
									</span>
								</div>
							</div>
						))}
					</ContextSection>

					<ContextSection title="板块涨幅" data-info-level="l1" data-info-unit="sector-performance">
						{data.sectors.map((s) => (
							<div
								key={s.sector}
								className="flex items-center justify-between py-1.5 border-b border-(--color-border) last:border-b-0"
							>
								<span className="text-sm text-(--color-foreground)">{s.sector}</span>
								<div className="flex items-center gap-3">
									<span className="text-xs text-(--color-foreground-tertiary)">{s.topStock}</span>
									<span
										className={`text-sm font-data ${s.change >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}`}
									>
										{s.change > 0 ? "+" : ""}
										{s.change}%
									</span>
								</div>
							</div>
						))}
					</ContextSection>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
