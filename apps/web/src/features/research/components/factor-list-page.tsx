import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { Drawer } from "@/components/indicator/overlay/drawer";
import { CatalogLayout, Panel, PanelBody, PanelHeader, ShellHeaderExtension } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import type { FactorCatalogItem } from "../api/factor-catalog";
import { useFactorCatalog } from "../hooks";

type LaneFilter = "all" | "stock" | "etf";

function metric(value: number | null | undefined, digits: number): string {
	return value === null || value === undefined ? "未评估" : value.toFixed(digits);
}

function percent(value: number | null | undefined): string {
	return value === null || value === undefined ? "未评估" : `${(value * 100).toFixed(1)}%`;
}

function statusLabel(value: string | null | undefined): string {
	if (value === "stable") return "稳定";
	if (value === "degrading") return "衰减";
	if (value === "warning") return "关注";
	return "未评估";
}

function statusClass(value: string | null | undefined): string {
	if (value === "stable") {
		return "bg-[color-mix(in_oklch,var(--color-model-stable-fg)_12%,transparent)] text-(--color-model-stable-fg)";
	}
	if (value === "degrading") {
		return "bg-[color-mix(in_oklch,var(--color-model-degrading-fg)_12%,transparent)] text-(--color-model-degrading-fg)";
	}
	if (value === "warning") {
		return "bg-[color-mix(in_oklch,var(--color-model-drifting-fg)_12%,transparent)] text-(--color-model-drifting-fg)";
	}
	return "bg-(--color-surface-strip) text-(--color-foreground-tertiary)";
}

function errorMessage(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "FACTOR_CATALOG_ERROR"}: ${error.message}`
		: error.message;
}

function FactorCatalogToolbar({
	query,
	onQueryChange,
	lane,
	onLaneChange,
	visibleCount,
	evaluatedCount,
	degradingCount,
	compareCount,
	onOpenCompare,
}: {
	readonly query: string;
	readonly onQueryChange: (value: string) => void;
	readonly lane: LaneFilter;
	readonly onLaneChange: (value: LaneFilter) => void;
	readonly visibleCount: number;
	readonly evaluatedCount: number;
	readonly degradingCount: number;
	readonly compareCount: number;
	readonly onOpenCompare: () => void;
}) {
	const laneButtons = [
		["all", "全部 lane"],
		["stock", "仅个股"],
		["etf", "仅 ETF"],
	] as const;

	return (
		<div data-info-level="l1" data-info-unit="factor-catalog-toolbar">
			<div
				data-testid="factor-catalog-filters"
				className="flex h-8 items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-panel-base) px-4"
			>
				<label className="flex min-w-52 items-center gap-2 text-xs text-(--color-foreground-tertiary)">
					<span>搜索</span>
					<input
						type="search"
						aria-label="搜索因子"
						value={query}
						onChange={(event) => onQueryChange(event.currentTarget.value)}
						placeholder="factor_id"
						className="h-(--density-action-height) min-w-0 flex-1 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) px-2 font-data text-xs text-(--color-foreground)"
					/>
				</label>
				<div className="flex items-center gap-1">
					{laneButtons.map(([value, label]) => (
						<button
							key={value}
							type="button"
							aria-pressed={lane === value}
							className={`h-(--density-action-height) rounded-(--radius-sm) border px-2 text-xs ${
								lane === value
									? "border-(--color-accent) bg-(--color-interaction-selected-bg) text-(--color-accent)"
									: "border-(--color-border-subtle) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
							}`}
							onClick={() => onLaneChange(value)}
						>
							{label}
						</button>
					))}
				</div>
				<span className="ml-auto font-data text-xs tabular-nums text-(--color-foreground-tertiary)">
					{visibleCount} 个因子
				</span>
				<button
					type="button"
					aria-label={`因子对比 ${compareCount}`}
					className="h-(--density-action-height) rounded-(--radius-sm) border border-(--color-border) px-2.5 text-xs font-medium hover:bg-(--color-interaction-hover-subtle-bg)"
					onClick={onOpenCompare}
				>
					因子对比 · {compareCount}
				</button>
			</div>
			<div className="grid h-(--factor-summary-height) grid-cols-3 items-center border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 text-xs">
				<p>
					<span className="text-(--color-foreground-tertiary)">目录</span>{" "}
					<span className="font-data tabular-nums">{visibleCount}</span>
				</p>
				<p className="text-center">
					<span className="text-(--color-foreground-tertiary)">已评估</span>{" "}
					<span className="font-data tabular-nums">{evaluatedCount}</span>
				</p>
				<p className="text-right">
					<span className="text-(--color-foreground-tertiary)">需优先诊断</span>{" "}
					<span className="font-data tabular-nums text-(--color-model-degrading-fg)">{degradingCount}</span>
				</p>
			</div>
		</div>
	);
}

function FactorCatalogTable({
	rows,
	selectedId,
	compareIds,
	onSelect,
	onToggleCompare,
}: {
	readonly rows: readonly FactorCatalogItem[];
	readonly selectedId: string | null;
	readonly compareIds: readonly string[];
	readonly onSelect: (factorId: string) => void;
	readonly onToggleCompare: (factorId: string) => void;
}) {
	return (
		<table className="w-full table-fixed border-collapse text-left text-xs" aria-label="因子目录">
			<colgroup>
				<col className="w-[22%]" />
				<col className="w-[10%]" />
				<col className="w-[11%]" />
				<col className="w-[9%]" />
				<col className="w-[14%]" />
				<col className="w-[11%]" />
				<col className="w-[13%]" />
				<col className="w-[10%]" />
			</colgroup>
			<thead className="sticky top-0 z-10 bg-(--color-surface-strip) text-(--color-foreground-tertiary)">
				<tr className="h-[calc(var(--density-action-height)-1px)]">
					<th className="px-4 font-medium">Factor ID</th>
					<th className="px-2 font-medium">Lanes</th>
					<th className="px-2 text-right font-medium">Rank IC</th>
					<th className="px-2 text-right font-medium">IC_IR</th>
					<th className="px-2 text-right font-medium">衰减</th>
					<th className="px-2 font-medium">诊断状态</th>
					<th className="px-2 font-medium">证据范围</th>
					<th className="px-3 text-right font-medium">对比</th>
				</tr>
			</thead>
			<tbody className="divide-y divide-(--color-border-subtle)">
				{rows.map((row) => {
					const checked = compareIds.includes(row.factorId);
					const compareDisabled = compareIds.length >= 2 && !checked;
					return (
						<tr
							key={row.factorId}
							aria-selected={selectedId === row.factorId}
							className={`h-10 ${
								selectedId === row.factorId
									? "bg-(--color-interaction-selected-bg)"
									: "hover:bg-(--color-interaction-hover-subtle-bg)"
							}`}
						>
							<td className="overflow-hidden px-4">
								<button
									type="button"
									aria-label={`查看 ${row.factorId}`}
									className="block max-w-full truncate font-data font-medium text-(--color-foreground) hover:text-(--color-accent)"
									onClick={() => onSelect(row.factorId)}
								>
									{row.factorId}
								</button>
								<p className="mt-0.5 truncate font-data text-(--color-foreground-tertiary)">
									{row.lookback} · {row.pitRequirement}
								</p>
							</td>
							<td className="truncate px-2 text-(--color-foreground-secondary)">{row.lanes.join(" / ") || "未声明"}</td>
							<td className="px-2 text-right font-data tabular-nums">{metric(row.diagnosticPreview?.rankIc, 3)}</td>
							<td className="px-2 text-right font-data tabular-nums">{metric(row.diagnosticPreview?.icIr, 2)}</td>
							<td className="px-2 text-right font-data tabular-nums">{percent(row.diagnosticPreview?.decay)}</td>
							<td className="px-2 font-medium">
								<span className={`inline-flex rounded-full px-2 py-0.5 ${statusClass(row.diagnosticPreview?.status)}`}>
									{statusLabel(row.diagnosticPreview?.status)}
								</span>
							</td>
							<td className="px-2 text-(--color-foreground-tertiary)">
								{row.diagnosticPreview ? "目录预览" : "未绑定"}
							</td>
							<td className="px-3 text-right">
								<input
									type="checkbox"
									aria-label={`将 ${row.factorId} 加入对比`}
									checked={checked}
									disabled={compareDisabled}
									onChange={() => onToggleCompare(row.factorId)}
									className="accent-(--color-accent)"
								/>
							</td>
						</tr>
					);
				})}
			</tbody>
		</table>
	);
}

function FactorDetail({ row, onCompare }: { readonly row: FactorCatalogItem | null; readonly onCompare: () => void }) {
	return (
		<aside
			aria-label="因子详情"
			data-testid="factor-catalog-detail"
			className="relative z-1 h-[calc(100%+var(--factor-summary-height))] min-h-0 [transform:translateY(calc(-1*var(--factor-summary-height)))]"
		>
			<Panel className="h-full rounded-none border-y-0 border-r-0">
				<PanelHeader title="质量诊断" />
				<PanelBody className="p-(--density-panel-padding)">
					{row === null ? (
						<p className="text-sm text-(--color-foreground-tertiary)">当前筛选没有可选择的受控因子。</p>
					) : (
						<div className="flex min-h-full flex-col gap-(--section-gap)">
							<div>
								<p className="font-data text-base font-semibold text-(--color-foreground)">{row.factorId}</p>
								<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
									{row.lanes.join(" / ") || "lane 未声明"} · {row.lookback}
								</p>
							</div>
							<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3">
								<p className="text-xs font-medium text-(--color-foreground)">证据范围</p>
								<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
									未绑定 snapshot、时间窗口与 registry hash
								</p>
							</div>
							<dl className="grid grid-cols-2 gap-2 text-xs">
								<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2.5">
									<dt className="text-(--color-foreground-tertiary)">Rank IC</dt>
									<dd className="mt-1 font-data tabular-nums">{metric(row.diagnosticPreview?.rankIc, 3)}</dd>
								</div>
								<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2.5">
									<dt className="text-(--color-foreground-tertiary)">IC_IR</dt>
									<dd className="mt-1 font-data tabular-nums">{metric(row.diagnosticPreview?.icIr, 2)}</dd>
								</div>
								<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2.5">
									<dt className="text-(--color-foreground-tertiary)">衰减</dt>
									<dd className="mt-1 font-data tabular-nums">{percent(row.diagnosticPreview?.decay)}</dd>
								</div>
								<div className="rounded-(--radius-sm) border border-(--color-border-subtle) p-2.5">
									<dt className="text-(--color-foreground-tertiary)">覆盖率</dt>
									<dd className="mt-1 font-data tabular-nums">{percent(row.diagnosticPreview?.coverage)}</dd>
								</div>
							</dl>
							<div className="mt-auto flex flex-col gap-2">
								<Link
									to="/research/factors/$id"
									params={{ id: row.factorId }}
									search={{ snapshotId: "", startDate: "", endDate: "", registryHash: "" }}
									className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
								>
									打开精确诊断
								</Link>
								<button
									type="button"
									className="rounded-(--radius-sm) border border-(--color-border) px-3 py-2 text-xs hover:bg-(--color-interaction-hover-subtle-bg)"
									onClick={onCompare}
								>
									查看目录级对比
								</button>
							</div>
						</div>
					)}
				</PanelBody>
			</Panel>
		</aside>
	);
}

function FactorCompareDrawer({
	open,
	onClose,
	rows,
}: {
	readonly open: boolean;
	readonly onClose: () => void;
	readonly rows: readonly FactorCatalogItem[];
}) {
	return (
		<Drawer open={open} onClose={onClose} title="因子对比">
			<div className="space-y-4 pb-6">
				<p className="text-xs text-(--color-foreground-tertiary)">
					目录级对比只展示受控描述与已有诊断预览；不会合成相关性或跨窗口指标。
				</p>
				{rows.length === 0 ? (
					<p className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
						请先在目录中选择最多两个因子。
					</p>
				) : (
					<div className="grid gap-3 sm:grid-cols-2">
						{rows.map((row) => (
							<section key={row.factorId} className="rounded-(--radius-sm) border border-(--color-border-subtle) p-3">
								<h3 className="font-data font-medium text-(--color-foreground)">{row.factorId}</h3>
								<dl className="mt-3 space-y-2 text-xs">
									<div className="flex justify-between gap-3">
										<dt className="text-(--color-foreground-tertiary)">Rank IC</dt>
										<dd className="font-data">{metric(row.diagnosticPreview?.rankIc, 3)}</dd>
									</div>
									<div className="flex justify-between gap-3">
										<dt className="text-(--color-foreground-tertiary)">IC_IR</dt>
										<dd className="font-data">{metric(row.diagnosticPreview?.icIr, 2)}</dd>
									</div>
									<div className="flex justify-between gap-3">
										<dt className="text-(--color-foreground-tertiary)">PIT</dt>
										<dd className="truncate font-data">{row.pitRequirement}</dd>
									</div>
								</dl>
							</section>
						))}
					</div>
				)}
				<div className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3">
					<p className="font-medium text-(--color-foreground)">相关性未计算</p>
					<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
						需要同一 snapshot、折叠窗口和 registry hash 的服务端诊断制品。
					</p>
				</div>
			</div>
		</Drawer>
	);
}

export function FactorListPage() {
	const catalog = useFactorCatalog();
	const rows = catalog.data ?? [];
	const [query, setQuery] = useState("");
	const [lane, setLane] = useState<LaneFilter>("all");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [compareIds, setCompareIds] = useState<readonly string[]>([]);
	const [compareOpen, setCompareOpen] = useState(false);

	const filteredRows = useMemo(() => {
		const normalized = query.trim().toLowerCase();
		return rows.filter(
			(row) =>
				(lane === "all" || row.lanes.includes(lane)) &&
				(normalized.length === 0 || row.factorId.toLowerCase().includes(normalized)),
		);
	}, [lane, query, rows]);
	const selected = filteredRows.find((row) => row.factorId === selectedId) ?? filteredRows[0] ?? null;
	const compareRows = compareIds.flatMap((id) => {
		const row = rows.find((candidate) => candidate.factorId === id);
		return row ? [row] : [];
	});
	const evaluatedCount = filteredRows.filter((row) => row.diagnosticPreview !== null).length;
	const degradingCount = filteredRows.filter((row) => row.diagnosticPreview?.status === "degrading").length;

	function toggleCompare(factorId: string) {
		setCompareIds((current) =>
			current.includes(factorId) ? current.filter((id) => id !== factorId) : [...current, factorId].slice(-2),
		);
	}

	return (
		<>
			<ShellHeaderExtension>
				<button
					type="button"
					className="ml-auto h-(--density-action-height) rounded-(--radius-sm) border border-(--color-border) px-2.5 text-xs font-medium hover:bg-(--color-interaction-hover-subtle-bg)"
					onClick={() => setCompareOpen(true)}
				>
					因子对比
				</button>
			</ShellHeaderExtension>
			<CatalogLayout
				className="[--factor-summary-height:37px] max-[1279px]:grid-cols-[1fr_300px]"
				toolbar={
					<FactorCatalogToolbar
						query={query}
						onQueryChange={setQuery}
						lane={lane}
						onLaneChange={setLane}
						visibleCount={filteredRows.length}
						evaluatedCount={evaluatedCount}
						degradingCount={degradingCount}
						compareCount={compareIds.length}
						onOpenCompare={() => setCompareOpen(true)}
					/>
				}
				main={
					<section
						aria-label="受控因子目录"
						className="h-full min-h-0"
						data-info-level="l1"
						data-info-unit="factor-catalog"
					>
						{catalog.error ? (
							<div className="flex flex-col items-start gap-2 p-4 text-sm text-(--color-led-danger)">
								<p role="alert">{errorMessage(catalog.error)}</p>
								<button type="button" className="underline" onClick={() => void catalog.refetch()}>
									重试因子目录
								</button>
							</div>
						) : catalog.isLoading ? (
							<LoadingSkeleton variant="table" rows={10} />
						) : filteredRows.length === 0 ? (
							<div className="p-4 text-sm text-(--color-foreground-tertiary)">
								<p>当前筛选没有受控因子。</p>
								<p className="mt-1">请调整 factor_id 或 lane；系统不会回退到原型目录。</p>
							</div>
						) : (
							<div className="h-full overflow-auto">
								<FactorCatalogTable
									rows={filteredRows}
									selectedId={selected?.factorId ?? null}
									compareIds={compareIds}
									onSelect={setSelectedId}
									onToggleCompare={toggleCompare}
								/>
							</div>
						)}
					</section>
				}
				detail={<FactorDetail row={selected} onCompare={() => setCompareOpen(true)} />}
			/>
			<FactorCompareDrawer open={compareOpen} onClose={() => setCompareOpen(false)} rows={compareRows} />
		</>
	);
}
