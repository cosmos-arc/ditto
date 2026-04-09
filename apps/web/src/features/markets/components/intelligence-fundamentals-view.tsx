import { useIntelligenceFundamentals } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function IntelligenceFundamentalsView() {
	const { data, isLoading, refetch } = useIntelligenceFundamentals();

	if (isLoading) {
		return (
			<ContextSection title="基本面">
				<LoadingSkeleton variant="table" rows={3} columns={3} />
			</ContextSection>
		);
	}

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<ContextSection title="基本面">
				{data && (
					<div className="flex flex-col gap-3">
						<div className="flex flex-col gap-1">
							<span className="text-xs text-(--color-foreground-tertiary)">评级变动</span>
							{data.ratingChanges.map((rc) => (
								<div
									key={`${rc.date}-${rc.code}`}
									className="flex items-center justify-between py-1 border-b border-(--color-border) last:border-b-0"
								>
									<div className="flex flex-col gap-0.5 min-w-0">
										<span className="text-sm text-(--color-foreground)">
											{rc.name}
										</span>
										<span className="text-xs text-(--color-foreground-tertiary)">
											{rc.org} · {rc.action}
										</span>
									</div>
									<span className="text-xs text-(--color-foreground-secondary) font-medium shrink-0">
										{rc.rating}
									</span>
								</div>
							))}
						</div>
						<div className="flex flex-col gap-1">
							<span className="text-xs text-(--color-foreground-tertiary)">盈利预测</span>
							{data.earningsEstimates.map((est) => (
								<div
									key={est.code}
									className="flex items-center justify-between py-1 border-b border-(--color-border) last:border-b-0"
								>
									<span className="text-sm text-(--color-foreground)">{est.name}</span>
									<span className="text-xs text-(--color-foreground-secondary) font-data">
										FY1 {est.epsFY1} / FY2 {est.epsFY2}
									</span>
								</div>
							))}
						</div>
					</div>
				)}
			</ContextSection>
		</DittoErrorBoundary>
	);
}
