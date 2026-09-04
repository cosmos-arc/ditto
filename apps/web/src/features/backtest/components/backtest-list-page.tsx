import { useMemo, useState } from "react";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import { useBacktestRuns } from "../hooks";
import type { BacktestRun } from "../types";
import { BacktestCompareOverlay } from "./backtest-overlays";

const compareAction = [{ id: "compare", label: "回测对比" }] as const;

function statusVariant(status: string): "healthy" | "warning" | "critical" | "idle" {
	switch (status.toLowerCase()) {
		case "completed":
			return "healthy";
		case "running":
			return "warning";
		case "failed":
		case "cancelled":
			return "critical";
		default:
			return "idle";
	}
}

function errorText(error: Error | null): string | null {
	if (!error) return null;
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "BACKTEST_RUNS_ERROR"}: ${error.message}`
		: error.message;
}

function RunSummary({ run }: { readonly run: BacktestRun }) {
	return (
		<div className="flex flex-col gap-(--section-gap)">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<h2 className="break-all font-data text-sm font-semibold text-(--color-foreground)">{run.runId}</h2>
					<p className="mt-1 break-all text-xs text-(--color-foreground-secondary)">
						{run.strategyId} · v{run.strategyVersion || "未报告"}
					</p>
				</div>
				<StatusBadge label={run.status} variant={statusVariant(run.status)} size="sm" />
			</div>
			<dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 border-y border-(--color-border-subtle) py-3 text-xs">
				<dt className="text-(--color-foreground-tertiary)">Progress</dt>
				<dd className="font-data text-(--color-foreground)">{run.progressPct}%</dd>
				<dt className="text-(--color-foreground-tertiary)">Current step</dt>
				<dd className="break-all font-data text-(--color-foreground-secondary)">{run.currentStep || "未报告"}</dd>
				<dt className="text-(--color-foreground-tertiary)">Days</dt>
				<dd className="font-data text-(--color-foreground-secondary)">
					{run.completedDays} / {run.totalDays || "未报告"}
				</dd>
				<dt className="text-(--color-foreground-tertiary)">Benchmark</dt>
				<dd className="font-data text-(--color-foreground-secondary)">
					{run.benchmarkReturn === null ? "未发布" : `${run.benchmarkReturn}%`}
				</dd>
				<dt className="text-(--color-foreground-tertiary)">Started</dt>
				<dd className="font-data text-(--color-foreground-secondary)">{run.startedAt || "未报告"}</dd>
				<dt className="text-(--color-foreground-tertiary)">Completed</dt>
				<dd className="font-data text-(--color-foreground-secondary)">{run.completedAt || "尚未完成"}</dd>
			</dl>
			{run.errorMessage && (
				<p className="rounded-(--radius-sm) border border-(--color-led-danger) p-3 text-xs text-(--color-led-danger)">
					{run.errorMessage}
				</p>
			)}
			<a
				href={`/research/backtests/${encodeURIComponent(run.runId)}`}
				className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
			>
				打开回测结果
			</a>
		</div>
	);
}

export function BacktestListPage() {
	const query = useBacktestRuns();
	const runs = query.data ?? [];
	const [search, setSearch] = useState("");
	const [status, setStatus] = useState("all");
	const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
	const [compareOpen, setCompareOpen] = useState(false);
	const statuses = useMemo(() => [...new Set(runs.map((run) => run.status))].sort(), [runs]);
	const filtered = useMemo(() => {
		const needle = search.trim().toLowerCase();
		return runs.filter(
			(run) =>
				(status === "all" || run.status === status) &&
				(!needle ||
					run.runId.toLowerCase().includes(needle) ||
					run.strategyId.toLowerCase().includes(needle) ||
					run.status.toLowerCase().includes(needle)),
		);
	}, [runs, search, status]);
	const selected = filtered.find((run) => run.runId === selectedRunId) ?? filtered[0] ?? null;
	const completedCount = runs.filter((run) => run.status === "completed").length;
	const runningCount = runs.filter((run) => run.status === "running").length;
	const compareIds = [selected?.runId, ...runs.map((run) => run.runId)]
		.filter((value): value is string => Boolean(value))
		.filter((value, index, values) => values.indexOf(value) === index)
		.slice(0, 2);

	return (
		<section aria-label="受控回测目录" className="h-full min-h-0">
			<CatalogLayout
				className="max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_1fr] max-[899px]:[grid-template-areas:'toolbar''main']"
				toolbar={
					<div className="flex h-12 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<div className="min-w-0">
							<p className="text-sm font-medium text-(--color-foreground)">回测目录</p>
							<p className="hidden text-xs text-(--color-foreground-tertiary) 2xl:block">
								run identity · progress · benchmark publication
							</p>
						</div>
						<label className="ml-auto min-w-48 max-w-72 flex-1">
							<span className="sr-only">搜索回测运行</span>
							<input
								type="search"
								aria-label="搜索回测运行"
								value={search}
								onChange={(event) => setSearch(event.currentTarget.value)}
								placeholder="run / strategy / status"
								className="h-8 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-3 text-xs outline-none focus:border-(--color-border-strong)"
							/>
						</label>
						<select
							aria-label="按状态筛选回测"
							value={status}
							onChange={(event) => setStatus(event.currentTarget.value)}
							className="h-8 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-2 text-xs"
						>
							<option value="all">全部状态</option>
							{statuses.map((value) => (
								<option key={value} value={value}>
									{value}
								</option>
							))}
						</select>
						<PageActionBar ariaLabel="回测目录操作" actions={compareAction} onOpen={() => setCompareOpen(true)} />
					</div>
				}
				main={
					<Panel className="m-3 h-[calc(100%-1.5rem)]">
						<PanelHeader
							title="Backtest Runs"
							count={filtered.length}
							actions={
								<span className="font-data text-xs text-(--color-foreground-tertiary)">
									{completedCount} completed · {runningCount} running
								</span>
							}
						/>
						<PanelBody className="p-0">
							<div className="grid grid-cols-[minmax(11rem,1.2fr)_minmax(12rem,1.5fr)_6rem_6rem_8rem] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
								<span>Run</span>
								<span>Strategy version</span>
								<span>Status</span>
								<span>Progress</span>
								<span>Started</span>
							</div>
							{query.error ? (
								<div className="flex flex-col items-start gap-2 p-4 text-xs text-(--color-led-danger)">
									<p role="alert">{errorText(query.error)}</p>
									<Button size="sm" variant="outline" onClick={() => void query.refetch()}>
										重试回测目录
									</Button>
								</div>
							) : query.isLoading && runs.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">正在加载回测运行…</p>
							) : filtered.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">当前筛选下没有回测运行。</p>
							) : (
								<div className="divide-y divide-(--color-border-subtle)">
									{filtered.map((run) => {
										const isSelected = selected === run;
										return (
											<button
												key={run.runId}
												type="button"
												aria-label={`选择回测 ${run.runId}`}
												aria-pressed={isSelected}
												onClick={() => setSelectedRunId(run.runId)}
												className={`grid w-full grid-cols-[minmax(11rem,1.2fr)_minmax(12rem,1.5fr)_6rem_6rem_8rem] items-center px-3 py-2.5 text-left text-xs transition-colors ${
													isSelected
														? "bg-[color-mix(in_oklch,var(--color-accent)_8%,transparent)]"
														: "hover:bg-(--color-interaction-hover-subtle-bg)"
												}`}
											>
												<span className="truncate font-data font-medium text-(--color-foreground)">{run.runId}</span>
												<span className="truncate font-data text-(--color-foreground-secondary)">
													{run.strategyId} · v{run.strategyVersion || "—"}
												</span>
												<StatusBadge label={run.status} variant={statusVariant(run.status)} size="sm" />
												<span className="font-data text-(--color-foreground-secondary)">{run.progressPct}%</span>
												<span className="font-data text-xs text-(--color-foreground-tertiary)">
													{run.startedAt.slice(0, 10) || "—"}
												</span>
											</button>
										);
									})}
								</div>
							)}
						</PanelBody>
					</Panel>
				}
				detail={
					<aside
						aria-label="回测运行详情"
						className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-1) max-[899px]:hidden"
					>
						<div className="flex h-10 items-center justify-between border-b border-(--color-border-subtle) px-4">
							<p className="text-xs font-medium text-(--color-foreground)">Run Detail</p>
							<span className="font-data text-xs text-(--color-foreground-tertiary)">LIVE</span>
						</div>
						<div className="h-[calc(100%-2.5rem)] overflow-y-auto p-(--density-panel-padding)">
							{selected ? (
								<RunSummary run={selected} />
							) : (
								<p className="text-xs text-(--color-foreground-tertiary)">选择运行以查看精确状态。</p>
							)}
						</div>
					</aside>
				}
			/>
			<BacktestCompareOverlay open={compareOpen} onClose={() => setCompareOpen(false)} runIds={compareIds} />
		</section>
	);
}
