import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useRecentSignals } from "../hooks";

function formatTime(isoString: string): string {
	const date = new Date(isoString);
	return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

const SIGNAL_VARIANT: Record<string, "trade" | "research" | "risk"> = {
	BUY: "trade",
	SELL: "risk",
	HOLD: "research",
};

export function SignalsSection() {
	const { data, isLoading, refetch } = useRecentSignals();

	return (
		<ContextSection title="近期信号" count={data?.signals.length}>
			{isLoading && <LoadingSkeleton variant="table" rows={3} />}
			<DittoErrorBoundary
				fallbackProps={{
					title: "信号加载失败",
					onRetry: () => void refetch(),
				}}
			>
				{data && (
					<div className="space-y-1">
						{data.signals.map((signal, i) => (
							<div
								key={`${signal.ticker}-${i}`}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<StatusBadge variant={SIGNAL_VARIANT[signal.action] ?? "research"} label={signal.action} size="sm" />
									<span className="font-medium">{signal.ticker}</span>
								</div>
								<div className="flex items-center gap-3 text-(--color-foreground-tertiary)">
									<span>{signal.strategy}</span>
									<span>{signal.confidence}%</span>
									<span>{formatTime(signal.time)}</span>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
