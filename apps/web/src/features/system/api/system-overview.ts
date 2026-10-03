import { apiClient } from "@/api/transport";

export type SystemCatalogAsset = {
	readonly datasetId: string;
	readonly freshnessAt: string;
	readonly namespace: string;
	readonly rowCount: number | null;
	readonly schemaHash: string;
	readonly source: string;
	readonly storageUri: string;
};

export type SystemSourceHealthSummary = {
	readonly attentionItems: readonly {
		readonly datasetId: string;
		readonly reasons: readonly string[];
		readonly selectedSource: string;
		readonly severity: string;
		readonly status: string;
	}[];
	readonly attentionRequiredCount: number;
	readonly failoverCount: number;
	readonly noFallbackSourceCount: number;
	readonly selectedSources: readonly { readonly count: number; readonly source: string }[];
	readonly statusCounts: readonly { readonly count: number; readonly status: string }[];
	readonly totalReports: number;
};

export type SystemOverviewScope = {
	readonly datasetIds: readonly string[];
	readonly tradeDate: string;
};

export const systemOverviewKeys = {
	all: ["system", "catalog-overview"] as const,
	assets: () => [...systemOverviewKeys.all, "assets"] as const,
	scope: (scope: SystemOverviewScope) => [...systemOverviewKeys.all, scope.tradeDate, ...scope.datasetIds] as const,
	sourceHealth: (scope: SystemOverviewScope) => [...systemOverviewKeys.scope(scope), "source-health"] as const,
};

function scopedQuery(scope: SystemOverviewScope) {
	return { dataset_ids: [...scope.datasetIds], trade_dates: [scope.tradeDate] };
}

export async function fetchSystemCatalogAssets(): Promise<readonly SystemCatalogAsset[]> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/assets", {
		params: { query: { limit: 100, offset: 0 } },
	});
	return response.map((item) => ({
		datasetId: item.asset.dataset_id,
		freshnessAt: item.freshness_at,
		namespace: item.asset.namespace,
		rowCount: item.schema_fingerprint.row_count ?? null,
		schemaHash: item.schema_fingerprint.schema_hash,
		source: item.source,
		storageUri: item.storage_uri,
	}));
}

export async function fetchSystemSourceHealth(scope: SystemOverviewScope): Promise<SystemSourceHealthSummary> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/source-health/summary", {
		params: { query: scopedQuery(scope) },
	});
	return {
		attentionItems: response.attention_required.map((item) => ({
			datasetId: item.dataset_id,
			reasons: item.attention_reasons ?? [],
			selectedSource: item.selected_source,
			severity: item.attention_severity,
			status: item.source_selection_status,
		})),
		attentionRequiredCount: response.attention_required.length,
		failoverCount: response.failover_count,
		noFallbackSourceCount: response.no_fallback_source_count,
		selectedSources: response.selected_source_counts.map((item) => ({ count: item.count, source: item.source })),
		statusCounts: response.status_counts.map((item) => ({ count: item.count, status: item.status })),
		totalReports: response.total_reports,
	};
}
