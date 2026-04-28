import type { ColumnDef } from "@/components/data";
import { DataTable } from "@/components/data";
import { ContextSection } from "@/components/domain/context-section";
import { ConfidenceBar, type ConfidenceColor } from "@/components/indicator";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { cn } from "@/lib/utils";
import { useFactors } from "../hooks";
import type { Factor } from "@/types";

const HEALTH_VARIANT: Record<string, "healthy" | "warning" | "error" | "default"> = {
	completed: "healthy",
	running: "healthy",
	pending: "default",
	failed: "error",
	warning: "warning",
	cancelled: "default",
};

// --- IC / IR conditional level helpers ---

type SignalLevel = "strong" | "normal" | "muted" | "dim";

const IC_THRESHOLDS: readonly { readonly min: number; readonly level: SignalLevel }[] = [
	{ min: 0.05, level: "strong" },
	{ min: 0.03, level: "normal" },
	{ min: 0.02, level: "muted" },
] as const;

const IR_THRESHOLDS: readonly { readonly min: number; readonly level: SignalLevel }[] = [
	{ min: 0.8, level: "strong" },
	{ min: 0.5, level: "normal" },
	{ min: 0.3, level: "muted" },
] as const;

function getIcLevel(ic: number): SignalLevel {
	const abs = Math.abs(ic);
	for (const t of IC_THRESHOLDS) {
		if (abs >= t.min) return t.level;
	}
	return "dim";
}

function getIrLevel(ir: number): SignalLevel {
	const abs = Math.abs(ir);
	for (const t of IR_THRESHOLDS) {
		if (abs >= t.min) return t.level;
	}
	return "dim";
}

const LEVEL_COLORS: Record<SignalLevel, string> = {
	strong: "text-(--color-market-up)",
	normal: "text-(--color-accent)",
	muted: "text-(--color-foreground-secondary)",
	dim: "text-(--color-foreground-muted)",
};

const LEVEL_BAR_COLORS: Record<SignalLevel, ConfidenceColor> = {
	strong: "success",
	normal: "brand",
	muted: "neutral",
	dim: "neutral",
};

// --- Status bar helpers ---

const STATUS_BAR_COLORS: Record<string, string> = {
	failed: "bg-(--color-risk-critical-fg)",
	warning: "bg-(--color-risk-high-fg)",
};

// --- Sharpe trend helpers ---

type SharpeTrend = "up" | "flat" | "down";

function getSharpeTrend(sharpe: number): SharpeTrend {
	if (sharpe >= 1.5) return "up";
	if (sharpe >= 1.0) return "flat";
	return "down";
}

const SHARPE_ARROW: Record<SharpeTrend, string> = {
	up: "▲",
	flat: "▶",
	down: "▼",
};

const SHARPE_COLOR: Record<SharpeTrend, string> = {
	up: "text-(--color-market-up)",
	flat: "text-(--color-foreground-tertiary)",
	down: "text-(--color-market-down)",
};

// --- Columns ---

const COLUMNS: readonly ColumnDef<Factor>[] = [
	{
		id: "statusBar",
		header: "",
		width: "4px",
		accessor: (row) => (
			<div
				data-slot="status-bar"
				data-health={row.healthStatus}
				className={cn(
					"h-full w-1 min-h-4 rounded-full",
					STATUS_BAR_COLORS[row.healthStatus] ?? "bg-transparent",
				)}
			/>
		),
		className: "!p-0 w-1",
	},
	{
		id: "name",
		header: "因子",
		width: "20%",
		accessor: (row) => (
			<div className="flex items-center gap-2">
				<span className="font-medium text-(--color-foreground)">
					{row.name}
				</span>
				<span className="text-xs text-(--color-foreground-tertiary)">
					{row.family}
				</span>
			</div>
		),
	},
	{
		id: "ic",
		header: "IC",
		width: "12%",
		accessor: (row) => {
			const level = getIcLevel(row.ic);
			return (
				<div data-testid={`ic-${row.id}`} data-level={level} className="flex flex-col gap-0.5">
					<span className={cn("font-data tabular-nums", LEVEL_COLORS[level])}>
						{row.ic.toFixed(3)}
					</span>
					<ConfidenceBar
						data-testid={`ic-bar-${row.id}`}
						value={Math.abs(row.ic)}
						max={0.1}
						color={LEVEL_BAR_COLORS[level]}
						size="sm"
						className="ml-auto w-12"
						aria-label={`IC strength ${row.ic.toFixed(3)}`}
					/>
				</div>
			);
		},
		align: "right",
		numeric: true,
	},
	{
		id: "ir",
		header: "IR",
		width: "10%",
		accessor: (row) => {
			const level = getIrLevel(row.ir);
			return (
				<span
					data-testid={`ir-${row.id}`}
					data-level={level}
					className={cn("font-data tabular-nums", LEVEL_COLORS[level])}
				>
					{row.ir.toFixed(2)}
				</span>
			);
		},
		align: "right",
		numeric: true,
	},
	{
		id: "turnover",
		header: "换手率",
		width: "10%",
		accessor: (row) => `${(row.turnover * 100).toFixed(0)}%`,
		align: "right",
		numeric: true,
	},
	{
		id: "decay",
		header: "衰减",
		width: "8%",
		accessor: (row) => String(row.decay),
		align: "right",
		numeric: true,
	},
	{
		id: "coverage",
		header: "覆盖率",
		width: "10%",
		accessor: (row) => `${((row.coverage ?? 0) * 100).toFixed(0)}%`,
		align: "right",
		numeric: true,
	},
	{
		id: "sharpe",
		header: "Sharpe",
		width: "10%",
		accessor: (row) => {
			const sharpe = row.sharpe ?? 0;
			const trend = getSharpeTrend(sharpe);
			return (
				<span
					data-testid={`sharpe-${row.id}`}
					data-trend={trend}
					className={cn("inline-flex items-center gap-1 font-data tabular-nums", SHARPE_COLOR[trend])}
				>
					<span className="text-xs">{SHARPE_ARROW[trend]}</span>
					{sharpe.toFixed(2)}
				</span>
			);
		},
		align: "right",
		numeric: true,
	},
	{
		id: "universe",
		header: "Universe",
		width: "10%",
		accessor: (row) => row.universe ?? "—",
	},
	{
		id: "healthStatus",
		header: "状态",
		width: "10%",
		accessor: (row) => (
			<StatusBadge
				variant={HEALTH_VARIANT[row.healthStatus] ?? "default"}
				label={row.healthStatus}
				size="sm"
			/>
		),
	},
] as const;

export function FactorTable() {
	const { data, isLoading, refetch } = useFactors();

	return (
		<ContextSection title="因子监控" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={5} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div data-slot="factor-table">
						<DataTable<Factor>
							columns={COLUMNS}
							data={data.items}
							rowKey="id"
							density="dense"
						/>
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
