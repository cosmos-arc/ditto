import { useScreenerResults } from "../hooks";
import { useScreenerStore } from "../stores/screener.store";
import { ContextSection } from "@/components/domain/context-section";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";

export function ScreenerResults() {
	const { data, isLoading, isError, refetch } = useScreenerResults();
	const { selectedIds, toggleSelect } = useScreenerStore();

	return (
		<ContextSection title="筛选结果" count={data?.total}>
			{isLoading && <LoadingSkeleton variant="table" rows={8} />}
			<DittoErrorBoundary fallbackProps={{ onRetry: () => void refetch() }}>
				{data && (
					<div className="space-y-1">
						{data.results.map((item) => (
							<div
								key={item.code}
								className="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
							>
								<div className="flex items-center gap-3">
									<span className="font-medium">{item.name}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">{item.code}</span>
									<span className="text-xs text-(--color-foreground-tertiary)">{item.industry}</span>
								</div>
								<div className="flex items-center gap-4 text-(--color-foreground-tertiary)">
									<span className="tabular-nums">{item.price.toFixed(2)}</span>
									<span
										className={
											item.changePercent >= 0
												? "text-(--color-system-healthy)"
												: "text-(--color-system-down)"
										}
									>
										{item.changePercent >= 0 ? "+" : ""}
										{item.changePercent.toFixed(2)}%
									</span>
									<span>PE {item.pe.toFixed(1)}</span>
									<span>市值 {item.marketCap.toLocaleString()}亿</span>
									<button
										type="button"
										className="rounded border border-(--color-border-subtle) px-2 py-0.5 text-xs transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
										onClick={() => toggleSelect(item.code)}
									>
										{selectedIds.includes(item.code) ? "已选" : "对比"}
									</button>
								</div>
							</div>
						))}
					</div>
				)}
			</DittoErrorBoundary>
		</ContextSection>
	);
}
