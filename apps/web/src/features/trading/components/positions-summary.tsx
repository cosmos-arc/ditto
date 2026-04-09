import { usePositions } from "../hooks";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function PositionsSummary() {
	const { data, isLoading, isError, refetch } = usePositions();

	return (
		<ContextSection title="持仓汇总" count={data?.positions.length}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.positions.map((pos) => (
							<div
								key={pos.code}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-surface-hover)"
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{pos.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">{pos.code}</span>
									{pos.frozenQty > 0 && (
										<StatusBadge variant="warning" label={`冻结 ${pos.frozenQty.toLocaleString()}`} size="sm" />
									)}
								</div>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span>{pos.qty.toLocaleString()} 股</span>
									<span
										className={
											pos.pnl >= 0
												? "text-(--color-status-success)"
												: "text-(--color-status-error)"
										}
									>
										{pos.pnl >= 0 ? "+" : ""}
										{pos.pnl.toLocaleString()}
									</span>
									<span
										className={
											pos.pnlPercent >= 0
												? "text-(--color-status-success)"
												: "text-(--color-status-error)"
										}
									>
										{pos.pnlPercent >= 0 ? "+" : ""}
										{pos.pnlPercent.toFixed(2)}%
									</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
