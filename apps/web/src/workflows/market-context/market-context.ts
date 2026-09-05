import { useQuery } from "@tanstack/react-query";
import { fetchDataProductEvidence, fetchDataProducts } from "@/features/data-products";
import { fetchMarketContext, type MarketContext } from "@/features/markets";

const MARKET_CONTEXT_DATASETS = new Set([
	"stock_daily",
	"index_daily",
	"global_index_daily",
	"index_weight",
	"macro_indicators",
	"fx_daily",
	"commodity_daily",
]);
const REQUIRED_MARKET_CONTEXT_DATASETS = ["stock_daily", "index_daily"] as const;

export const currentMarketContextKeys = {
	all: ["market-evidence", "context"] as const,
	current: (asOf?: string) => [...currentMarketContextKeys.all, asOf ?? "current"] as const,
};

/**
 * Resolve certified Data Product evidence into the exact source-snapshot scope
 * required by the Markets capability. Cross-feature orchestration belongs here,
 * above both capabilities, so neither feature owns the other's adapter.
 */
export async function fetchCurrentMarketContext(asOf = new Date().toISOString()): Promise<MarketContext> {
	const products = await fetchDataProducts();
	const certified = products.filter(
		(product) => MARKET_CONTEXT_DATASETS.has(product.dataset_id) && product.active_certification_report_id !== null,
	);
	const certifiedDatasetIds = new Set(certified.map((product) => product.dataset_id));
	if (REQUIRED_MARKET_CONTEXT_DATASETS.some((datasetId) => !certifiedDatasetIds.has(datasetId))) {
		throw new Error("market context requires certified stock_daily and index_daily source snapshots");
	}
	const evidence = await Promise.all(certified.map((product) => fetchDataProductEvidence(product.dataset_id)));
	const sourceSnapshotIds = [...new Set(evidence.flatMap((item) => item.snapshot_ids))];
	return fetchMarketContext({
		asOf,
		knowledgeCutoff: asOf,
		publicationCutoff: asOf,
		sourceSnapshotIds,
	});
}

export function useCurrentMarketContext(asOf?: string) {
	return useQuery({
		queryKey: currentMarketContextKeys.current(asOf),
		queryFn: () => fetchCurrentMarketContext(asOf),
		staleTime: 60_000,
	});
}
