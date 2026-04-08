import { useCallback, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import { cn } from "@/lib/utils";
import { dittoTheme } from "./theme";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

/* ── Default column definitions ── */

const DEFAULT_COL_DEF: Partial<ColDef> = {
	cellStyle: {
		display: "flex",
		alignItems: "center",
	},
};

const DEFAULT_NUMERIC_COL_DEF: Partial<ColDef> = {
	...DEFAULT_COL_DEF,
	type: "numericColumn",
	cellStyle: {
		...DEFAULT_COL_DEF.cellStyle,
		justifyContent: "flex-end",
		fontFamily: "var(--font-data), sans-serif",
		fontFeatureSettings: "'tnum' 1",
	},
};

/* ── Props ── */

interface DittoGridProps<TData = Record<string, unknown>> {
	readonly columnDefs: ColDef<TData>[];
	readonly rowData: TData[];
	readonly className?: string;
	/** Grid container height (CSS value, e.g. "400px" or "50vh"). Defaults to "400px". */
	readonly height?: string;
}

/* ── Component ── */

function DittoGrid<TData = Record<string, unknown>>({
	columnDefs,
	rowData,
	className,
	height = "400px",
}: DittoGridProps<TData>) {
	const gridRef = useRef<AgGridReact<TData>>(null);

	const handleExportCsv = useCallback(() => {
		const api = gridRef.current?.api;
		if (!api) return;
		const csv = api.getDataAsCsv();
		const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const link = document.createElement("a");
		link.href = url;
		link.download = "export.csv";
		link.click();
		URL.revokeObjectURL(url);
	}, []);

	return (
		<div
			data-slot="ditto-grid"
			data-testid="ditto-grid-root"
			className={cn("flex flex-col gap-2", className)}
		>
			<div className={cn("ag-theme-quartz", `h-[${height}]`)}>
				<AgGridReact<TData>
					ref={gridRef}
					columnDefs={columnDefs}
					rowData={rowData}
					defaultColDef={DEFAULT_COL_DEF}
					theme={dittoTheme}
					rowSelection="single"
					suppressCellFocus
					animateRows={false}
				/>
			</div>
			<button
				type="button"
				aria-label="Export CSV"
				className="self-end rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1 text-[var(--text-sm)] text-[var(--color-foreground-tertiary)] transition-colors hover:bg-[var(--color-surface-3)] hover:text-[var(--color-foreground)]"
				onClick={handleExportCsv}
			>
				CSV
			</button>
		</div>
	);
}

export { DittoGrid, DEFAULT_COL_DEF, DEFAULT_NUMERIC_COL_DEF };
export type { DittoGridProps };
