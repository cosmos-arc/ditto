import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ApiError } from "@/api";
import { LoadingSkeleton } from "@/components/data";
import { Button } from "@/components/ui/button";
import { CatalogLayout, ShellHeaderExtension } from "@/features/shell";
import type { StrategyLifecycleState, StrategyListItem } from "@/types/strategy";
import { useStrategies, useStrategy } from "../hooks";
import { type StrategyListOverlay, StrategyListOverlays } from "./strategy-list-overlays";

type LifecycleFilter = "all" | "published" | "draft" | "governance";

const FILTERS: readonly { readonly id: LifecycleFilter; readonly label: string }[] = [
	{ id: "all", label: "全部状态" },
	{ id: "published", label: "仅已发布" },
	{ id: "draft", label: "仅草稿" },
	{ id: "governance", label: "治理中" },
];

const LIFECYCLE_LABELS: Readonly<Record<StrategyLifecycleState, string>> = {
	draft: "草稿",
	review: "审查中",
	approved: "已批准",
	published: "已发布",
	deprecated: "已弃用",
	unknown: "未知",
};

const LIFECYCLE_CLASSES: Readonly<Record<StrategyLifecycleState, string>> = {
	draft: "border-(--color-border) bg-(--color-surface-2) text-(--color-foreground-secondary)",
	review: "border-(--color-led-warning) bg-(--color-led-warning-bg) text-(--color-led-warning)",
	approved: "border-(--color-led-info) bg-(--color-led-info-bg) text-(--color-led-info)",
	published: "border-(--color-led-success) bg-(--color-led-success-bg) text-(--color-led-success)",
	deprecated: "border-(--color-border-subtle) bg-(--color-surface-strip) text-(--color-foreground-tertiary)",
	unknown: "border-(--color-border-subtle) bg-(--color-surface-strip) text-(--color-foreground-tertiary)",
};

function errorMessage(error: Error): string {
	if (error instanceof ApiError) {
		return `${error.status} ${error.errorCode ?? "STRATEGY_LIST_ERROR"}: ${error.message}`;
	}
	return error.message;
}

function matchesFilter(row: StrategyListItem, filter: LifecycleFilter): boolean {
	if (filter === "all") return true;
	if (filter === "governance") return row.lifecycleState === "review" || row.lifecycleState === "approved";
	return row.lifecycleState === filter;
}

function LifecyclePill({ state }: { readonly state: StrategyLifecycleState }) {
	return (
		<span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${LIFECYCLE_CLASSES[state]}`}>
			{LIFECYCLE_LABELS[state]}
		</span>
	);
}

function SummaryCard({
	label,
	value,
	note,
}: {
	readonly label: string;
	readonly value: string;
	readonly note: string;
}) {
	return (
		<div className="flex min-w-0 items-center gap-2 border-r border-(--color-border-subtle) px-4 last:border-r-0">
			<p className="truncate text-[11px] uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">{label}</p>
			<strong className="font-data text-sm font-semibold text-(--color-foreground)">{value}</strong>
			<span className="truncate text-xs text-(--color-foreground-tertiary)">{note}</span>
		</div>
	);
}

function StrategyToolbar({
	filter,
	onFilterChange,
	onQueryChange,
	query,
	visibleCount,
}: {
	readonly filter: LifecycleFilter;
	readonly onFilterChange: (filter: LifecycleFilter) => void;
	readonly onQueryChange: (query: string) => void;
	readonly query: string;
	readonly visibleCount: number;
}) {
	return (
		<div
			data-testid="strategy-catalog-filters"
			className="flex h-8 items-center gap-2 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
		>
			<label className="relative min-w-56 flex-1 sm:max-w-80">
				<span className="sr-only">搜索策略</span>
				<span
					aria-hidden="true"
					className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-(--color-foreground-tertiary)"
				>
					⌕
				</span>
				<input
					type="search"
					aria-label="搜索策略"
					value={query}
					onChange={(event) => onQueryChange(event.currentTarget.value)}
					placeholder="名称、ID 或标签"
					className="h-7 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) pl-8 pr-3 text-xs text-(--color-foreground) outline-none transition-colors placeholder:text-(--color-foreground-tertiary) focus:border-(--color-border-emphasis)"
				/>
			</label>
			<div className="flex items-center gap-1 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) p-0.5">
				{FILTERS.map((item) => (
					<button
						key={item.id}
						type="button"
						aria-pressed={filter === item.id}
						onClick={() => onFilterChange(item.id)}
						className={`h-6 rounded-[calc(var(--radius-sm)-2px)] px-2.5 text-[11px] font-medium transition-colors ${
							filter === item.id
								? "bg-(--color-interaction-selected-bg) text-(--color-foreground)"
								: "text-(--color-foreground-tertiary) hover:text-(--color-foreground)"
						}`}
					>
						{item.label}
					</button>
				))}
			</div>
			<span className="ml-auto font-data text-[11px] text-(--color-foreground-tertiary)">{visibleCount} 项</span>
		</div>
	);
}

function StrategySummary({ rows }: { readonly rows: readonly StrategyListItem[] }) {
	const published = rows.filter((row) => row.lifecycleState === "published").length;
	const governance = rows.filter((row) => row.lifecycleState === "review" || row.lifecycleState === "approved").length;

	return (
		<div
			data-testid="strategy-catalog-summary"
			className="grid h-[37px] grid-cols-4 border-b border-(--color-border-subtle) bg-(--color-surface-strip)"
		>
			<SummaryCard label="策略目录" value={String(rows.length)} note="服务端版本" />
			<SummaryCard label="已发布" value={String(published)} note="active 版本" />
			<SummaryCard label="治理队列" value={String(governance)} note="审查或待发布" />
			<SummaryCard label="绩效证据" value="未评估" note="未绑定回测制品" />
		</div>
	);
}

function StrategyTable({
	onAction,
	onSelect,
	rows,
	selectedId,
}: {
	readonly onAction: (row: StrategyListItem, action: StrategyListOverlay) => void;
	readonly onSelect: (strategyId: string) => void;
	readonly rows: readonly StrategyListItem[];
	readonly selectedId: string | null;
}) {
	return (
		<table aria-label="策略目录" className="w-full min-w-[760px] border-collapse text-left text-xs">
			<thead className="sticky top-0 z-10 bg-(--color-surface-strip) text-[11px] text-(--color-foreground-tertiary)">
				<tr className="border-b border-(--color-border-subtle)">
					<th className="px-4 py-2.5 font-medium">策略</th>
					<th className="w-16 px-3 py-2.5 font-medium">版本</th>
					<th className="w-40 px-3 py-2.5 font-medium">标签</th>
					<th className="w-24 px-3 py-2.5 font-medium">治理状态</th>
					<th className="w-24 px-3 py-2.5 font-medium">绩效证据</th>
					<th className="w-24 px-3 py-2.5 font-medium">创建日</th>
					<th className="w-24 px-3 py-2.5 text-right font-medium">操作</th>
				</tr>
			</thead>
			<tbody className="divide-y divide-(--color-border-subtle)">
				{rows.map((row) => {
					const selected = row.strategyId === selectedId;
					return (
						<tr
							key={row.strategyId}
							className={
								selected ? "bg-(--color-interaction-selected-bg)" : "hover:bg-(--color-interaction-hover-subtle-bg)"
							}
						>
							<td className="p-0">
								<button
									type="button"
									aria-label={`选择 ${row.strategyId}`}
									onClick={() => onSelect(row.strategyId)}
									className="flex w-full flex-col items-start px-4 py-3 text-left"
								>
									<span className="font-medium text-(--color-foreground)">{row.name}</span>
									<span className="mt-0.5 font-data text-[11px] text-(--color-foreground-tertiary)">
										{row.strategyId}
									</span>
								</button>
							</td>
							<td className="px-3 py-3 font-data text-(--color-foreground-secondary)">v{row.version}</td>
							<td className="px-3 py-3">
								<div className="flex max-w-36 flex-wrap gap-1">
									{row.tags.length > 0 ? (
										row.tags.slice(0, 2).map((tag) => (
											<span
												key={tag}
												className="rounded bg-(--color-surface-3) px-1.5 py-0.5 text-xs text-(--color-foreground-secondary)"
											>
												{tag}
											</span>
										))
									) : (
										<span className="text-(--color-foreground-tertiary)">—</span>
									)}
								</div>
							</td>
							<td className="px-3 py-3">
								<LifecyclePill state={row.lifecycleState} />
							</td>
							<td className="px-3 py-3 font-medium text-(--color-foreground-tertiary)">未评估</td>
							<td className="px-3 py-3 font-data text-[11px] text-(--color-foreground-tertiary)">
								{row.createdAt.slice(0, 10)}
							</td>
							<td className="px-3 py-3">
								<div className="flex justify-end gap-1">
									<button
										type="button"
										aria-label={`克隆 ${row.strategyId}`}
										title="克隆为草稿"
										onClick={() => onAction(row, "clone")}
										className="h-7 rounded-(--radius-sm) px-2 text-[11px] text-(--color-foreground-secondary) hover:bg-(--color-surface-3) hover:text-(--color-foreground)"
									>
										克隆
									</button>
									<button
										type="button"
										aria-label={`删除 ${row.strategyId}`}
										title="版本治理"
										onClick={() => onAction(row, "delete")}
										className="h-7 rounded-(--radius-sm) px-2 text-[11px] text-(--color-foreground-tertiary) hover:bg-(--color-led-danger-bg) hover:text-(--color-led-danger)"
									>
										弃用
									</button>
								</div>
							</td>
						</tr>
					);
				})}
			</tbody>
		</table>
	);
}

function StrategyDetailRail({ row }: { readonly row: StrategyListItem | null }) {
	if (!row) {
		return (
			<aside
				aria-label="策略详情"
				data-testid="strategy-catalog-detail"
				className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-1) p-(--density-panel-padding) text-sm text-(--color-foreground-tertiary)"
			>
				没有符合当前筛选的策略。
			</aside>
		);
	}

	return (
		<aside
			aria-label="策略详情"
			data-testid="strategy-catalog-detail"
			className="flex h-full flex-col overflow-y-auto border-l border-(--color-border-subtle) bg-(--color-surface-1)"
		>
			<header className="border-b border-(--color-border-subtle) p-4">
				<div className="flex items-start justify-between gap-3">
					<div className="min-w-0">
						<p className="truncate text-sm font-semibold text-(--color-foreground)">{row.name}</p>
						<p className="mt-1 font-data text-[11px] text-(--color-foreground-tertiary)">
							{row.strategyId} · v{row.version}
						</p>
					</div>
					<LifecyclePill state={row.lifecycleState} />
				</div>
			</header>
			<div className="flex flex-1 flex-col gap-(--section-gap) p-(--density-panel-padding)">
				<section
					aria-label="版本事实"
					className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-3"
				>
					<p className="text-[11px] font-medium uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
						版本事实
					</p>
					<dl className="mt-3 grid grid-cols-[5rem_1fr] gap-x-3 gap-y-2 text-xs">
						<dt className="text-(--color-foreground-tertiary)">原始状态</dt>
						<dd className="font-data text-(--color-foreground-secondary)">{row.status}</dd>
						<dt className="text-(--color-foreground-tertiary)">创建时间</dt>
						<dd className="font-data text-(--color-foreground-secondary)">{row.createdAt.slice(0, 10)}</dd>
						<dt className="text-(--color-foreground-tertiary)">标签</dt>
						<dd className="text-(--color-foreground-secondary)">{row.tags.join(" · ") || "未设置"}</dd>
					</dl>
				</section>
				<section
					aria-label="绩效证据"
					className="rounded-(--radius-md) border border-dashed border-(--color-border) p-3"
				>
					<div className="flex items-center justify-between gap-3">
						<p className="text-xs font-medium text-(--color-foreground)">绩效证据</p>
						<span className="text-xs font-semibold text-(--color-foreground-tertiary)">未评估</span>
					</div>
					<p className="mt-2 text-xs leading-5 text-(--color-foreground-tertiary)">
						当前列表响应未绑定不可变回测或审查制品，因此不展示收益、Sharpe 或回撤。
					</p>
				</section>
				<div className="mt-auto grid gap-2">
					<Button asChild className="w-full">
						<Link to="/research/strategies/$id/studio" params={{ id: row.strategyId }}>
							打开 Strategy Studio
						</Link>
					</Button>
					<Button asChild variant="outline" className="w-full">
						<Link to="/research/strategies/$id" params={{ id: row.strategyId }}>
							查看版本治理
						</Link>
					</Button>
				</div>
			</div>
		</aside>
	);
}

export function StrategyListPage() {
	const catalog = useStrategies();
	const rows = catalog.data ?? [];
	const [query, setQuery] = useState("");
	const [filter, setFilter] = useState<LifecycleFilter>("all");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [overlay, setOverlay] = useState<StrategyListOverlay | null>(null);

	const filteredRows = useMemo(() => {
		const normalized = query.trim().toLowerCase();
		return rows.filter((row) => {
			const searchable = `${row.strategyId} ${row.name} ${row.tags.join(" ")}`.toLowerCase();
			return matchesFilter(row, filter) && (normalized.length === 0 || searchable.includes(normalized));
		});
	}, [filter, query, rows]);
	const selected = filteredRows.find((row) => row.strategyId === selectedId) ?? filteredRows[0] ?? null;
	const detail = useStrategy(selected?.strategyId ?? "");

	function openAction(row: StrategyListItem, action: StrategyListOverlay) {
		setSelectedId(row.strategyId);
		setOverlay(action);
	}

	return (
		<>
			<ShellHeaderExtension>
				<Button size="sm" className="ml-auto" onClick={() => setOverlay("create")}>
					新建策略
				</Button>
			</ShellHeaderExtension>
			<CatalogLayout
				className="max-[1279px]:grid-cols-[1fr_300px]"
				toolbar={
					<StrategyToolbar
						filter={filter}
						onFilterChange={setFilter}
						onQueryChange={setQuery}
						query={query}
						visibleCount={filteredRows.length}
					/>
				}
				main={
					<div className="grid h-full min-h-0 grid-rows-[37px_1fr]">
						<StrategySummary rows={rows} />
						<section
							aria-label="受控策略目录"
							className="min-h-0 bg-(--color-surface-1)"
							data-info-level="l1"
							data-info-unit="strategy-catalog"
							data-testid="strategy-catalog-main"
						>
							{catalog.error ? (
								<div className="flex flex-col items-start gap-2 p-4 text-sm text-(--color-led-danger)">
									<p role="alert">{errorMessage(catalog.error)}</p>
									<button type="button" className="underline" onClick={() => void catalog.refetch()}>
										重试策略目录
									</button>
								</div>
							) : catalog.isLoading ? (
								<LoadingSkeleton variant="table" rows={9} />
							) : filteredRows.length === 0 ? (
								<div className="p-4 text-sm text-(--color-foreground-tertiary)">
									<p>当前筛选没有受控策略。</p>
									<p className="mt-1">请调整名称、ID、标签或治理状态；系统不会回退到原型数据。</p>
								</div>
							) : (
								<div className="h-full overflow-auto">
									<StrategyTable
										rows={filteredRows}
										selectedId={selected?.strategyId ?? null}
										onSelect={setSelectedId}
										onAction={openAction}
									/>
								</div>
							)}
						</section>
					</div>
				}
				detail={<StrategyDetailRail row={selected} />}
			/>
			<StrategyListOverlays
				open={overlay}
				onClose={() => setOverlay(null)}
				selected={selected}
				detail={detail.data}
				detailLoading={detail.isLoading}
			/>
		</>
	);
}
