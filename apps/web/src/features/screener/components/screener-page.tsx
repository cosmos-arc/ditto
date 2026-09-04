import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { fetchInstrumentCatalog } from "@/features/instruments/api/instrument-catalog";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ErrorState } from "@/lib/error-boundary";
import { useScreenerStore } from "../stores/screener.store";
import { type ScreenerOverlayId, ScreenerOverlays, screenerActions } from "./screener-overlays";

const PRESET_STORAGE_KEY = "ditto.market-screener-preset.v1";

export function ScreenerPage() {
	const [search, setSearch] = useState("");
	const [assetClass, setAssetClass] = useState("all");
	const [exchange, setExchange] = useState("all");
	const [activeOverlay, setActiveOverlay] = useState<ScreenerOverlayId | null>(null);
	const [feedback, setFeedback] = useState<string | null>(null);
	const { selectedIds, toggleSelect, clearSelection } = useScreenerStore();
	const query = useQuery({
		queryKey: ["screener", "metadata-identities"],
		queryFn: () => fetchInstrumentCatalog({ limit: 100 }),
	});

	const normalizedSearch = search.trim().toLowerCase();
	const results = (query.data?.items ?? []).filter(
		(item) =>
			(assetClass === "all" || item.asset_class === assetClass) &&
			(exchange === "all" || item.exchange === exchange) &&
			(normalizedSearch.length === 0 ||
				item.name.toLowerCase().includes(normalizedSearch) ||
				item.ticker.toLowerCase().includes(normalizedSearch)),
	);
	const selected = (query.data?.items ?? []).filter((item) => selectedIds.includes(String(item.instrument_id)));

	function savePreset(): void {
		localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify({ assetClass, exchange, search }));
		setFeedback("筛选预设已保存到本机");
		setActiveOverlay(null);
	}

	function exportResults(): void {
		const rows = [
			["instrument_id", "name", "ticker", "exchange", "asset_class"],
			...results.map((item) => [item.instrument_id, item.name, item.ticker, item.exchange, item.asset_class]),
		];
		const csv = rows.map((row) => row.map((value) => JSON.stringify(String(value))).join(",")).join("\n");
		const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
		const link = document.createElement("a");
		link.href = url;
		link.download = "ditto-screener-metadata.csv";
		link.click();
		URL.revokeObjectURL(url);
		setFeedback(`已导出 ${results.length} 个 metadata 身份`);
		setActiveOverlay(null);
	}

	return (
		<>
			<CatalogLayout
				toolbar={
					<div
						data-info-level="l1"
						data-info-unit="screener-toolbar"
						className="flex h-full flex-wrap items-end gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-1"
					>
						<label className="grid min-w-64 flex-1 gap-1 text-xs text-(--color-foreground-tertiary)">
							搜索代码或名称
							<input
								aria-label="搜索代码或名称"
								value={search}
								onChange={(event) => setSearch(event.currentTarget.value)}
								placeholder="名称 / ticker"
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-3 py-1.5 text-sm text-(--color-foreground)"
							/>
						</label>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							资产类别
							<select
								value={assetClass}
								onChange={(event) => setAssetClass(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
							>
								<option value="all">全部</option>
								<option value="stock">stock</option>
								<option value="etf">etf</option>
							</select>
						</label>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							交易所
							<select
								value={exchange}
								onChange={(event) => setExchange(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
							>
								<option value="all">全部</option>
								<option value="SSE">SSE</option>
								<option value="SZSE">SZSE</option>
							</select>
						</label>
						<PageActionBar ariaLabel="筛选器页面操作" actions={screenerActions} onOpen={setActiveOverlay} />
					</div>
				}
				main={
					<div
						data-info-level="l1"
						data-info-unit="screener-main"
						className="h-full overflow-y-auto p-(--density-panel-padding)"
					>
						<ContextSection
							title="身份筛选结果"
							count={results.length}
							data-info-level="l1"
							data-info-unit="screener-results"
						>
							{feedback && (
								<p role="status" className="px-3 py-2 text-xs text-(--color-system-healthy-fg)">
									{feedback}
								</p>
							)}
							{query.isLoading && <LoadingSkeleton variant="table" rows={8} />}
							{query.isError && <ErrorState onRetry={() => void query.refetch()} />}
							{query.data && results.length === 0 && (
								<div className="p-10 text-center text-sm text-(--color-foreground-tertiary)">没有匹配的标的身份</div>
							)}
							{results.length > 0 && (
								<div
									data-info-level="l2"
									data-info-unit="screener-list"
									className="divide-y divide-(--color-border-subtle)"
								>
									{results.map((item) => {
										const id = String(item.instrument_id);
										const isSelected = selectedIds.includes(id);
										return (
											<div
												key={id}
												data-info-level="l3"
												data-info-unit="screener-result-item"
												className="grid grid-cols-[minmax(0,1fr)_8rem_7rem_auto] items-center gap-3 px-3 py-3 text-sm hover:bg-(--color-interaction-hover-subtle-bg)"
											>
												<div>
													<a href={`/instruments/${id}`} className="font-medium hover:text-(--color-accent)">
														{item.name}
													</a>
													<p className="text-xs text-(--color-foreground-tertiary)">ID {id}</p>
												</div>
												<span className="font-mono text-(--color-foreground-secondary)">
													{item.ticker} · {item.exchange}
												</span>
												<span className="text-(--color-foreground-tertiary)">{item.asset_class}</span>
												<button
													type="button"
													aria-label={`对比 ${item.name}`}
													onClick={() => toggleSelect(id)}
													className={
														isSelected
															? "rounded-md bg-(--color-accent) px-2 py-1 text-xs text-white"
															: "rounded-md border border-(--color-border-subtle) px-2 py-1 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
													}
												>
													{isSelected ? "已选" : "对比"}
												</button>
											</div>
										);
									})}
								</div>
							)}
						</ContextSection>
					</div>
				}
				detail={
					<Panel data-info-level="l2" data-info-unit="screener-detail" className="m-4 ml-0">
						<PanelHeader title="身份对比" subtitle="metadata only" />
						<PanelBody className="p-4">
							{selected.length === 0 ? (
								<p className="text-sm text-(--color-foreground-tertiary)">从结果中选择标的，比较身份字段。</p>
							) : (
								<div className="space-y-3">
									<div className="flex items-center justify-between text-sm">
										<span>{`已选 ${selected.length} 个标的`}</span>
										<button
											type="button"
											onClick={clearSelection}
											className="text-xs text-(--color-foreground-tertiary)"
										>
											清除
										</button>
									</div>
									{selected.map((item) => (
										<div
											key={item.instrument_id}
											className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-3 text-sm"
										>
											<p className="font-medium">{item.name}</p>
											<p className="mt-1 font-mono text-xs text-(--color-foreground-tertiary)">
												{item.ticker} · {item.exchange} · {item.asset_class}
											</p>
										</div>
									))}
								</div>
							)}
							<p className="mt-4 border-t border-(--color-border-subtle) pt-3 text-xs leading-5 text-(--color-foreground-tertiary)">
								未查询价格、估值、市值或行业；筛选范围严格受 metadata 合同约束。
							</p>
						</PanelBody>
					</Panel>
				}
			/>
			<ScreenerOverlays
				active={activeOverlay}
				filterSummary={`${assetClass} · ${exchange} · ${search.trim() || "全部"}`}
				onClose={() => setActiveOverlay(null)}
				onExport={exportResults}
				onSavePreset={savePreset}
				resultCount={results.length}
				selectedCount={selected.length}
			/>
		</>
	);
}
