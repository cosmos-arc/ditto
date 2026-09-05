import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { ApiError } from "@/api";
import { AnalyticalLayout, ShellHeaderExtension } from "@/features/shell";
import type { ExperimentListItem } from "@/types";
import type { ReviewQueueEntry } from "@/types/review";
import { useExperiments, useFactorCatalog, useReviews } from "../hooks";
import { ResearchActivityRail } from "./research-activity-rail";
import { ResearchAnalysisBand } from "./research-analysis-band";
import { ResearchFactorMonitor } from "./research-factor-monitor";
import { type ResearchOverlayId, ResearchOverlays } from "./research-overlays";

function typedError(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "RESEARCH_RESOURCE_ERROR"}: ${error.message}`
		: error.message;
}

function ResourceError({
	error,
	label,
	onRetry,
}: {
	readonly error: Error;
	readonly label: string;
	readonly onRetry: () => void;
}) {
	return (
		<div className="flex flex-col gap-1 border-b border-(--color-border-subtle) p-3 text-xs text-(--color-led-danger)">
			<p role="alert">{typedError(error)}</p>
			<button type="button" className="self-start underline" onClick={onRetry}>
				{label}
			</button>
		</div>
	);
}

const ACTIVE_STATUSES = new Set(["queued", "running", "pause_requested", "cancel_requested", "pausing", "cancelling"]);

export function ResearchPage() {
	const factors = useFactorCatalog();
	const experiments = useExperiments();
	const reviews = useReviews();
	const factorRows = factors.data ?? [];
	const experimentRows = experiments.data ?? [];
	const reviewRows = reviews.data ?? [];
	const [activeOverlay, setActiveOverlay] = useState<ResearchOverlayId | null>(null);
	const [selectedExperiment, setSelectedExperiment] = useState<ExperimentListItem | null>(null);
	const [selectedReview, setSelectedReview] = useState<ReviewQueueEntry | null>(null);

	const activeRuns = experimentRows.filter((entry) => ACTIVE_STATUSES.has(entry.status.toLowerCase())).length;
	const degradingFactors = factorRows.filter((entry) => entry.diagnosticPreview?.status === "degrading").length;
	const evaluatedFactors = factorRows.filter((entry) => entry.diagnosticPreview !== null).length;
	const synchronized = !factors.isFetching && !experiments.isFetching && !reviews.isFetching;
	const primaryAnswer =
		degradingFactors > 0
			? `优先诊断 ${degradingFactors} 个 IC 退化因子`
			: factorRows.length > 0
				? `${factorRows.length} 个受控因子等待证据范围`
				: "研究目录等待同步";

	function openRun(experiment: ExperimentListItem) {
		setSelectedExperiment(experiment);
		setSelectedReview(null);
		setActiveOverlay("run-detail");
	}

	function openReview(review: ReviewQueueEntry) {
		if (review.experimentId === null) return;
		setSelectedReview(review);
		setSelectedExperiment(null);
		setActiveOverlay("review-action");
	}

	return (
		<>
			<ShellHeaderExtension>
				<div className="mx-auto flex items-center gap-1.5">
					<button
						type="button"
						className="h-(--density-action-height) rounded-(--radius-sm) bg-(--brand-accent) px-2.5 text-xs font-medium text-(--brand-accent-fg)"
						onClick={() => setActiveOverlay("new-backtest")}
					>
						新建回测
					</button>
					<button
						type="button"
						className="h-(--density-action-height) rounded-(--radius-sm) border border-(--color-border) px-2.5 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
						onClick={() => setActiveOverlay("new-strategy")}
					>
						新建策略
					</button>
					<button
						type="button"
						className="h-(--density-action-height) rounded-(--radius-sm) border border-(--color-border) px-2.5 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
						onClick={() => setActiveOverlay("new-experiment")}
					>
						新建实验
					</button>
					<Link
						to="/research/factors"
						className="px-2 py-1 text-xs text-(--color-foreground-secondary) hover:text-(--color-foreground)"
					>
						进入因子分析
					</Link>
				</div>
			</ShellHeaderExtension>

			<AnalyticalLayout
				className="[--height-analysis-band:180px]"
				strip={
					<section
						aria-label="研究证据范围"
						data-info-level="l1"
						data-info-unit="research-scope-strip"
						data-state={synchronized ? "fresh" : "stale"}
						className="grid h-(--density-strip-height) grid-cols-[minmax(15rem,1.45fr)_repeat(4,minmax(6rem,0.65fr))] items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 max-xl:grid-cols-[minmax(14rem,1fr)_repeat(2,minmax(6rem,0.55fr))]"
					>
						<div className="flex min-w-0 items-baseline gap-2">
							<p className="shrink-0 truncate text-xs font-semibold text-(--color-foreground)">{primaryAnswer}</p>
							<p className="truncate text-xs text-(--color-foreground-tertiary)">请选择实验与折叠窗口后读取诊断证据</p>
						</div>
						<div className="flex items-baseline justify-end gap-1.5">
							<p className="text-xs text-(--color-foreground-tertiary)">受控因子</p>
							<p className="font-data text-sm tabular-nums">{factors.isLoading ? "…" : factorRows.length}</p>
						</div>
						<div className="flex items-baseline justify-end gap-1.5">
							<p className="text-xs text-(--color-foreground-tertiary)">已评估</p>
							<p className="font-data text-sm tabular-nums">{factors.isLoading ? "…" : evaluatedFactors}</p>
						</div>
						<div className="flex items-baseline justify-end gap-1.5 max-xl:hidden">
							<p className="text-xs text-(--color-foreground-tertiary)">活跃运行</p>
							<p className="font-data text-sm tabular-nums">{experiments.isLoading ? "…" : activeRuns}</p>
						</div>
						<div className="flex items-baseline justify-end gap-1.5 max-xl:hidden">
							<p className="text-xs text-(--color-foreground-tertiary)">审查队列</p>
							<p className="font-data text-sm tabular-nums">{reviews.isLoading ? "…" : reviewRows.length}</p>
						</div>
					</section>
				}
				main={
					<div className="h-full min-h-0 p-(--density-panel-padding)">
						<ResearchFactorMonitor
							rows={factorRows}
							isLoading={factors.isLoading}
							error={factors.error}
							onRetry={() => void factors.refetch()}
						/>
					</div>
				}
				activity={
					<div className="h-full min-h-0">
						{experiments.error && (
							<ResourceError
								error={experiments.error}
								label="重试实验目录"
								onRetry={() => void experiments.refetch()}
							/>
						)}
						{reviews.error && (
							<ResourceError error={reviews.error} label="重试审查队列" onRetry={() => void reviews.refetch()} />
						)}
						<ResearchActivityRail
							experiments={experimentRows}
							reviews={reviewRows}
							onOpenRun={openRun}
							onOpenReview={openReview}
						/>
					</div>
				}
				analysis={<ResearchAnalysisBand factors={factorRows} />}
			/>

			<ResearchOverlays
				active={activeOverlay}
				onClose={() => setActiveOverlay(null)}
				experiment={selectedExperiment}
				review={selectedReview}
			/>
		</>
	);
}
