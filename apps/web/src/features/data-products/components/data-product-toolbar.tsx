import type { KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";

const WORKBENCH_VIEWS = [
	{ id: "overview", label: "概览" },
	{ id: "coverage", label: "覆盖" },
	{ id: "quality", label: "质量" },
	{ id: "runs", label: "运行与修复" },
	{ id: "evidence", label: "证据与许可" },
	{ id: "operations", label: "运营治理" },
] as const;

export type WorkbenchView = (typeof WORKBENCH_VIEWS)[number]["id"];

interface DataProductToolbarProps {
	readonly view: WorkbenchView;
	readonly onViewChange: (view: WorkbenchView) => void;
	readonly onRefresh: () => void;
}

export function DataProductToolbar({ view, onViewChange, onRefresh }: DataProductToolbarProps) {
	function moveTab(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
		if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
		event.preventDefault();

		let targetIndex: number;
		if (event.key === "Home") {
			targetIndex = 0;
		} else if (event.key === "End") {
			targetIndex = WORKBENCH_VIEWS.length - 1;
		} else {
			const direction = event.key === "ArrowLeft" ? -1 : 1;
			targetIndex = (index + direction + WORKBENCH_VIEWS.length) % WORKBENCH_VIEWS.length;
		}
		const target = WORKBENCH_VIEWS[targetIndex];
		if (!target) return;
		onViewChange(target.id);
		document.getElementById(`data-products-tab-${target.id}`)?.focus();
	}

	return (
		<div className="border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<div>
					<h1 className="text-base font-semibold text-(--color-foreground)">数据产品工作台</h1>
					<p className="text-xs text-(--color-foreground-tertiary)">R2 modern A-share daily，profile: research_daily</p>
				</div>
				<Button type="button" variant="outline" size="xs" onClick={onRefresh}>
					刷新真实 API
				</Button>
			</div>
			<div role="tablist" aria-label="数据产品视图" className="mt-2 flex gap-1 overflow-x-auto">
				{WORKBENCH_VIEWS.map((item, index) => (
					<button
						key={item.id}
						id={`data-products-tab-${item.id}`}
						type="button"
						role="tab"
						aria-selected={view === item.id}
						aria-controls="data-products-tabpanel"
						tabIndex={view === item.id ? 0 : -1}
						onClick={() => onViewChange(item.id)}
						onKeyDown={(event) => moveTab(event, index)}
						className={
							view === item.id
								? "shrink-0 rounded-(--radius-sm) bg-(--color-interaction-selected-bg) px-3 py-1.5 text-xs font-medium text-(--color-foreground) outline-none ring-1 ring-(--color-interaction-selected-border) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)"
								: "shrink-0 rounded-(--radius-sm) px-3 py-1.5 text-xs text-(--color-foreground-secondary) outline-none hover:bg-(--color-interaction-hover-subtle-bg) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)"
						}
					>
						{item.label}
					</button>
				))}
			</div>
		</div>
	);
}
