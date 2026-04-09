import { useCapitalRotation } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function CapitalRotationTable() {
	const { data, isLoading, isError, refetch } = useCapitalRotation();

	return (
		<ContextSection title="资金轮动">
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.sectors.map((sector) => (
							<div
								key={sector.name}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-surface-hover)"
							>
								<span className="font-medium">{sector.name}</span>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span className="text-(--color-status-success)">
										+{sector.netFlow.toFixed(1)}亿
									</span>
									<span>流入 {sector.inflow.toFixed(1)}亿</span>
									<span>流出 {sector.outflow.toFixed(1)}亿</span>
									{sector.rankChange !== 0 && (
										<span
											className={
												sector.rankChange > 0
													? "text-(--color-status-success)"
													: "text-(--color-status-error)"
											}
										>
											{sector.rankChange > 0 ? "↑" : "↓"}
										</span>
									)}
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
