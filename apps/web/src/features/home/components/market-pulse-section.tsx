import { useMarketIndices } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ScrollReveal } from "@/components/ui/scroll-reveal";

/**
 * MarketPulseSection — sidebar "市场脉搏" section.
 * Matches prototype .context-section with .pulse-metric items.
 * Shows market index values with up/down indicators.
 */
export function MarketPulseSection() {
	const { data, isLoading } = useMarketIndices();

	return (
		<ContextSection title="市场脉搏" defaultOpen>
			{isLoading && <LoadingSkeleton variant="table" rows={4} />}
			{data && (
				<ScrollReveal>
					<div className="flex flex-col gap-1">
						{data.indices.slice(0, 4).map((index) => (
							<div
								key={index.code}
								className="flex items-center justify-between rounded-[var(--radius-sm)] px-2 py-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<span className="text-[10px] text-(--color-foreground-tertiary) uppercase tracking-[0.02em]">
									{index.name}
								</span>
								<span
									className={`font-data text-xs tabular-nums ${index.dir === "up" ? "text-(--color-market-up-fg)" : "text-(--color-market-down-fg)"}`}
								>
									{index.price.toLocaleString()}
									<span className="ml-1.5 text-[10px]">
										{index.change >= 0 ? "+" : ""}{index.changePercent.toFixed(2)}%
									</span>
								</span>
							</div>
						))}
					</div>
				</ScrollReveal>
			)}
		</ContextSection>
	);
}
