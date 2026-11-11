import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError } from "@/api/errors";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { LOCAL_WATCHLIST_STORAGE_KEY, readLocalWatchlist } from "@/lib/local-watchlist";
import { WatchlistOverlay, type WatchlistOverlayId } from "./market-page-overlays";
import type {
	MarketCalendarStatusQuery,
	MarketCatalog,
	MarketCatalogInstrument,
	MarketQuoteSnapshot,
	WatchlistQuoteFn,
} from "./market-view-contracts";
import { observationAnchorLabel } from "./market-view-contracts";

const watchlistActions = [
	{ id: "add-instrument", label: "添加标的" },
	{ id: "bulk-delete", label: "批量删除" },
] as const;

/** 名称/代码检索由 workflow 注入（按 offset 分页），markets 能力不依赖 instruments 能力。 */
export type WatchlistSearchFn = (term: string, offset: number) => Promise<MarketCatalog>;
/** 自选对象按精确身份解析（现有单对象解析），由 workflow 注入。 */
export type WatchlistEntryFn = (instrumentId: number) => Promise<MarketCatalogInstrument>;

/** 与图表主读数同口径的有符号数字（负号用 U+2212），保证表图数字对齐。 */
function formatSigned(value: number, digits = 2): string {
	const sign = value > 0 ? "+" : value < 0 ? "−" : "";
	return `${sign}${Math.abs(value).toFixed(digits)}`;
}

/**
 * 行情列统一宽度（收盘 + 涨跌 + 行情日三段 nowrap 不折行；视觉门 V1）：
 * 各状态共用同一列宽，行间列边界稳定，数值 tabular 右对齐；flex-none
 * 保证空间不足时整列换行而非挤压内部断行。
 */
const QUOTE_CELL_WIDTH_CLASS = "inline-flex w-[23rem] flex-none justify-end";

export function WatchlistPage({
	resolveEntry,
	searchCatalog,
	observationQuery,
	quote,
}: {
	readonly resolveEntry: WatchlistEntryFn;
	readonly searchCatalog: WatchlistSearchFn;
	/** 最近完整交易日锚点（calendar 数据集真实摄取结果），用于摘要与行情窗口。 */
	readonly observationQuery: MarketCalendarStatusQuery;
	/** 行情解析（既有日 K 合同）与锚点状态（日期未落定为 null；pending=日历仍在读取），由 workflow 注入。 */
	readonly quote: {
		readonly anchorDate: string | null;
		readonly anchorPending: boolean;
		readonly resolve: WatchlistQuoteFn;
	};
}) {
	const [ids, setIds] = useState<number[]>(readLocalWatchlist);
	const [activeOverlay, setActiveOverlay] = useState<WatchlistOverlayId | null>(null);

	useEffect(() => {
		localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify(ids));
	}, [ids]);

	function addInstrument(instrumentId: number): void {
		setIds((current) => (current.includes(instrumentId) ? current : [...current, instrumentId]));
		setActiveOverlay(null);
	}

	return (
		<>
			<CatalogLayout
				toolbar={
					<div
						data-info-level="l1"
						data-info-unit="watchlist-toolbar"
						className="flex h-8 items-center justify-between gap-3 overflow-hidden border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4"
					>
						<p className="truncate text-xs font-medium">
							自选监控{" "}
							<span className="font-normal text-(--color-foreground-tertiary)">
								· 行情为最近可见交易日收盘，不伪造盘中实时数据
							</span>
						</p>
						<PageActionBar ariaLabel="自选页面操作" actions={watchlistActions} onOpen={setActiveOverlay} />
					</div>
				}
				main={
					<div className="flex h-full min-h-0 flex-col">
						<section
							aria-label="观察列表摘要"
							className="grid h-[70px] shrink-0 grid-cols-3 divide-x divide-(--color-border-subtle) border-b border-(--color-border-subtle) bg-(--color-surface-panel-base)"
							data-info-level="l1"
							data-info-unit="watchlist-summary"
						>
							<div className="flex min-w-0 flex-col justify-center px-4">
								<span className="text-xs text-(--color-foreground-tertiary)">当前清单</span>
								<span className="mt-1 font-data text-sm">{ids.length} 个本地标的</span>
							</div>
							<div className="flex min-w-0 flex-col justify-center px-4" data-testid="watchlist-anchor">
								<span className="text-xs text-(--color-foreground-tertiary)">最近完整交易日</span>
								<span className="mt-1 truncate font-data text-sm">
									{observationAnchorLabel(observationQuery.data, observationQuery.isError, observationQuery.isLoading)}
								</span>
							</div>
							<div className="flex min-w-0 flex-col justify-center px-4">
								<span className="text-xs text-(--color-foreground-tertiary)">数据边界</span>
								<span className="mt-1 truncate text-sm">行情列按各对象真实可见行情日展示</span>
							</div>
						</section>
						<main
							className="min-h-0 flex-1"
							data-info-level="l1"
							data-info-unit="watchlist-catalog"
							data-testid="watchlist-catalog"
						>
							<Panel className="m-4" data-info-unit="watchlist-main">
								<PanelHeader title="本地 Watchlist" subtitle={`${ids.length} symbols`} />
								<PanelBody>
									{ids.length === 0 && (
										<div className="p-12 text-center">
											<p className="font-medium">尚未添加标的</p>
											<p className="mt-1 text-sm text-(--color-foreground-tertiary)">
												使用「添加标的」按名称或代码检索真实 metadata 目录。
											</p>
										</div>
									)}
									{ids.length > 0 && (
										<div className="divide-y divide-(--color-border-subtle)">
											{ids.map((id) => (
												<WatchlistEntryRow
													key={id}
													instrumentId={id}
													quote={quote}
													resolveEntry={resolveEntry}
													onRemove={() => setIds((current) => current.filter((entry) => entry !== id))}
												/>
											))}
										</div>
									)}
								</PanelBody>
							</Panel>
						</main>
					</div>
				}
				detail={
					<Panel className="m-4 ml-0" data-info-level="l2" data-info-unit="watchlist-boundary">
						<PanelHeader title="保存与证据边界" />
						<PanelBody className="space-y-3 p-(--density-panel-padding) text-sm leading-6 text-(--color-foreground-secondary)">
							<p>此清单仅保存在当前浏览器，不会同步到服务端或其他设备。</p>
							<p>
								每个对象重开时按 instrument_id
								精确身份重新解析；目录中已不存在或已退出的对象会明确标注，不会静默消失或被替换。
							</p>
							<p>
								行情列为最近可见交易日收盘与对前收盘涨跌；本地行情库未覆盖的对象明确标注「行情不可得」，不会用静态值替代。
							</p>
						</PanelBody>
					</Panel>
				}
			/>
			<WatchlistOverlay
				active={activeOverlay}
				count={ids.length}
				onClear={() => {
					setIds([]);
					setActiveOverlay(null);
				}}
				onClose={() => setActiveOverlay(null)}
				addForm={<WatchlistSearchForm savedIds={ids} searchCatalog={searchCatalog} onAdd={addInstrument} />}
			/>
		</>
	);
}

function WatchlistEntryRow({
	instrumentId,
	onRemove,
	resolveEntry,
	quote,
}: {
	readonly instrumentId: number;
	readonly onRemove: () => void;
	readonly resolveEntry: WatchlistEntryFn;
	readonly quote: {
		readonly anchorDate: string | null;
		readonly anchorPending: boolean;
		readonly resolve: WatchlistQuoteFn;
	};
}) {
	const entry = useQuery({
		queryKey: ["watchlist-entry", instrumentId],
		queryFn: () => resolveEntry(instrumentId),
		retry: false,
	});
	// 行情列仅在观察锚点落定且身份解析成功后发起：无成功锚点（日历失败/
	// 未报告）不猜测日期发注定 422 的请求；未知/解析失败对象不请求行情。
	// 锚点未落定时 queryFn 不执行（占位串仅满足类型）。
	const quoteQuery = useQuery({
		queryKey: ["watchlist-quote", instrumentId, quote.anchorDate],
		queryFn: () => quote.resolve(instrumentId, quote.anchorDate ?? ""),
		enabled: quote.anchorDate !== null && entry.data !== undefined,
		retry: false,
	});

	if (entry.isError) {
		const unknown = entry.error instanceof ApiError && entry.error.status === 404;
		return (
			<div
				data-info-level="l3"
				data-info-unit="watchlist-row"
				data-row-state={unknown ? "unknown" : "error"}
				className="flex items-center justify-between gap-3 px-4 py-3 text-sm"
			>
				<div>
					{unknown ? (
						<p>
							目录中未找到标的 <span className="font-mono">ID {instrumentId}</span>
						</p>
					) : (
						<p>
							标的 <span className="font-mono">ID {instrumentId}</span> 解析失败（网络或服务错误）
						</p>
					)}
					<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
						{unknown ? "该对象不会从清单中静默消失；可移除或保留待目录恢复。" : "该对象保留在清单中，可重试解析。"}
					</p>
				</div>
				<div className="flex shrink-0 items-center gap-2">
					{!unknown && (
						<button
							type="button"
							onClick={() => void entry.refetch()}
							className="rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							重试
						</button>
					)}
					<button
						type="button"
						aria-label={`移除 未知标的 ${instrumentId}`}
						onClick={onRemove}
						className="rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
					>
						移除
					</button>
				</div>
			</div>
		);
	}

	if (entry.data === undefined) {
		return (
			<div data-info-level="l3" data-info-unit="watchlist-row" className="px-4 py-3 text-sm">
				<span className="text-(--color-foreground-tertiary)">正在按精确身份解析 ID {instrumentId}…</span>
			</div>
		);
	}

	const instrument = entry.data;
	const snapshot = quoteQuery.data ?? null;
	// 观察上下文合同：进入标的图表时携带该对象自己的最近可见行情日，
	// 表（自选行情列）与图（K 线 Primary Answer）锚定同一交易日。
	const href = snapshot
		? `/instruments/${instrument.instrument_id}?tab=chart&observeDate=${snapshot.tradeDate}`
		: `/instruments/${instrument.instrument_id}`;
	return (
		<div
			data-info-level="l3"
			data-info-unit="watchlist-row"
			data-row-state={instrument.is_active ? "active" : "delisted"}
			className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm"
		>
			<div className="min-w-[11rem] flex-1">
				<a href={href} className="font-medium hover:text-(--color-accent)">
					{instrument.name}
				</a>
				<p className="font-mono text-xs text-(--color-foreground-tertiary)">ID {instrument.instrument_id}</p>
			</div>
			<span className="w-32 font-mono text-xs text-(--color-foreground-secondary)">
				{instrument.ticker} · {instrument.exchange}
			</span>
			<span className="flex w-24 items-center gap-1 text-(--color-foreground-tertiary)">
				{instrument.asset_class}
				{instrument.is_active ? null : (
					<span className="rounded bg-(--color-risk-warning)/10 px-1 py-0.5 text-xs text-(--color-risk-warning)">
						已退出
					</span>
				)}
			</span>
			<WatchlistQuoteCell
				anchorDate={quote.anchorDate}
				anchorPending={quote.anchorPending}
				instrumentId={instrumentId}
				instrumentName={instrument.name}
				query={quoteQuery}
			/>
			<button
				type="button"
				aria-label={`移除 ${instrument.name}`}
				onClick={onRemove}
				className="rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
			>
				移除
			</button>
		</div>
	);
}

function WatchlistQuoteCell({
	instrumentId,
	instrumentName,
	anchorDate,
	anchorPending,
	query,
}: {
	readonly instrumentId: number;
	readonly instrumentName: string;
	/** 成功锚点日期；null = 无成功锚点（已落定，非等待中）。 */
	readonly anchorDate: string | null;
	/** 日历状态仍在读取（等待锚点，非终态）。 */
	readonly anchorPending: boolean;
	readonly query: {
		readonly data: MarketQuoteSnapshot | null | undefined;
		readonly isError: boolean;
		readonly isLoading: boolean;
		readonly refetch: () => unknown;
	};
}) {
	if (anchorPending || query.isLoading) {
		return <span className={QUOTE_CELL_WIDTH_CLASS}>行情解析中…</span>;
	}
	if (anchorDate === null) {
		return (
			<span
				data-quote-state="anchor-unresolved"
				title="日历数据集未报告最近成功摄取的交易日；行情列不猜测锚点日期发起注定失败的请求，待日历恢复后自动重解析"
				className={QUOTE_CELL_WIDTH_CLASS}
			>
				<span className="text-xs text-(--color-foreground-muted)">锚点未落定</span>
			</span>
		);
	}
	if (query.isError) {
		return (
			<span className={`${QUOTE_CELL_WIDTH_CLASS} flex items-center justify-end gap-2`}>
				<span data-quote-state="error" className="text-xs text-(--color-risk-warning-fg)">
					行情读取失败
				</span>
				<button
					type="button"
					aria-label={`重试行情 ${instrumentName}`}
					onClick={() => void query.refetch()}
					className="rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
				>
					重试
				</button>
			</span>
		);
	}
	const snapshot = query.data ?? null;
	if (snapshot === null) {
		return (
			<span
				data-quote-state="unavailable"
				title={`标的 ${instrumentId}：本地行情库当前窗口内没有可见日 K（数据集未覆盖或未晋级）`}
				className={QUOTE_CELL_WIDTH_CLASS}
			>
				<span className="text-xs text-(--color-foreground-muted)">行情不可得</span>
			</span>
		);
	}
	const direction = snapshot.change === null || snapshot.change === 0 ? "flat" : snapshot.change > 0 ? "up" : "down";
	return (
		<span className={`${QUOTE_CELL_WIDTH_CLASS} flex items-baseline justify-end gap-3`}>
			<span data-quote-field="close" className="w-20 text-right font-data text-sm tabular-nums">
				{snapshot.close.toFixed(2)}
			</span>
			<span
				data-quote-field="change"
				className={`w-[9rem] whitespace-nowrap text-right font-data text-sm tabular-nums ${
					direction === "up"
						? "text-(--color-market-up)"
						: direction === "down"
							? "text-(--color-market-down)"
							: "text-(--color-foreground-secondary)"
				}`}
			>
				{snapshot.change === null
					? "—"
					: `${formatSigned(snapshot.change)}${snapshot.changePercent === null ? "" : ` (${formatSigned(snapshot.changePercent)}%)`}`}
			</span>
			{/* ISO 日期禁止在连字符处断行（视觉门 V1）：固定列宽整列右对齐。 */}
			<span
				data-quote-field="date"
				className="w-[7.5rem] whitespace-nowrap text-right text-xs text-(--color-foreground-tertiary)"
			>
				行情日 {snapshot.tradeDate}
			</span>
		</span>
	);
}

function WatchlistSearchForm({
	onAdd,
	savedIds,
	searchCatalog,
}: {
	readonly onAdd: (instrumentId: number) => void;
	readonly savedIds: readonly number[];
	readonly searchCatalog: WatchlistSearchFn;
}) {
	const [draft, setDraft] = useState("");
	const [term, setTerm] = useState("");
	const results = useInfiniteQuery({
		queryKey: ["watchlist-search", term],
		queryFn: ({ pageParam }) => searchCatalog(term, pageParam),
		initialPageParam: 0,
		getNextPageParam: (lastPage, allPages) => {
			const loaded = allPages.reduce((count, page) => count + page.items.length, 0);
			return loaded < lastPage.total && lastPage.items.length > 0 ? loaded : undefined;
		},
		enabled: term.length > 0,
		retry: false,
	});
	const items = results.data?.pages.flatMap((page) => page.items) ?? [];
	const total = results.data?.pages.at(0)?.total ?? 0;

	function submit(event: React.FormEvent): void {
		event.preventDefault();
		const next = draft.trim();
		if (next === term) {
			// 同值重提交：React 状态 bailout 后仍要真实重取（错误态恢复路径）。
			void results.refetch();
			return;
		}
		setTerm(next);
	}

	return (
		<div className="space-y-4">
			<form className="grid gap-1" onSubmit={submit}>
				<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
					搜索代码或名称
					<input
						aria-label="搜索代码或名称"
						value={draft}
						onChange={(event) => setDraft(event.currentTarget.value)}
						className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-3 py-2 text-sm text-(--color-foreground)"
						placeholder="例如 贵州茅台 / 600519 / 510300.SH"
					/>
				</label>
				<button
					type="submit"
					disabled={draft.trim().length === 0}
					className="w-full rounded-md bg-(--color-accent) px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
				>
					检索
				</button>
			</form>
			{term.length > 0 && results.isLoading && (
				<p className="text-xs text-(--color-foreground-tertiary)">正在检索 metadata 目录…</p>
			)}
			{term.length > 0 && results.isError && (
				<p role="alert" className="text-xs text-(--color-risk-warning-fg)">
					检索失败：{results.error instanceof Error ? results.error.message : "未知错误"}。清单未修改，可重试。
				</p>
			)}
			{term.length > 0 && !results.isLoading && !results.isError && items.length === 0 && (
				<p role="alert" className="text-xs text-(--color-foreground-tertiary)">
					没有匹配的标的；请调整名称或代码后重试。
				</p>
			)}
			{term.length > 0 && !results.isLoading && !results.isError && items.length > 0 && (
				<>
					<p className="text-xs text-(--color-foreground-tertiary)" data-testid="watchlist-search-evidence">
						共 {total} 项 · 已加载 {items.length}
					</p>
					<ul className="grid gap-2" aria-label="候选结果">
						{items.map((candidate) => (
							<li
								key={candidate.instrument_id}
								className="flex items-center justify-between gap-3 rounded-md border border-(--color-border-subtle) px-3 py-2"
							>
								<div className="min-w-0">
									<p className="truncate text-sm font-medium">{candidate.name}</p>
									<p className="truncate font-mono text-xs text-(--color-foreground-tertiary)">
										{candidate.ticker} · {candidate.exchange} · {candidate.asset_class}
										{candidate.is_active ? "" : " · 已退出"}
									</p>
								</div>
								<button
									type="button"
									aria-label={`加入自选 ${candidate.name}`}
									disabled={savedIds.includes(candidate.instrument_id)}
									onClick={() => {
										onAdd(candidate.instrument_id);
										setDraft("");
										setTerm("");
									}}
									className="shrink-0 rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg) disabled:opacity-50"
								>
									{savedIds.includes(candidate.instrument_id) ? "已在自选" : "加入自选"}
								</button>
							</li>
						))}
					</ul>
					{results.hasNextPage && (
						<button
							type="button"
							onClick={() => void results.fetchNextPage()}
							disabled={results.isFetchingNextPage}
							className="w-full rounded-md border border-(--color-border-subtle) px-3 py-2 text-xs hover:bg-(--color-interaction-hover-subtle-bg) disabled:opacity-50"
						>
							{results.isFetchingNextPage ? "正在加载…" : "加载更多"}
						</button>
					)}
				</>
			)}
		</div>
	);
}
