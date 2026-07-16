import { useMarketPulseMetrics } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { Sparkline } from "@/components/data/sparkline";
import type { SparklineColor } from "@/components/data/sparkline";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ScrollReveal } from "@/components/ui/scroll-reveal";

/** Derive sparkline color from the change string. */
function changeToColor(change: string): SparklineColor {
	if (change.startsWith("+")) return "up";
	if (change.startsWith("-")) return "down";
	return "neutral";
}

/** Map change string + direction to a CSS text color class. */
function changeTextColor(change: string): string {
	if (change.startsWith("+")) return "text-(--color-market-up-fg)";
	if (change.startsWith("-")) return "text-(--color-market-down-fg)";
	return "text-(--color-foreground-tertiary)";
}

/**
 * MarketPulseSection -- sidebar "市场脉搏" section.
 * Matches prototype .pulse-metric items: label + value/change + optional sparkline.
 * Consumes MarketPulseMetric mock data (4 metrics with inline sparklines).
 */
export function MarketPulseSection() {
	const { data, isLoading } = useMarketPulseMetrics();

	return (
		<ContextSection title="市场脉搏" defaultOpen data-info-level="l1" data-info-unit="market-pulse">
			{isLoading && <LoadingSkeleton variant="table" rows={4} />}
			{data && (
				<ScrollReveal>
					<div className="flex flex-col gap-1">
						{data.metrics.map((metric) => (
							<div
								key={metric.label}
								className="flex items-center justify-between rounded-[var(--radius-sm)] px-2 py-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg) border-b border-dashed border-(--color-border-subtle) last:border-b-0"
							>
								<span className="text-xs text-(--color-foreground-tertiary) uppercase tracking-[0.02em]">
									{metric.label}
								</span>
								<span
									className={`flex items-center gap-1.5 font-data text-xs tabular-nums ${changeTextColor(metric.change)}`}
								>
									{metric.value}
									{metric.change && (
										<span>{metric.change}</span>
									)}
									{metric.sparkline && metric.sparkline.length >= 2 && (
										<Sparkline
											data={metric.sparkline}
											color={changeToColor(metric.change)}
											width={48}
											height={16}
										/>
									)}
								</span>
							</div>
						))}
					</div>
				</ScrollReveal>
			)}
		</ContextSection>
	);
}
