import { useEffect, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import { LOCAL_WATCHLIST_STORAGE_KEY, readLocalWatchlist } from "@/lib/local-watchlist";
import { WatchlistOverlay, type WatchlistOverlayId } from "./market-page-overlays";
import type { MarketCatalogQuery } from "./market-view-contracts";

const watchlistActions = [
	{ id: "add-instrument", label: "添加标的" },
	{ id: "bulk-delete", label: "批量删除" },
] as const;

export function WatchlistPage({ catalog }: { readonly catalog: MarketCatalogQuery }) {
	const [ids, setIds] = useState<number[]>(readLocalWatchlist);
	const [draftId, setDraftId] = useState("");
	const [feedback, setFeedback] = useState<string | null>(null);
	const [activeOverlay, setActiveOverlay] = useState<WatchlistOverlayId | null>(null);

	useEffect(() => {
		localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify(ids));
	}, [ids]);

	const rows = (catalog.data?.items ?? []).filter((item) => ids.includes(item.instrument_id));

	function addInstrument() {
		const id = Number(draftId);
		if (!Number.isInteger(id) || id <= 0) {
			setFeedback("请输入正整数内部 ID");
			return;
		}
		if (!catalog.data?.items.some((item) => item.instrument_id === id)) {
			setFeedback("当前 metadata 目录中没有该标的");
			return;
		}
		setIds((current) => (current.includes(id) ? current : [...current, id]));
		setDraftId("");
		setFeedback(null);
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
								<span className="mt-1 truncate text-sm">添加内部 ID 建立浏览器清单</span>
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
									{catalog.isLoading && <LoadingSkeleton variant="table" rows={5} />}
									{catalog.isError && <ErrorState onRetry={() => void catalog.refetch()} />}
									{feedback && (
										<p className="m-3 rounded-md bg-(--color-risk-warning)/10 px-3 py-2 text-sm text-(--color-risk-warning)">
											{feedback}
										</p>
									)}
									{!catalog.isLoading && !catalog.isError && ids.length === 0 && (
										<div className="p-12 text-center">
											<p className="font-medium">尚未添加标的</p>
											<p className="mt-1 text-sm text-(--color-foreground-tertiary)">
												输入 metadata 内部 ID 建立本地监控清单。
											</p>
										</div>
									)}
									{rows.length > 0 && (
										<div className="divide-y divide-(--color-border-subtle)">
											{rows.map((item) => (
												<div
													key={item.instrument_id}
													data-info-level="l3"
													data-info-unit="watchlist-row"
													className="grid grid-cols-[minmax(0,1fr)_8rem_6rem_auto] items-center gap-3 px-4 py-3 text-sm"
												>
													<div>
														<a
															href={`/instruments/${item.instrument_id}`}
															className="font-medium hover:text-(--color-accent)"
														>
															{item.name}
														</a>
														<p className="font-mono text-xs text-(--color-foreground-tertiary)">
															ID {item.instrument_id}
														</p>
													</div>
													<span className="font-mono">
														{item.ticker} · {item.exchange}
													</span>
													<span className="text-(--color-foreground-tertiary)">{item.asset_class}</span>
													<button
														type="button"
														aria-label={`移除 ${item.name}`}
														onClick={() => setIds((current) => current.filter((id) => id !== item.instrument_id))}
														className="rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
													>
														移除
													</button>
												</div>
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
				addForm={
					<div className="space-y-4">
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							标的内部 ID
							<input
								aria-label="标的内部 ID"
								inputMode="numeric"
								value={draftId}
								onChange={(event) => setDraftId(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-3 py-2 text-sm text-(--color-foreground)"
								placeholder="例如 1000001"
							/>
						</label>
						{feedback && (
							<p role="alert" className="text-xs text-(--color-risk-warning-fg)">
								{feedback}
							</p>
						)}
						<button
							type="button"
							onClick={addInstrument}
							disabled={catalog.isLoading}
							className="w-full rounded-md bg-(--color-accent) px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
						>
							确认添加
						</button>
					</div>
				}
			/>
		</>
	);
}
