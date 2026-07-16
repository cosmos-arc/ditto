import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { MarketCard } from "@/components/domain/market-card/market-card";
import { ScrollReveal } from "@/components/ui/scroll-reveal";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useMarketOverview } from "../hooks";

const LOADING_CARD_IDS = ["market-1", "market-2", "market-3", "market-4", "market-5", "market-6"] as const;

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
				{LOADING_CARD_IDS.map((cardId) => (
					<LoadingSkeleton key={cardId} variant="card" />
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
