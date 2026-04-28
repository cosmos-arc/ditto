import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DataToolbarProps {
	readonly searchLabel?: string;
	readonly selectedCount?: number;
	readonly onSearch?: () => void;
	readonly onFilter?: () => void;
	readonly onColumns?: () => void;
	readonly onExport?: () => void;
	readonly className?: string;
}

function ToolbarButton({
	children,
	label,
	onClick,
	toolbarAction,
}: {
	readonly children: ReactNode;
	readonly label: string;
	readonly onClick: () => void;
	readonly toolbarAction: "search" | "filter" | "columns" | "export";
}) {
	return (
		<button
			type="button"
			aria-label={label}
			data-table-toolbar={toolbarAction}
			onClick={onClick}
			className="inline-flex h-7 shrink-0 items-center gap-1 rounded-[var(--radius-sm)] border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-2 text-xs font-medium text-(--color-foreground-secondary) transition-colors hover:bg-(--color-interaction-hover-subtle-bg) hover:text-(--color-foreground)"
		>
			{children}
		</button>
	);
}

function SearchIcon() {
	return (
		<svg width={13} height={13} viewBox="0 0 20 20" fill="none" aria-hidden="true">
			<circle cx="9" cy="9" r="5.5" stroke="currentColor" strokeWidth={1.5} />
			<path d="M13 13l4 4" stroke="currentColor" strokeWidth={1.5} />
		</svg>
	);
}

function FilterIcon() {
	return (
		<svg width={13} height={13} viewBox="0 0 20 20" fill="none" aria-hidden="true">
			<path
				d="M4 5h12M6 10h8M8 15h4"
				stroke="currentColor"
				strokeWidth={1.5}
				strokeLinecap="round"
			/>
		</svg>
	);
}

function ColumnsIcon() {
	return (
		<svg width={13} height={13} viewBox="0 0 20 20" fill="none" aria-hidden="true">
			<rect x="4" y="4" width="12" height="12" rx="1.5" stroke="currentColor" strokeWidth={1.5} />
			<path d="M8 4v12M12 4v12" stroke="currentColor" strokeWidth={1.5} />
		</svg>
	);
}

function ExportIcon() {
	return (
		<svg width={13} height={13} viewBox="0 0 20 20" fill="none" aria-hidden="true">
			<path
				d="M10 3v9m0-9l3 3m-3-3L7 6M4 13v3h12v-3"
				stroke="currentColor"
				strokeWidth={1.5}
				strokeLinecap="round"
				strokeLinejoin="round"
			/>
		</svg>
	);
}

export function DataToolbar({
	searchLabel = "搜索",
	selectedCount = 0,
	onSearch,
	onFilter,
	onColumns,
	onExport,
	className,
}: DataToolbarProps) {
	return (
		<div
			role="toolbar"
			aria-label="数据表工具栏"
			data-table-toolbar="root"
			className={cn(
				"flex min-h-9 items-center justify-between gap-2 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-2 py-1",
				className,
			)}
		>
			<div className="flex min-w-0 items-center gap-2">
				{onSearch && (
					<ToolbarButton label={searchLabel} toolbarAction="search" onClick={onSearch}>
						<SearchIcon />
						<span>{searchLabel}</span>
					</ToolbarButton>
				)}
				{selectedCount > 0 && (
					<span className="rounded-[var(--radius-sm)] bg-(--color-interaction-selected-bg) px-2 py-1 text-xs font-medium text-(--color-foreground-secondary)">
						已选 {selectedCount} 项
					</span>
				)}
			</div>
			<div className="flex shrink-0 items-center gap-1">
				{onFilter && (
					<ToolbarButton label="筛选" toolbarAction="filter" onClick={onFilter}>
						<FilterIcon />
						<span>筛选</span>
					</ToolbarButton>
				)}
				{onColumns && (
					<ToolbarButton label="列配置" toolbarAction="columns" onClick={onColumns}>
						<ColumnsIcon />
						<span>列</span>
					</ToolbarButton>
				)}
				{onExport && (
					<ToolbarButton label="导出" toolbarAction="export" onClick={onExport}>
						<ExportIcon />
						<span>导出</span>
					</ToolbarButton>
				)}
			</div>
		</div>
	);
}

export type { DataToolbarProps };
