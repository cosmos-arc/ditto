import { useRiskExposure } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function RiskExposureSummary() {
	const { data, isLoading, refetch } = useRiskExposure();

	return (
		<ContextSection title="敞口概览">
			{isLoading && <LoadingSkeleton variant="metric" rows={2} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-4">
						<div data-info-level="l1" data-info-unit="exposure-metrics" className="grid grid-cols-2 gap-3">
							<div className="rounded-md border border-(--color-border-subtle) p-3">
								<span className="text-xs text-(--color-foreground-tertiary)">总敞口</span>
								<span className="ml-2 font-medium tabular-nums">{data.grossExposure}%</span>
							</div>
							<div className="rounded-md border border-(--color-border-subtle) p-3">
								<span className="text-xs text-(--color-foreground-tertiary)">净敞口</span>
								<span className="ml-2 font-medium tabular-nums">{data.netExposure}%</span>
							</div>
						</div>
						<div data-info-level="l1" data-info-unit="sector-breakdown" className="space-y-1">
							<span className="text-xs font-medium text-(--color-foreground-tertiary)">板块分布</span>
							{data.bySector.map((sector) => (
								<div
									key={sector.name}
									className="flex items-center justify-between rounded-md px-3 py-1.5 text-sm"
								>
									<span>{sector.name}</span>
									<div className="flex gap-3 text-xs text-(--color-foreground-tertiary)">
										<span>多 {sector.long}%</span>
										<span>空 {sector.short}%</span>
										<span className="font-medium">净 {sector.net}%</span>
									</div>
								</div>
							))}
						</div>
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
