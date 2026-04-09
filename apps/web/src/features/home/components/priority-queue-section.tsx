import { usePendingActions } from "../hooks";
import { Panel, PanelHeader, PanelBody } from "@/features/shell/components/panel";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

const PRIORITY_BAR_COLOR: Record<string, string> = {
	critical: "bg-(--color-risk-high-fg)",
	high: "bg-(--color-system-degraded-fg)",
	medium: "bg-(--color-foreground-muted)",
	low: "bg-(--color-foreground-disabled)",
};

const BADGE_COLOR: Record<string, string> = {
	signal: "bg-(--color-brand-500)/10 text-(--color-brand-400)",
	backtest: "bg-(--color-system-healthy-fg)/10 text-(--color-system-healthy-fg)",
	alert: "bg-(--color-risk-high-fg)/10 text-(--color-risk-high-fg)",
	factor: "bg-(--color-system-degraded-fg)/10 text-(--color-system-degraded-fg)",
	resource: "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)",
};

function formatTime(isoString: string): string {
	const date = new Date(isoString);
	const now = new Date();
	const diffMs = now.getTime() - date.getTime();
	const diffMin = Math.floor(diffMs / 60000);
	if (diffMin < 60) return `${diffMin}分钟前`;
	const diffHr = Math.floor(diffMin / 60);
	if (diffHr < 24) return `${diffHr}小时前`;
	return `${Math.floor(diffHr / 24)}天前`;
}

/**
 * PriorityQueueSection — "今日优先事项" panel.
 * Matches prototype .panel with .queue-item rows.
 * Each item has: colored priority bar | title+reason | footer (source + time)
 */
export function PriorityQueueSection() {
	const { data, isLoading, isError, refetch } = usePendingActions();

	return (
		<Panel className="flex-1">
			<PanelHeader
				title="今日优先事项"
				subtitle="跨域关注项"
				count={data?.actions.length}
				actions={
					<button
						type="button"
						className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
					>
						查看全部 →
					</button>
				}
			/>
			<PanelBody>
				{isLoading && <LoadingSkeleton variant="table" rows={4} />}
				<DittoErrorBoundary
					fallbackProps={{
						title: "待处理事项加载失败",
						onRetry: () => void refetch(),
					}}
				>
					{data && (
						<div className="flex flex-col">
							{data.actions.map((action) => (
								<div
									key={action.id}
									className="flex gap-0 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
								>
									{/* Priority bar */}
									<div
										className={`w-0.5 shrink-0 ${PRIORITY_BAR_COLOR[action.priority] ?? "bg-(--color-foreground-disabled)"}`}
									/>

									{/* Body */}
									<div className="flex min-w-0 flex-1 flex-col gap-0.5 px-3">
										<div className="flex items-center gap-1.5">
											<span className="truncate text-xs font-medium text-(--color-foreground)">
												{action.title}
											</span>
											<span className={`shrink-0 rounded-[var(--radius-sm)] px-1.5 text-[10px] ${BADGE_COLOR[action.badge.type] ?? "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)"}`}>
												{action.badge.label}
											</span>
										</div>
										<span className="text-xs text-(--color-foreground-tertiary)">
											{action.meta}
										</span>
										<div className="flex items-center justify-between pt-0.5">
											<span className="text-xs tabular-nums text-(--color-foreground-muted)">
												{action.domain} · {formatTime(action.time)}
											</span>
											<button
												type="button"
												className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
											>
												查看详情
											</button>
										</div>
									</div>
								</div>
							))}
						</div>
					)}
				</DittoErrorBoundary>
			</PanelBody>
		</Panel>
	);
}
