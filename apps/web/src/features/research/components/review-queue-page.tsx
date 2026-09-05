/** Review queue catalog. Rows remain selectable even when a packet is missing so the rail can explain why review is blocked. */
import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ApiError } from "@/api";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { ReviewQueueEntry } from "@/types/review";
import { useReviews } from "../hooks";

function outcomeVariant(outcome: string): "healthy" | "warning" | "error" | "idle" {
	switch (outcome.toLowerCase()) {
		case "approved":
			return "healthy";
		case "pending":
			return "warning";
		case "rejected":
			return "error";
		default:
			return "idle";
	}
}

function queueError(error: Error | null): string | null {
	if (!error) return null;
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "REVIEW_QUEUE_ERROR"}: ${error.message}`
		: error.message;
}

function ReviewSummary({ entry }: { readonly entry: ReviewQueueEntry }) {
	return (
		<div className="flex flex-col gap-(--section-gap)">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<h2 className="break-all font-data text-sm font-semibold text-(--color-foreground)">
						{entry.strategyId} · v{entry.version}
					</h2>
					<p className="mt-1 font-data text-[11px] text-(--color-foreground-tertiary)">
						parent {entry.parentVersion === null ? "root" : `v${entry.parentVersion}`}
					</p>
				</div>
				<StatusBadge label={entry.reviewOutcome} variant={outcomeVariant(entry.reviewOutcome)} size="sm" />
			</div>
			<dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 border-y border-(--color-border-subtle) py-3 text-xs">
				<dt className="text-(--color-foreground-tertiary)">Version state</dt>
				<dd className="font-data text-(--color-foreground-secondary)">{entry.state}</dd>
				<dt className="text-(--color-foreground-tertiary)">Experiment</dt>
				<dd className="break-all font-data text-(--color-foreground)">
					{entry.experimentId ?? "Review packet 尚未生成"}
				</dd>
				<dt className="text-(--color-foreground-tertiary)">Spec hash</dt>
				<dd className="truncate font-data text-(--color-foreground-secondary)" title={entry.specHash}>
					{entry.specHash}
				</dd>
				<dt className="text-(--color-foreground-tertiary)">Created</dt>
				<dd className="font-data text-(--color-foreground-secondary)">{entry.createdAt}</dd>
			</dl>
			{entry.experimentId ? (
				<div className="grid gap-2">
					<Link
						to="/research/reviews/$id"
						params={{ id: entry.experimentId }}
						search={{ strategyId: entry.strategyId, version: entry.version }}
						className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
					>
						打开审查工作台
					</Link>
					<Link
						to="/research/strategies/$id"
						params={{ id: entry.strategyId }}
						className="rounded-(--radius-sm) border border-(--color-border-subtle) px-3 py-2 text-center text-xs text-(--color-foreground-secondary)"
					>
						查看策略版本
					</Link>
				</div>
			) : (
				<div className="rounded-(--radius-sm) border border-(--color-led-warning) bg-(--color-surface-strip) p-3 text-xs text-(--color-foreground-secondary)">
					Review packet 尚未生成；当前版本可见，但批准、驳回与发布均不可执行。
				</div>
			)}
		</div>
	);
}

export function ReviewQueuePage() {
	const query = useReviews();
	const entries = query.data ?? [];
	const [search, setSearch] = useState("");
	const [outcome, setOutcome] = useState("all");
	const [selectedIdentity, setSelectedIdentity] = useState<string | null>(null);
	const outcomes = useMemo(() => [...new Set(entries.map((entry) => entry.reviewOutcome))].sort(), [entries]);
	const filtered = useMemo(() => {
		const needle = search.trim().toLowerCase();
		return entries.filter(
			(entry) =>
				(outcome === "all" || entry.reviewOutcome === outcome) &&
				(!needle ||
					entry.strategyId.toLowerCase().includes(needle) ||
					entry.experimentId?.toLowerCase().includes(needle) ||
					entry.reviewOutcome.toLowerCase().includes(needle)),
		);
	}, [entries, outcome, search]);
	const selected =
		filtered.find((entry) => `${entry.strategyId}@${entry.version}` === selectedIdentity) ?? filtered[0] ?? null;
	const actionableCount = entries.filter((entry) => entry.experimentId !== null).length;
	const approvedCount = entries.filter((entry) => entry.reviewOutcome === "approved").length;

	return (
		<section aria-label="受控审查队列" className="h-full min-h-0">
			<CatalogLayout
				className="max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_1fr] max-[899px]:[grid-template-areas:'toolbar''main']"
				toolbar={
					<div className="flex h-12 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<div className="min-w-0">
							<p className="text-sm font-medium text-(--color-foreground)">审查队列</p>
							<p className="hidden text-xs text-(--color-foreground-tertiary) 2xl:block">
								hard gates · packet hash · append-only governance
							</p>
						</div>
						<label className="ml-auto min-w-48 max-w-72 flex-1">
							<span className="sr-only">搜索审查版本</span>
							<input
								type="search"
								aria-label="搜索审查版本"
								value={search}
								onChange={(event) => setSearch(event.currentTarget.value)}
								placeholder="strategy / experiment / outcome"
								className="h-8 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-3 text-xs outline-none focus:border-(--color-border-strong)"
							/>
						</label>
						<select
							aria-label="按结论筛选审查"
							value={outcome}
							onChange={(event) => setOutcome(event.currentTarget.value)}
							className="h-8 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-2 text-xs"
						>
							<option value="all">全部结论</option>
							{outcomes.map((value) => (
								<option key={value} value={value}>
									{value}
								</option>
							))}
						</select>
					</div>
				}
				main={
					<Panel className="m-3 h-[calc(100%-1.5rem)]">
						<PanelHeader
							title="Reviews"
							count={filtered.length}
							actions={
								<span className="font-data text-xs text-(--color-foreground-tertiary)">
									{actionableCount} packets · {approvedCount} approved
								</span>
							}
						/>
						<PanelBody className="p-0">
							<div className="grid grid-cols-[minmax(12rem,1.5fr)_5rem_minmax(9rem,1fr)_7rem_7rem] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
								<span>Strategy version</span>
								<span>Parent</span>
								<span>Experiment</span>
								<span>Outcome</span>
								<span>Created</span>
							</div>
							{query.error ? (
								<div className="flex flex-col items-start gap-2 p-4 text-xs text-(--color-led-danger)">
									<p role="alert">{queueError(query.error)}</p>
									<Button size="sm" variant="outline" onClick={() => void query.refetch()}>
										重试审查队列
									</Button>
								</div>
							) : query.isLoading && entries.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">正在加载审查队列…</p>
							) : filtered.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">当前筛选下没有审查版本。</p>
							) : (
								<div className="divide-y divide-(--color-border-subtle)">
									{filtered.map((entry) => {
										const identity = `${entry.strategyId}@${entry.version}`;
										const isSelected = selected === entry;
										return (
											<button
												key={identity}
												type="button"
												aria-label={`选择 ${entry.strategyId} v${entry.version}`}
												aria-pressed={isSelected}
												onClick={() => setSelectedIdentity(identity)}
												className={`grid w-full grid-cols-[minmax(12rem,1.5fr)_5rem_minmax(9rem,1fr)_7rem_7rem] items-center px-3 py-2.5 text-left text-xs transition-colors ${
													isSelected
														? "bg-[color-mix(in_oklch,var(--color-accent)_8%,transparent)]"
														: "hover:bg-(--color-interaction-hover-subtle-bg)"
												}`}
											>
												<span className="truncate font-data font-medium text-(--color-foreground)">
													{entry.strategyId} · v{entry.version}
												</span>
												<span className="font-data text-(--color-foreground-secondary)">
													{entry.parentVersion === null ? "root" : `v${entry.parentVersion}`}
												</span>
												<span className="truncate font-data text-(--color-foreground-secondary)">
													{entry.experimentId ?? "packet missing"}
												</span>
												<StatusBadge
													label={entry.reviewOutcome}
													variant={outcomeVariant(entry.reviewOutcome)}
													size="sm"
												/>
												<span className="font-data text-xs text-(--color-foreground-tertiary)">
													{entry.createdAt.slice(0, 10)}
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
						aria-label="审查详情"
						className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-1) max-[899px]:hidden"
					>
						<div className="flex h-10 items-center justify-between border-b border-(--color-border-subtle) px-4">
							<p className="text-xs font-medium text-(--color-foreground)">Review Detail</p>
							<span className="font-data text-xs text-(--color-foreground-tertiary)">GOVERNED</span>
						</div>
						<div className="h-[calc(100%-2.5rem)] overflow-y-auto p-(--density-panel-padding)">
							{selected ? (
								<ReviewSummary entry={selected} />
							) : (
								<p className="text-xs text-(--color-foreground-tertiary)">选择版本以查看审查身份。</p>
							)}
						</div>
					</aside>
				}
			/>
		</section>
	);
}
