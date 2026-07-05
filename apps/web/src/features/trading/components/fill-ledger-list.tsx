import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useFillLedger } from "../hooks";

const DIRECTION_VARIANT = {
	BUY: "trade",
	SELL: "risk",
} as const;

interface FillLedgerListProps {
	readonly enabled?: boolean;
}

export function FillLedgerList({ enabled = true }: FillLedgerListProps) {
	const { data, isLoading, refetch } = useFillLedger(undefined, { enabled });
	const fills = data?.fills ?? [];

	return (
		<ContextSection
			title="手工执行流水"
			count={fills.length}
			data-info-level="l1"
			data-info-unit="fill-ledger"
		>
			<div className="py-2">
				{isLoading && <LoadingSkeleton variant="table" rows={4} />}
				<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
					{!isLoading && fills.length === 0 && (
						<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-3 py-4 text-sm text-(--color-foreground-secondary)">
							尚未录入手工成交
						</div>
					)}
					{fills.length > 0 && (
						<div className="flex flex-col gap-1">
							{fills.map((fill) => (
								<div
									key={fill.id}
									className="grid grid-cols-[minmax(7rem,1fr)_minmax(7rem,1fr)_5rem_5rem_4rem] items-center gap-2 rounded-(--radius-sm) px-2 py-2 text-sm hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="min-w-0">
										<div className="truncate font-data text-(--color-foreground)">
											{fill.id}
										</div>
										<div className="truncate text-xs text-(--color-foreground-tertiary)">
											{fill.intentId}
										</div>
									</div>
									<div className="flex min-w-0 items-center gap-2">
										<StatusBadge
											variant={DIRECTION_VARIANT[fill.direction]}
											label={fill.direction}
											size="sm"
										/>
										<span className="truncate font-data text-(--color-foreground-secondary)">
											{fill.instrument}
										</span>
									</div>
									<span className="font-data tabular-nums text-(--color-foreground-tertiary)">
										{fill.quantity.toLocaleString()}
									</span>
									<span className="font-data tabular-nums text-(--color-foreground-tertiary)">
										¥{fill.fillPrice.toFixed(2)}
									</span>
									<span className="font-data tabular-nums text-(--color-foreground-tertiary)">
										¥{fill.fee.toFixed(2)}
									</span>
								</div>
							))}
						</div>
					)}
				</DittoErrorBoundary>
			</div>
		</ContextSection>
	);
}
