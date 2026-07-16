import { useMemo } from "react";
import { type ColumnDef, DataTable, Sparkline } from "@/components/data";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { cn } from "@/lib/utils";
import type { Position } from "@/types";
import { usePositions } from "../hooks";

const COLUMNS: readonly ColumnDef<Position>[] = [
	{
		id: "code",
		header: "代码",
		width: "100px",
		accessor: "code",
	},
	{
		id: "name",
		header: "名称",
		accessor: (row) => (
			<span className="inline-flex items-center gap-1.5">
				<span>{row.name}</span>
				{row.frozenQty > 0 && (
					<StatusBadge variant="warning" label={`冻结 ${row.frozenQty.toLocaleString()}`} size="sm" />
				)}
			</span>
		),
	},
	{
		id: "qty",
		header: "数量",
		width: "80px",
		accessor: "qty",
		align: "right",
		numeric: true,
	},
	{
		id: "avgCost",
		header: "成本",
		width: "80px",
		accessor: (row) => row.avgCost.toFixed(2),
		align: "right",
		numeric: true,
	},
	{
		id: "currentPrice",
		header: "现价",
		width: "80px",
		accessor: (row) => row.currentPrice.toFixed(2),
		align: "right",
		numeric: true,
	},
	{
		id: "sparkline7d",
		header: "7日",
		width: "80px",
		accessor: (row) =>
			row.sparkline7d ? (
				<Sparkline data={row.sparkline7d} color={row.pnl >= 0 ? "up" : "down"} width={64} height={20} />
			) : null,
		align: "center",
	},
	{
		id: "pnl",
		header: "盈亏",
		width: "100px",
		accessor: (row) => (
			<span className={row.pnl >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}>
				{row.pnl >= 0 ? "+" : ""}
				{row.pnl.toLocaleString()}
			</span>
		),
		align: "right",
		numeric: true,
	},
	{
		id: "pnlPercent",
		header: "盈亏%",
		width: "80px",
		accessor: (row) => (
			<span className={row.pnlPercent >= 0 ? "text-(--color-market-up)" : "text-(--color-market-down)"}>
				{row.pnlPercent >= 0 ? "+" : ""}
				{row.pnlPercent.toFixed(2)}%
			</span>
		),
		align: "right",
		numeric: true,
	},
] as const;

function getRowClassName(row: Position): string {
	return cn(
		row.pnl >= 0 && "bg-[color-mix(in_oklch,var(--color-market-up)_4%,transparent)]",
		row.pnl < 0 && "bg-[color-mix(in_oklch,var(--color-market-down)_4%,transparent)]",
	);
}

function SummaryFooter({ positions }: { readonly positions: readonly Position[] }) {
	const totalPnl = useMemo(() => positions.reduce((sum, p) => sum + p.pnl, 0), [positions]);

	return (
		<div
			data-slot="positions-summary-footer"
			className="flex items-center justify-end gap-4 border-t border-(--color-border-subtle) px-[var(--cell-padding-x)] py-1.5 text-xs font-medium"
		>
			<span className="text-(--color-foreground-tertiary)">合计盈亏</span>
			<span
				className={
					totalPnl >= 0
						? "font-data tabular-nums text-(--color-market-up)"
						: "font-data tabular-nums text-(--color-market-down)"
				}
			>
				{totalPnl >= 0 ? "+" : ""}
				{totalPnl.toLocaleString()}
			</span>
		</div>
	);
}

export function PositionsSummary() {
	const { data, isLoading, isError, refetch } = usePositions();

	return (
		<div data-slot="positions-summary" data-info-level="l1" data-info-unit="positions-summary">
			<ContextSection title="持仓汇总" count={data?.positions.length}>
				{isLoading && <LoadingSkeleton variant="table" rows={5} />}
				{isError && (
					<div
						role="alert"
						className="my-2 flex flex-col items-start gap-2 rounded-(--radius-sm) border border-(--color-risk-critical-fg) px-3 py-3 text-sm text-(--color-foreground-secondary) sm:flex-row sm:items-center sm:justify-between"
					>
						<span>持仓汇总加载失败</span>
						<Button variant="outline" size="sm" onClick={() => void refetch()}>
							重试
						</Button>
					</div>
				)}
				<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
					{!isError && data && (
						<>
							<DataTable columns={COLUMNS} data={data.positions} rowKey="code" rowClassName={getRowClassName} />
							<SummaryFooter positions={data.positions} />
						</>
					)}
				</DittoErrorBoundary>
			</ContextSection>
		</div>
	);
}
