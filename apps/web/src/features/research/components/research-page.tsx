import { Link } from "@tanstack/react-router";
import { Metric } from "@/components/data/metric";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { AnalyticalLayout } from "@/features/shell";
import { Panel, PanelBody, PanelHeader } from "@/features/shell/components/panel";
import { ApiError } from "@/lib/api-client";
import { useExperiments, useReviews } from "../hooks";

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
		<div className="flex flex-col gap-1 p-3 text-sm text-(--color-led-danger)">
			<p role="alert">{typedError(error)}</p>
			<button type="button" className="self-start underline" onClick={onRetry}>
				{label}
			</button>
		</div>
	);
}

export function ResearchPage() {
	const experiments = useExperiments();
	const reviews = useReviews();
	const experimentRows = experiments.data ?? [];
	const reviewRows = reviews.data ?? [];
	const activeCount = experimentRows.filter((entry) =>
		["queued", "running", "pausing", "cancelling"].includes(entry.status.toLowerCase()),
	).length;
	const approvedCount = reviewRows.filter((entry) => entry.reviewOutcome.toLowerCase() === "approved").length;

	return (
		<AnalyticalLayout
			strip={
				<div
					data-info-level="l1"
					data-info-unit="research-live-strip"
					className="grid grid-cols-2 gap-2 p-2 md:grid-cols-4"
				>
					<Metric variant="strip" label="实验总数" value={experiments.isLoading ? "…" : experimentRows.length} />
					<Metric variant="strip" label="运行中" value={experiments.isLoading ? "…" : activeCount} />
					<Metric variant="strip" label="审查队列" value={reviews.isLoading ? "…" : reviewRows.length} />
					<Metric variant="strip" label="已批准待发布" value={reviews.isLoading ? "…" : approvedCount} />
				</div>
			}
			main={
				<div data-info-level="l1" data-info-unit="live-experiment-catalog" className="p-(--density-panel-padding)">
					<Panel>
						<PanelHeader
							title="研究实验"
							count={experimentRows.length}
							actions={
								<Link
									to="/research/experiments/new"
									className="rounded-(--radius-sm) bg-(--brand-accent) px-2.5 py-1.5 text-xs font-medium text-(--brand-accent-fg)"
								>
									创建实验
								</Link>
							}
						/>
						<PanelBody className="p-0">
							{experiments.error ? (
								<ResourceError
									error={experiments.error}
									label="重试实验目录"
									onRetry={() => void experiments.refetch()}
								/>
							) : experiments.isLoading ? (
								<LoadingSkeleton variant="table" rows={6} />
							) : experimentRows.length === 0 ? (
								<p className="p-3 text-sm text-(--color-foreground-tertiary)">
									暂无实验。先创建实验并完成只读 preflight。
								</p>
							) : (
								<div className="divide-y divide-(--color-border-subtle)">
									{experimentRows.slice(0, 12).map((entry) => (
										<Link
											key={entry.experimentId}
											to="/research/experiments/$id"
											params={{ id: entry.experimentId }}
											className="grid gap-1 px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg) sm:grid-cols-[1fr_7rem_7rem_5rem] sm:items-center"
										>
											<span className="font-data font-medium">{entry.experimentId}</span>
											<span className="text-(--color-foreground-secondary)">{entry.status}</span>
											<span className="text-(--color-foreground-secondary)">{entry.stage}</span>
											<span className="font-data text-(--color-foreground-tertiary)">r{entry.revision}</span>
										</Link>
									))}
								</div>
							)}
						</PanelBody>
					</Panel>
				</div>
			}
			activity={
				<div
					data-info-level="l1"
					data-info-unit="research-governance-queue"
					className="p-(--density-panel-padding) pl-0 max-md:pl-(--density-panel-padding)"
				>
					<Panel>
						<PanelHeader title="治理审查" count={reviewRows.length} />
						<PanelBody className="p-0">
							{reviews.error ? (
								<ResourceError error={reviews.error} label="重试审查队列" onRetry={() => void reviews.refetch()} />
							) : reviews.isLoading ? (
								<LoadingSkeleton variant="table" rows={4} />
							) : reviewRows.length === 0 ? (
								<p className="p-3 text-sm text-(--color-foreground-tertiary)">暂无待审查版本。</p>
							) : (
								<div className="divide-y divide-(--color-border-subtle)">
									{reviewRows.slice(0, 8).map((entry) =>
										entry.experimentId ? (
											<Link
												key={`${entry.strategyId}-${entry.version}`}
												to="/research/reviews/$id"
												params={{ id: entry.experimentId }}
												search={{ strategyId: entry.strategyId, version: entry.version }}
												className="block px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
											>
												<p className="font-data">
													{entry.strategyId} · v{entry.version}
												</p>
												<p className="text-xs text-(--color-foreground-tertiary)">
													{entry.state} · {entry.reviewOutcome}
												</p>
											</Link>
										) : (
											<div key={`${entry.strategyId}-${entry.version}`} className="px-3 py-2 text-sm opacity-50">
												<p className="font-data">
													{entry.strategyId} · v{entry.version}
												</p>
												<p className="text-xs">尚无持久化 review packet</p>
											</div>
										),
									)}
								</div>
							)}
						</PanelBody>
					</Panel>
				</div>
			}
			analysis={
				<nav
					aria-label="研究工作区"
					data-info-level="l2"
					data-info-unit="research-workspace-navigation"
					className="flex flex-wrap gap-2 border-t border-(--color-border-subtle) p-3 text-xs"
				>
					<Link
						className="rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-1"
						to="/research/factors"
					>
						因子目录
					</Link>
					<Link
						className="rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-1"
						to="/research/strategies"
					>
						策略目录
					</Link>
					<Link
						className="rounded-(--radius-sm) border border-(--color-border-subtle) px-2 py-1"
						to="/research/reviews"
					>
						完整审查队列
					</Link>
				</nav>
			}
		/>
	);
}
