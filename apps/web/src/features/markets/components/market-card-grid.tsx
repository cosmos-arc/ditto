import { useMarketOverview } from "../hooks";
import { MarketCard } from "@/components/domain/market-card/market-card";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ScrollReveal } from "@/components/ui/scroll-reveal";

function normalizeRegimeTag(regimeTag: string): "on" | "off" | "mixed" {
	if (regimeTag === "on" || regimeTag === "off" || regimeTag === "mixed") {
		return regimeTag;
	}
	return "mixed";
}

export function MarketCardGrid() {
	const { data, isLoading, refetch } = useMarketOverview();

	if (isLoading) {
		return (
			<div className="grid grid-cols-3 gap-3">
				{Array.from({ length: 6 }).map((_, i) => (
					<LoadingSkeleton key={i} variant="card" />
				))}
			</div>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
			<div className="grid grid-cols-3 gap-3" data-info-level="l1" data-info-unit="market-cards">
					{data.cards.map((card, index) => (
						<ScrollReveal key={card.indexCode} stagger={index % 3}>
							<MarketCard
								name={card.name}
								regime={normalizeRegimeTag(card.regimeTag)}
								index={card.price.toLocaleString()}
								change={card.change}
								judgment={card.driver}
							/>
						</ScrollReveal>
					))}
				</div>
			)}
		</DittoErrorBoundary>
	);
}
