import { fetchDataProductEvidence, fetchDataProducts } from "@/features/data-products/api";
import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type MacroIndicator = components["schemas"]["Indicator"];
export type MarketContext = components["schemas"]["MarketContextResponse"];

export type MarketContextScope = {
	readonly asOf: string;
	readonly knowledgeCutoff: string;
	readonly publicationCutoff: string;
	readonly sourceSnapshotIds: readonly string[];
};

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

function marketContextPath(scope: MarketContextScope): string {
	if (
		scope.sourceSnapshotIds.length === 0 ||
		new Set(scope.sourceSnapshotIds).size !== scope.sourceSnapshotIds.length
	) {
		throw new Error("market context requires unique exact source snapshot IDs");
	}
	const search = new URLSearchParams({
		as_of: scope.asOf,
		knowledge_cutoff: scope.knowledgeCutoff,
		publication_cutoff: scope.publicationCutoff,
	});
	for (const snapshotId of scope.sourceSnapshotIds) search.append("source_snapshot_id", snapshotId);
	return `/v1/market/context?${search.toString()}`;
}

export function fetchMarketContext(scope: MarketContextScope): Promise<MarketContext> {
	return apiClient.get<MarketContext>(marketContextPath(scope));
}

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

export type MacroEvidenceRange = {
	readonly allowExperimentalData: boolean;
	readonly endDate: string;
	readonly startDate: string;
};

export function fetchMacroEvidence(range: MacroEvidenceRange): Promise<readonly MacroIndicator[]> {
	if (!range.allowExperimentalData) throw new Error("experimental macro data must be explicitly enabled");
	if (!range.startDate || !range.endDate || range.startDate > range.endDate) throw new Error("宏观查询日期范围无效");

	return apiClient.get<readonly MacroIndicator[]>(
		withQueryParams("/v1/macro/indicators/metadata", {
			allow_experimental_data: true,
			end: range.endDate,
			start: range.startDate,
		}),
	);
}
