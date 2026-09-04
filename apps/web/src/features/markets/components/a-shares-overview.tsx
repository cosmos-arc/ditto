import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain/context-section";
import { ErrorState } from "@/lib/error-boundary";
import { useMarketCatalog } from "../hooks";

export function ASharesOverview() {
	const query = useMarketCatalog({ assetClass: "stock", isActive: true, limit: 100 });
	const items = query.data?.items ?? [];
	const exchangeCounts = items.reduce<Record<string, number>>((counts, item) => {
		counts[item.exchange] = (counts[item.exchange] ?? 0) + 1;
		return counts;
	}, {});

	if (query.isLoading) return <LoadingSkeleton variant="table" rows={8} />;
	if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;

	return (
		<div data-info-level="l2" data-info-unit="a-share-coverage" className="flex flex-col gap-4">
			<ContextSection
				title="A 股身份覆盖"
				count={query.data?.total}
				data-info-level="l1"
				data-info-unit="identity-coverage"
			>
				<div className="grid gap-3 p-1 sm:grid-cols-2">
					{Object.entries(exchangeCounts).map(([exchange, count]) => (
						<div key={exchange} className="rounded-lg border border-(--color-border-subtle) bg-(--color-surface-1) p-4">
							<p className="font-mono text-xs text-(--color-foreground-tertiary)">{exchange}</p>
							<p className="mt-1 text-2xl font-semibold">{count}</p>
							<p className="text-xs text-(--color-foreground-tertiary)">active stock identities</p>
						</div>
					))}
				</div>
			</ContextSection>
			<ContextSection title="活跃标的" data-info-level="l1" data-info-unit="active-stock-list">
				<div className="divide-y divide-(--color-border-subtle)">
					{items.map((item) => (
						<a
							key={item.instrument_id}
							href={`/instruments/${item.instrument_id}`}
							data-info-level="l3"
							data-info-unit="a-share-row"
							className="grid grid-cols-[minmax(0,1fr)_7rem_5rem] items-center gap-3 px-3 py-2.5 text-sm transition-colors hover:bg-(--color-interaction-hover-subtle-bg)"
						>
							<span className="font-medium">{item.name}</span>
							<span className="font-mono text-(--color-foreground-tertiary)">{item.ticker}</span>
							<span className="text-(--color-foreground-tertiary)">{item.exchange}</span>
						</a>
					))}
				</div>
			</ContextSection>
		</div>
	);
}
