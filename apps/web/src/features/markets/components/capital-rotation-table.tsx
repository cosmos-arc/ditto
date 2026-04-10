import { useCapitalRotation } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { FlowBar } from "@/components/data";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { cn } from "@/lib/utils";

const NUMERIC = "font-data tabular-nums";

export function CapitalRotationTable() {
	const { data, isLoading, refetch } = useCapitalRotation();

	return (
		<ContextSection title="资金轮动">
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.sectors.map((sector) => (
							<div
								key={sector.name}
								className="rounded-md px-3 py-2 transition-colors hover:bg-(--color-surface-hover)"
							>
								<div className="flex items-center justify-between text-sm">
									<span className="font-medium">{sector.name}</span>
									<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
										<span className={cn(NUMERIC, "text-(--color-status-success)")}>
											+{sector.netFlow.toFixed(1)}亿
										</span>
										<span className={NUMERIC}>
											流入 {sector.inflow.toFixed(1)}亿
										</span>
										<span className={NUMERIC}>
											流出 {sector.outflow.toFixed(1)}亿
										</span>
										{sector.rankChange !== 0 && (
											<span
												className={cn(
													sector.rankChange > 0
														? "text-(--color-status-success)"
														: "text-(--color-status-error)",
												)}
											>
												{sector.rankChange > 0 ? "↑" : "↓"}
											</span>
										)}
									</div>
								</div>
								<FlowBar
									segments={[
										{ value: sector.inflow, label: "流入", color: "var(--color-market-up)" },
										{ value: sector.outflow, label: "流出", color: "var(--color-market-down)" },
									]}
									height={4}
								/>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
