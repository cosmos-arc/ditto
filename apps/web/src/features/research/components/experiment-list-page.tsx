import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ApiError } from "@/api";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useExperiments } from "@/features/research/hooks";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { ExperimentListItem } from "@/types";

function statusVariant(status: string): "healthy" | "live" | "warning" | "error" | "idle" {
	switch (status.toLowerCase()) {
		case "completed":
			return "healthy";
		case "running":
			return "live";
		case "queued":
		case "paused":
			return "warning";
		case "failed":
		case "cancelled":
			return "error";
		default:
			return "idle";
	}
}

function errorText(error: Error | null): string | null {
	if (!error) return null;
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "EXPERIMENT_CATALOG_ERROR"}: ${error.message}`
		: error.message;
}

function formatTime(value: string): string {
	return new Intl.DateTimeFormat("zh-CN", {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		hour12: false,
	}).format(new Date(value));
}

function ExperimentSummary({ experiment }: { readonly experiment: ExperimentListItem }) {
	return (
		<div className="flex flex-col gap-(--section-gap)">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<h2 className="truncate font-data text-sm font-semibold text-(--color-foreground)">
						{experiment.experimentId}
					</h2>
					<p className="mt-1 font-data text-[11px] text-(--color-foreground-tertiary)">
						revision {experiment.revision}
					</p>
				</div>
				<StatusBadge label={experiment.status} variant={statusVariant(experiment.status)} size="sm" />
			</div>
			<dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-2 border-y border-(--color-border-subtle) py-3 text-xs">
				<dt className="text-(--color-foreground-tertiary)">当前阶段</dt>
				<dd className="break-all font-data text-(--color-foreground)">{experiment.stage}</dd>
				<dt className="text-(--color-foreground-tertiary)">期望状态</dt>
				<dd className="font-data text-(--color-foreground-secondary)">{experiment.desiredState}</dd>
				<dt className="text-(--color-foreground-tertiary)">队列序号</dt>
				<dd className="font-data text-(--color-foreground-secondary)">{experiment.queueOrdinal ?? "不在队列"}</dd>
				<dt className="text-(--color-foreground-tertiary)">失败代码</dt>
				<dd className="break-all font-data text-(--color-foreground-secondary)">
					{experiment.failureCode ?? "未报告失败"}
				</dd>
			</dl>
			<div className="grid gap-3 text-[11px] text-(--color-foreground-tertiary)">
				<div>
					<p className="uppercase tracking-[0.08em]">Created</p>
					<p className="mt-1 font-data text-(--color-foreground-secondary)">{formatTime(experiment.createdAt)}</p>
				</div>
				<div>
					<p className="uppercase tracking-[0.08em]">Updated</p>
					<p className="mt-1 font-data text-(--color-foreground-secondary)">{formatTime(experiment.updatedAt)}</p>
				</div>
			</div>
		</div>
	);
}

export function ExperimentListPage() {
	const query = useExperiments();
	const experiments = query.data ?? [];
	const [search, setSearch] = useState("");
	const [status, setStatus] = useState("all");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [drawerOpen, setDrawerOpen] = useState(false);
	const statusOptions = useMemo(
		() => [...new Set(experiments.map((experiment) => experiment.status))].sort(),
		[experiments],
	);
	const filtered = useMemo(() => {
		const needle = search.trim().toLowerCase();
		return experiments.filter(
			(experiment) =>
				(status === "all" || experiment.status === status) &&
				(!needle ||
					experiment.experimentId.toLowerCase().includes(needle) ||
					experiment.stage.toLowerCase().includes(needle) ||
					experiment.status.toLowerCase().includes(needle)),
		);
	}, [experiments, search, status]);
	const selected = filtered.find((experiment) => experiment.experimentId === selectedId) ?? filtered[0] ?? null;
	const runningCount = experiments.filter((experiment) => experiment.status === "running").length;
	const failedCount = experiments.filter((experiment) => experiment.failureCode !== null).length;

	return (
		<section aria-label="受控实验目录" className="h-full min-h-0">
			<CatalogLayout
				className="max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_1fr] max-[899px]:[grid-template-areas:'toolbar''main']"
				toolbar={
					<div className="flex h-12 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<div className="min-w-0">
							<p className="text-sm font-medium text-(--color-foreground)">实验队列</p>
							<p className="hidden text-xs text-(--color-foreground-tertiary) 2xl:block">
								frozen identity · PIT preflight · 可恢复运行
							</p>
						</div>
						<label className="ml-auto min-w-48 max-w-72 flex-1">
							<span className="sr-only">搜索实验</span>
							<input
								type="search"
								aria-label="搜索实验"
								value={search}
								onChange={(event) => setSearch(event.currentTarget.value)}
								placeholder="ID / stage / status"
								className="h-8 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-3 text-xs outline-none focus:border-(--color-border-strong)"
							/>
						</label>
						<select
							aria-label="按状态筛选实验"
							value={status}
							onChange={(event) => setStatus(event.currentTarget.value)}
							className="h-8 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-2 text-xs"
						>
							<option value="all">全部状态</option>
							{statusOptions.map((option) => (
								<option key={option} value={option}>
									{option}
								</option>
							))}
						</select>
						<Link
							to="/research/experiments/new"
							className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-xs font-medium text-(--brand-accent-fg)"
						>
							创建实验
						</Link>
					</div>
				}
				main={
					<Panel className="m-3 h-[calc(100%-1.5rem)]">
						<PanelHeader
							title="Experiments"
							count={filtered.length}
							actions={
								<span className="font-data text-xs text-(--color-foreground-tertiary)">
									{runningCount} running · {failedCount} failed
								</span>
							}
						/>
						<PanelBody className="p-0">
							<div className="grid grid-cols-[minmax(9rem,1.2fr)_minmax(10rem,1.4fr)_7rem_5rem_7rem] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
								<span>Experiment</span>
								<span>Stage</span>
								<span>Status</span>
								<span>Revision</span>
								<span>Updated</span>
							</div>
							{query.error ? (
								<div className="flex flex-col items-start gap-2 p-4 text-xs text-(--color-led-danger)">
									<p role="alert">{errorText(query.error)}</p>
									<Button size="sm" variant="outline" onClick={() => void query.refetch()}>
										重试实验目录
									</Button>
								</div>
							) : query.isLoading && experiments.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">正在加载实验目录…</p>
							) : filtered.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">当前筛选下没有实验。</p>
							) : (
								<div className="divide-y divide-(--color-border-subtle)">
									{filtered.map((experiment) => {
										const isSelected = selected?.experimentId === experiment.experimentId;
										return (
											<button
												key={experiment.experimentId}
												type="button"
												aria-label={`选择 ${experiment.experimentId}`}
												aria-pressed={isSelected}
												onClick={() => setSelectedId(experiment.experimentId)}
												className={`grid w-full grid-cols-[minmax(9rem,1.2fr)_minmax(10rem,1.4fr)_7rem_5rem_7rem] items-center px-3 py-2.5 text-left text-xs transition-colors ${
													isSelected
														? "bg-[color-mix(in_oklch,var(--color-accent)_8%,transparent)]"
														: "hover:bg-(--color-interaction-hover-subtle-bg)"
												}`}
											>
												<span className="font-data font-medium text-(--color-foreground)">
													{experiment.experimentId}
												</span>
												<span className="truncate font-data text-(--color-foreground-secondary)">
													{experiment.stage}
												</span>
												<StatusBadge label={experiment.status} variant={statusVariant(experiment.status)} size="sm" />
												<span className="font-data text-(--color-foreground-secondary)">v{experiment.revision}</span>
												<span className="font-data text-xs text-(--color-foreground-tertiary)">
													{experiment.updatedAt.slice(0, 10)}
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
						aria-label="实验详情"
						className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-1)"
					>
						<div className="flex h-10 items-center justify-between border-b border-(--color-border-subtle) px-4">
							<p className="text-xs font-medium text-(--color-foreground)">Run Detail</p>
							<span className="font-data text-xs text-(--color-foreground-tertiary)">LIVE</span>
						</div>
						<div className="h-[calc(100%-2.5rem)] overflow-y-auto p-(--density-panel-padding)">
							{selected ? (
								<div className="flex flex-col gap-4">
									<ExperimentSummary experiment={selected} />
									<div className="grid gap-2">
										<Button
											size="sm"
											onClick={() => setDrawerOpen(true)}
											aria-label={`查看 ${selected.experimentId} 详情`}
										>
											查看详情
										</Button>
										<Link
											to="/research/experiments/$id"
											params={{ id: selected.experimentId }}
											className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-2 text-center text-xs text-(--color-foreground-secondary)"
										>
											打开实验工作台
										</Link>
									</div>
								</div>
							) : (
								<p className="text-xs text-(--color-foreground-tertiary)">选择实验以查看受控身份。</p>
							)}
						</div>
					</aside>
				}
			/>
			<Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
				<SheetContent side="right" className="p-0">
					<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
						<SheetTitle>{selected ? `实验 ${selected.experimentId} 详情` : "实验详情"}</SheetTitle>
						<SheetDescription>来自实验目录的精确 revision 与运行状态；完整证据在实验工作台。</SheetDescription>
					</SheetHeader>
					{selected && (
						<div className="flex flex-1 flex-col gap-5 overflow-y-auto p-5">
							<ExperimentSummary experiment={selected} />
							<Link
								to="/research/experiments/$id"
								params={{ id: selected.experimentId }}
								className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
							>
								打开实验工作台
							</Link>
						</div>
					)}
				</SheetContent>
			</Sheet>
		</section>
	);
}
