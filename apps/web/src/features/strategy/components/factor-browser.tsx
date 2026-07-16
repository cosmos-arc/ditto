import { useFactorLibrary } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function FactorBrowser() {
	const { data, isLoading, refetch } = useFactorLibrary();

	return (
		<ContextSection title="因子库" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={8} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.items.map((factor) => (
							<div
								key={factor.id}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{factor.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">{factor.family}</span>
								</div>
								<span className="text-xs text-(--color-foreground-tertiary)">{factor.description}</span>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
