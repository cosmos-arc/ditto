import { useScreenerPresets } from "../hooks";
import { FilterToolbar } from "@/components/domain/filter-controls/filter-toolbar";
import { FilterChip } from "@/components/domain/filter-controls/filter-chip";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { useScreenerStore } from "../stores/screener.store";

export function ScreenerToolbar() {
	const { data, isLoading, isError, refetch } = useScreenerPresets();
	const { activeFilters, removeFilter, clearFilters } = useScreenerStore();

	return (
		<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
			<FilterToolbar data-info-level="l1" data-info-unit="screener-toolbar">
				<span className="px-2 text-sm font-medium text-(--color-foreground-secondary)">
					筛选条件
				</span>
				{isLoading && <LoadingSkeleton variant="metric" className="h-7 w-40" />}
				{data?.presets.map((preset) => (
					<FilterChip key={preset.id} label={preset.name} />
				))}
				{activeFilters.length > 0 && (
					<>
						{activeFilters.map((f) => (
							<FilterChip
								key={f.field}
								label={`${f.field} ${f.op} ${String(f.value)}`}
								active
								onClick={() => removeFilter(f.field)}
							/>
						))}
						<FilterChip label="清除" onClick={clearFilters} />
					</>
				)}
			</FilterToolbar>
		</DittoErrorBoundary>
	);
}
