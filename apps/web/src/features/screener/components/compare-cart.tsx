import { useScreenerStore } from "../stores/screener.store";

export function CompareCart() {
	const { selectedIds, clearSelection } = useScreenerStore();

	if (selectedIds.length === 0) return null;

	return (
		<div className="flex items-center justify-between rounded-md border border-(--color-border-subtle) bg-(--color-surface-base) px-4 py-3">
			<span className="text-sm">
				已选 <strong>{selectedIds.length}</strong> 个标的对比
			</span>
			<button
				type="button"
				className="text-xs text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary)"
				onClick={clearSelection}
			>
				清除选择
			</button>
		</div>
	);
}
