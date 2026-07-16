import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { useSignals } from "../hooks";

const DIRECTION_VARIANT: Record<string, "trade" | "risk" | "research"> = {
	BUY: "trade",
	SELL: "risk",
	HOLD: "research",
};

const STATUS_VARIANT: Record<string, "healthy" | "warning" | "default" | "degraded"> = {
	pending: "warning",
	confirmed: "healthy",
	ignored: "default",
	ordered: "degraded",
};

interface SignalsListProps {
	readonly onSelectSignal?: (signalId: string) => void;
}

export function SignalsList({ onSelectSignal }: SignalsListProps) {
	const { data, isLoading, isError, refetch } = useSignals({ tab: "pending" });

	return (
		<ContextSection title="信号队列" count={data?.total} data-info-level="l1" data-info-unit="signals-list">
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			{isError && (
				<div
					role="alert"
					className="flex items-center justify-between rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm"
				>
					<span>信号队列加载失败</span>
					<Button variant="outline" size="sm" onClick={() => void refetch()}>
						重试
					</Button>
				</div>
			)}
			{!isLoading && !isError && data?.items.length === 0 && (
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-4 text-sm text-(--color-foreground-secondary)">
					暂无待复核建议
				</div>
			)}
			{data && data.items.length > 0 && (
				<div className="space-y-1">
					{data.items.map((signal) => (
						<button
							key={signal.id}
							type="button"
							className="flex w-full flex-col items-start gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg) sm:flex-row sm:items-center sm:justify-between"
							onClick={onSelectSignal ? () => onSelectSignal(signal.id) : undefined}
						>
							<div className="flex min-w-0 flex-wrap items-center gap-2">
								<StatusBadge
									variant={DIRECTION_VARIANT[signal.direction] ?? "default"}
									label={signal.direction}
									size="sm"
								/>
								<span className="text-xs text-(--color-foreground-tertiary)">{signal.instrument}</span>
								<span className="font-medium">{signal.source}</span>
								<StatusBadge variant={STATUS_VARIANT[signal.status] ?? "default"} label={signal.status} size="sm" />
							</div>
							<div className="flex w-full items-center justify-between gap-3 text-(--color-foreground-tertiary) sm:w-auto sm:justify-start">
								<span>权重 {signal.weight.toFixed(2)}</span>
								{signal.confidence != null && (
									<span className="font-medium">{(signal.confidence * 100).toFixed(0)}%</span>
								)}
							</div>
						</button>
					))}
				</div>
			)}
		</ContextSection>
	);
}
