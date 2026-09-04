import type { ExperimentListItem } from "@/types";
import type { ReviewQueueEntry } from "@/types/review";

const ACTIVE_STATUSES = new Set(["queued", "running", "pause_requested", "cancel_requested", "pausing", "cancelling"]);

export function ResearchActivityRail({
	experiments,
	reviews,
	onOpenRun,
	onOpenReview,
}: {
	readonly experiments: readonly ExperimentListItem[];
	readonly reviews: readonly ReviewQueueEntry[];
	readonly onOpenRun: (experiment: ExperimentListItem) => void;
	readonly onOpenReview: (review: ReviewQueueEntry) => void;
}) {
	return (
		<aside
			aria-label="研究活动"
			className="flex h-full min-h-0 flex-col border-l border-(--color-border-subtle) bg-(--color-surface-panel-base)"
			data-info-level="l1"
			data-info-unit="research-activity"
			data-testid="research-activity"
		>
			<section className="min-h-0 flex-1 overflow-y-auto border-b border-(--color-border-subtle)">
				<header className="sticky top-0 z-10 flex h-(--density-header-height) items-center justify-between bg-(--color-surface-strip) px-3 text-xs font-medium">
					<span>近期运行</span>
					<span className="font-data text-(--color-foreground-tertiary)">
						{experiments.filter((item) => ACTIVE_STATUSES.has(item.status.toLowerCase())).length} active
					</span>
				</header>
				{experiments.length === 0 ? (
					<p className="p-3 text-xs text-(--color-foreground-tertiary)">暂无实验运行。</p>
				) : (
					<div className="divide-y divide-(--color-border-subtle)">
						{experiments.slice(0, 6).map((item) => (
							<button
								key={item.experimentId}
								type="button"
								className="w-full px-3 py-2 text-left transition-colors hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-focus-ring)"
								onClick={() => onOpenRun(item)}
							>
								<div className="flex items-center justify-between gap-2 text-xs">
									<span className="truncate font-data font-medium text-(--color-foreground)">{item.experimentId}</span>
									<span className="shrink-0 text-(--color-foreground-tertiary)">{item.status}</span>
								</div>
								<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
									{item.stage} · r{item.revision}
								</p>
							</button>
						))}
					</div>
				)}
			</section>
			<section className="min-h-0 flex-1 overflow-y-auto">
				<header className="sticky top-0 z-10 flex h-(--density-header-height) items-center justify-between bg-(--color-surface-strip) px-3 text-xs font-medium">
					<span>审查队列</span>
					<span className="font-data text-(--color-foreground-tertiary)">{reviews.length}</span>
				</header>
				{reviews.length === 0 ? (
					<p className="p-3 text-xs text-(--color-foreground-tertiary)">暂无待审查版本。</p>
				) : (
					<div className="divide-y divide-(--color-border-subtle)">
						{reviews.slice(0, 6).map((item) => (
							<button
								key={`${item.strategyId}-${item.version}`}
								type="button"
								disabled={item.experimentId === null}
								className="w-full px-3 py-2 text-left transition-colors enabled:hover:bg-(--color-interaction-hover-subtle-bg) disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-(--color-focus-ring)"
								onClick={() => onOpenReview(item)}
							>
								<div className="flex items-center justify-between gap-2 text-xs">
									<span className="truncate font-data font-medium">
										{item.strategyId} · v{item.version}
									</span>
									<span className="shrink-0 text-(--color-foreground-tertiary)">{item.reviewOutcome}</span>
								</div>
								<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
									{item.experimentId ?? "尚无持久化 review packet"}
								</p>
							</button>
						))}
					</div>
				)}
			</section>
		</aside>
	);
}
