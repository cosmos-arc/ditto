import { useMarketOverview } from "../hooks";
import { MarketCard } from "@/components/domain/market-card/market-card";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ScrollReveal } from "@/components/ui/scroll-reveal";

export function MarketCardGrid() {
	const { data, isLoading, isError, refetch } = useMarketOverview();

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
				<div className="grid grid-cols-3 gap-3">
					{data.cards.map((card, index) => (
						<ScrollReveal key={card.indexCode} stagger={index % 3}>
							<MarketCard
								name={card.name}
								regime={card.regimeTag}
								index={card.price}
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
