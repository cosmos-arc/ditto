import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError } from "@/api/errors";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { LOCAL_WATCHLIST_STORAGE_KEY, readLocalWatchlist } from "@/lib/local-watchlist";
import { WatchlistOverlay, type WatchlistOverlayId } from "./market-page-overlays";
import type { MarketCatalog, MarketCatalogInstrument } from "./market-view-contracts";

const watchlistActions = [
	{ id: "add-instrument", label: "添加标的" },
	{ id: "bulk-delete", label: "批量删除" },
] as const;

/** 名称/代码检索由 workflow 注入，markets 能力不依赖 instruments 能力。 */
export type WatchlistSearchFn = (term: string) => Promise<MarketCatalog>;
/** 自选对象按精确身份解析（现有单对象解析），由 workflow 注入。 */
export type WatchlistEntryFn = (instrumentId: number) => Promise<MarketCatalogInstrument>;

export function WatchlistPage({
	resolveEntry,
	searchCatalog,
}: {
	readonly resolveEntry: WatchlistEntryFn;
	readonly searchCatalog: WatchlistSearchFn;
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
							<span className="font-normal text-(--color-foreground-tertiary)">· 仅保存 identity，不伪造实时行情</span>
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
							<div className="flex min-w-0 flex-col justify-center px-4">
								<span className="text-xs text-(--color-foreground-tertiary)">数据边界</span>
								<span className="mt-1 truncate text-sm">metadata identity only</span>
							</div>
							<div className="flex min-w-0 flex-col justify-center px-4">
								<span className="text-xs text-(--color-foreground-tertiary)">下一步</span>
								<span className="mt-1 truncate text-sm">按名称或代码检索并保存自选</span>
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
							<p>公开 Watchlist 写接口尚不存在；价格、信号、新闻与策略暴露也不会用静态值替代。</p>
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
}: {
	readonly instrumentId: number;
	readonly onRemove: () => void;
	readonly resolveEntry: WatchlistEntryFn;
}) {
	const entry = useQuery({
		queryKey: ["watchlist-entry", instrumentId],
		queryFn: () => resolveEntry(instrumentId),
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
	return (
		<div
			data-info-level="l3"
			data-info-unit="watchlist-row"
			data-row-state={instrument.is_active ? "active" : "delisted"}
			className="grid grid-cols-[minmax(0,1fr)_8rem_6rem_auto] items-center gap-3 px-4 py-3 text-sm"
		>
			<div>
				<a href={`/instruments/${instrument.instrument_id}`} className="font-medium hover:text-(--color-accent)">
					{instrument.name}
				</a>
				<p className="font-mono text-xs text-(--color-foreground-tertiary)">ID {instrument.instrument_id}</p>
			</div>
			<span className="font-mono">
				{instrument.ticker} · {instrument.exchange}
			</span>
			<span className="flex items-center gap-1 text-(--color-foreground-tertiary)">
				{instrument.asset_class}
				{instrument.is_active ? null : (
					<span className="rounded bg-(--color-risk-warning)/10 px-1 py-0.5 text-xs text-(--color-risk-warning)">
						已退出
					</span>
				)}
			</span>
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
	const results = useQuery({
		queryKey: ["watchlist-search", term],
		queryFn: () => searchCatalog(term),
		enabled: term.length > 0,
		retry: false,
	});

	function submit(event: React.FormEvent): void {
		event.preventDefault();
		setTerm(draft.trim());
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
					检索失败：{results.error instanceof Error ? results.error.message : "未知错误"}。清单未修改。
				</p>
			)}
			{term.length > 0 && !results.isLoading && !results.isError && (results.data?.items.length ?? 0) === 0 && (
				<p role="alert" className="text-xs text-(--color-foreground-tertiary)">
					没有匹配的标的；请调整名称或代码后重试。
				</p>
			)}
			{term.length > 0 && !results.isLoading && !results.isError && (results.data?.items.length ?? 0) > 0 && (
				<ul className="grid gap-2" aria-label="候选结果">
					{results.data?.items.map((candidate) => (
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
			)}
		</div>
	);
}
