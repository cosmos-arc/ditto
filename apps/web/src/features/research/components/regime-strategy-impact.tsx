import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useRegimeStrategyImpact } from "../hooks";

export function RegimeStrategyImpact() {
	const { data, isLoading, refetch } = useRegimeStrategyImpact();

	if (isLoading) {
		return (
			<ContextSection title="策略影响">
				<LoadingSkeleton variant="table" rows={3} columns={3} />
			</ContextSection>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextSection title="策略影响">
				{data?.strategies.map((strat) => (
					<div key={strat.id} className="flex flex-col gap-1 border-b border-(--color-border) py-2 last:border-b-0">
						<div className="flex items-center justify-between">
							<span className="text-sm font-medium text-(--color-foreground)">{strat.name}</span>
							<span
								className={`text-sm font-data ${strat.performance >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}`}
							>
								{strat.performance > 0 ? "+" : ""}
								{strat.performance}%
							</span>
						</div>
						<p className="text-xs text-(--color-foreground-tertiary)">适配度 — {strat.adjustmentSuggestion}</p>
					</div>
				))}
			</ContextSection>
		</DittoErrorBoundary>
	);
}
