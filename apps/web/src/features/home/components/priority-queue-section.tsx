import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ScrollReveal } from "@/components/ui/scroll-reveal";
import { Panel, PanelBody, PanelHeader } from "@/features/shell";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import type { PendingAction } from "@/types";
import { usePendingActions } from "../hooks";

const PRIORITY_BAR_COLOR: Record<string, string> = {
	critical: "bg-(--color-risk-high-fg)",
	high: "bg-(--color-system-degraded-fg)",
	medium: "bg-(--color-foreground-muted)",
	low: "bg-(--color-foreground-disabled)",
};

const BADGE_COLOR: Record<string, string> = {
	signal: "bg-(--color-brand-500)/10 text-(--color-brand-400)",
	trading: "bg-(--color-brand-500)/10 text-(--color-brand-400)",
	risk: "bg-(--color-risk-high-fg)/10 text-(--color-risk-high-fg)",
	research: "bg-(--color-system-healthy-fg)/10 text-(--color-system-healthy-fg)",
	platform: "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)",
	data: "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)",
	priority: "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)",
	backtest: "bg-(--color-system-healthy-fg)/10 text-(--color-system-healthy-fg)",
	alert: "bg-(--color-risk-high-fg)/10 text-(--color-risk-high-fg)",
	factor: "bg-(--color-system-degraded-fg)/10 text-(--color-system-degraded-fg)",
	resource: "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)",
};

/**
 * PriorityQueueSection — "今日优先事项" panel.
 * Matches prototype .panel with .queue-item rows.
 * Each item has: colored priority bar | title+badges | meta | footer (domain + time)
 */
interface PriorityQueueSectionProps {
	readonly onSelectAction?: (action: PendingAction) => void;
}

export function PriorityQueueSection({ onSelectAction }: PriorityQueueSectionProps) {
	const { data, isLoading, refetch } = usePendingActions();

	return (
		<Panel
			data-testid="priority-queue"
			data-info-level="l1"
			data-info-unit="priority-queue"
			className="h-[329.5px] flex-none"
		>
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
						<ScrollReveal>
							<div className="flex flex-col">
								{data.actions.length === 0 && (
									<p className="px-3 py-4 text-sm text-(--color-foreground-tertiary)">当前没有待复核事项</p>
								)}
								{data.actions.map((action) => (
									<div
										key={action.id}
										data-slot="queue-item"
										className="flex gap-0 py-1.5 transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
									>
										{/* Priority bar */}
										<div
											className={`w-0.5 shrink-0 ${PRIORITY_BAR_COLOR[action.priority] ?? "bg-(--color-foreground-disabled)"}`}
										/>

										{/* Body */}
										<div className="flex min-w-0 flex-1 flex-col gap-1 px-3">
											<div className="flex items-center gap-1.5">
												<span className="truncate text-(length:--text-sm) font-medium text-(--color-foreground)">
													{action.title}
												</span>
												{action.badges.map((b) => (
													<span
														key={b.label}
														className={`shrink-0 rounded-[var(--radius-sm)] px-1.5 text-xs ${BADGE_COLOR[b.type] ?? "bg-(--color-foreground-muted)/10 text-(--color-foreground-muted)"}`}
													>
														{b.label}
													</span>
												))}
											</div>
											<span className="text-xs text-(--color-foreground-secondary)">{action.meta}</span>
											<div className="flex items-center justify-between pt-0.5">
												<span className="text-xs tabular-nums text-(--color-foreground-muted)">
													{action.domain} · {action.time}
												</span>
												<button
													type="button"
													onClick={() => onSelectAction?.(action)}
													className="text-xs text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) rounded-[var(--radius-sm)] px-1.5 py-0.5"
												>
													查看详情
												</button>
											</div>
										</div>
									</div>
								))}
							</div>
						</ScrollReveal>
					)}
				</DittoErrorBoundary>
			</PanelBody>
		</Panel>
	);
}
