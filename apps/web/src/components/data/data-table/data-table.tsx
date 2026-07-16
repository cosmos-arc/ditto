import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

/* ── Types ── */

type SortDirection = "asc" | "desc";

interface ColumnDef<TRow extends object> {
	readonly id: string;
	readonly header: string;
	readonly width?: string;
	readonly accessor: keyof TRow | ((row: TRow) => React.ReactNode);
	readonly align?: "left" | "center" | "right";
	readonly numeric?: boolean;
	readonly sortable?: boolean;
	readonly className?: string;
}

interface DataTableProps<TRow extends object> {
	readonly columns: readonly ColumnDef<TRow>[];
	readonly data: readonly TRow[];
	readonly rowKey?: keyof TRow;
	readonly onRowClick?: (row: TRow) => void;
	readonly selectedId?: string;
	readonly density?: "default" | "comfortable" | "dense";
	readonly rowClassName?: (row: TRow) => string;
	readonly className?: string;
}

/* ── Cell renderer ── */

function renderCell<TRow extends object>(row: TRow, accessor: ColumnDef<TRow>["accessor"]): React.ReactNode {
	if (typeof accessor === "function") return accessor(row);
	const value = row[accessor];
	if (typeof value === "number") return value.toLocaleString("en-US");
	return String(value);
}

/* ── Sort logic ── */

function sortData<TRow extends object>(
	data: readonly TRow[],
	columnId: string | null,
	direction: SortDirection | null,
	columns: readonly ColumnDef<TRow>[],
): readonly TRow[] {
	if (!columnId || !direction) return data;

	const col = columns.find((c) => c.id === columnId);
	if (!col) return data;

	const sorted = [...data].sort((a, b) => {
		const aVal = typeof col.accessor === "function" ? null : a[col.accessor];
		const bVal = typeof col.accessor === "function" ? null : b[col.accessor];

		if (typeof aVal === "number" && typeof bVal === "number") {
			return direction === "asc" ? aVal - bVal : bVal - aVal;
		}
		const aStr = String(aVal ?? "");
		const bStr = String(bVal ?? "");
		return direction === "asc" ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
	});

	return sorted;
}

/* ── Component ── */

function DataTable<TRow extends object>({
	columns,
	data,
	rowKey = "id" as keyof TRow,
	onRowClick,
	selectedId,
	density,
	rowClassName,
	className,
}: DataTableProps<TRow>) {
	const [sortColumn, setSortColumn] = useState<string | null>(null);
	const [sortDirection, setSortDirection] = useState<SortDirection | null>(null);

	const sortedData = useMemo(
		() => sortData(data, sortColumn, sortDirection, columns),
		[data, sortColumn, sortDirection, columns],
	);

	function handleSort(columnId: string) {
		if (sortColumn !== columnId) {
			setSortColumn(columnId);
			setSortDirection("asc");
		} else if (sortDirection === "asc") {
			setSortDirection("desc");
		} else {
			setSortColumn(null);
			setSortDirection(null);
		}
	}

	const cellPadding = "px-[var(--cell-padding-x)] py-[var(--cell-padding-y)]";

	return (
		<div data-slot="data-table" className={cn("w-full overflow-auto", className)}>
			<table data-density={density || undefined} className="w-full table-fixed border-collapse text-sm">
				<thead className="sticky top-0 z-2 bg-(--color-surface-1)">
					<tr>
						{columns.map((col) => {
							const isActive = sortColumn === col.id;
							const dir = isActive ? sortDirection : null;

							return (
								<th
									key={col.id}
									scope="col"
									data-sort={dir}
									style={col.width ? { width: col.width } : undefined}
									className={cn(
										"text-left text-xs font-medium uppercase text-(--color-foreground-tertiary) border-b border-(--color-border-subtle)",
										cellPadding,
										col.align === "right" && "text-right",
										col.align === "center" && "text-center",
										col.sortable && "cursor-pointer select-none",
										col.className,
									)}
									onClick={col.sortable ? () => handleSort(col.id) : undefined}
								>
									<span className="inline-flex items-center gap-1">
										{col.header}
										{col.sortable && (
											<span aria-hidden="true" className="inline-flex flex-col text-[8px] leading-none opacity-50">
												<span className={isActive && dir === "asc" ? "opacity-100" : "opacity-30"}>▲</span>
												<span className={isActive && dir === "desc" ? "opacity-100" : "opacity-30"}>▼</span>
											</span>
										)}
									</span>
								</th>
							);
						})}
					</tr>
				</thead>
				<tbody>
					{sortedData.map((row, i) => {
						const key = String(row[rowKey] ?? i);
						const isSelected = selectedId != null && key === String(selectedId);
						return (
							<tr
								key={key}
								onClick={onRowClick ? () => onRowClick(row) : undefined}
								className={cn(
									"transition-colors",
									onRowClick && "cursor-pointer hover:bg-(--color-surface-hover)",
									isSelected && "bg-(--color-surface-2)",
									rowClassName?.(row),
								)}
							>
								{columns.map((col) => (
									<td
										key={col.id}
										className={cn(
											"text-xs text-(--color-foreground-secondary) truncate",
											cellPadding,
											col.numeric && "font-data tabular-nums",
											col.align === "right" && "text-right",
											col.align === "center" && "text-center",
											col.className,
										)}
									>
										{renderCell(row, col.accessor)}
									</td>
								))}
							</tr>
						);
					})}
				</tbody>
			</table>
		</div>
	);
}

export type { ColumnDef, DataTableProps };
export { DataTable };
