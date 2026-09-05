import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useFactorAnalysis } from "../hooks";

interface FactorAnalysisViewProps {
	readonly id: string;
}

export function FactorAnalysisView({ id }: FactorAnalysisViewProps) {
	const { data, isLoading, refetch } = useFactorAnalysis(id);

	if (isLoading) {
		return <LoadingSkeleton variant="table" rows={8} />;
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			{data && (
				<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
					<ContextSection title="IC 时序" count={data.icTimeSeries.length}>
						<div className="space-y-1">
							{data.icTimeSeries.map((point) => (
								<div
									key={point.date}
									className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<span className="text-(--color-foreground-tertiary)">{point.date}</span>
									<span className="font-mono">IC {point.ic.toFixed(3)}</span>
									<span className="font-mono">IR {point.ir.toFixed(2)}</span>
								</div>
							))}
						</div>
					</ContextSection>

					<ContextSection title="行业暴露" count={data.sectorExposure.length}>
						<div className="space-y-1">
							{data.sectorExposure.map((item) => (
								<div
									key={item.sector}
									className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<span className="font-medium">{item.sector}</span>
									<span className={item.exposure >= 0 ? "text-(--color-led-success)" : "text-(--color-led-error)"}>
										{item.exposure > 0 ? "+" : ""}
										{item.exposure.toFixed(2)}
									</span>
								</div>
							))}
						</div>
					</ContextSection>
				</div>
			)}
		</DittoErrorBoundary>
	);
}
