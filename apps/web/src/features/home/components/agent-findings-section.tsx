import { useRecentSignals } from "../hooks";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const SIGNAL_BADGE: Record<string, string> = {
	BUY: "bg-(--color-market-up-fg)/10 text-(--color-market-up-fg)",
	SELL: "bg-(--color-market-down-fg)/10 text-(--color-market-down-fg)",
	HOLD: "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)",
};

/**
 * AgentFindingsSection — "Agent 洞察" findings feed.
 * Matches prototype .findings-feed with .finding-item rows.
 * Reuses recent signals data for now.
 */
export function AgentFindingsSection() {
	const { data, isLoading, isError, refetch } = useRecentSignals();

	return (
		<div className="flex min-h-0 flex-col overflow-hidden">
			<div className="flex items-center justify-between border-b border-(--color-border-subtle) px-3 py-2">
				<span className="text-xs font-medium text-(--color-foreground)">
					Agent 洞察
					<span className="ml-2 font-normal text-(--color-foreground-tertiary)">关联分析</span>
				</span>
			</div>
			<div className="flex-1 overflow-y-auto px-3 py-2">
				{isLoading && <LoadingSkeleton variant="table" rows={3} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "Agent 洞察加载失败",
						onRetry: () => void refetch(),
					}}
				>
					{data && (
						<div className="flex flex-col gap-1">
							{data.signals.map((signal, i) => (
								<div
									key={`${signal.ticker}-${i}`}
									className="rounded-[var(--radius-sm)] px-2 py-1 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									<div className="flex items-center gap-1.5">
										<span className={`shrink-0 rounded-[var(--radius-sm)] px-1.5 text-[10px] ${SIGNAL_BADGE[signal.action] ?? ""}`}>
											{signal.action}
										</span>
										<span className="text-xs text-(--color-foreground)">
											{signal.ticker}
										</span>
									</div>
									<p className="mt-0.5 text-xs text-(--color-foreground-tertiary)">
										{signal.strategy} · 置信度 {signal.confidence}%
									</p>
								</div>
							))}
							<div className="pt-1">
								<button
									type="button"
									className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
								>
									展开全部 Agent 分析 →
								</button>
							</div>
						</div>
					)}
				</DittoErrorBoundary>
			</div>
		</div>
	);
}
