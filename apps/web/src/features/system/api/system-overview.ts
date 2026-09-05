import { apiClient } from "@/api";

export type SystemCatalogAsset = {
	readonly datasetId: string;
	readonly freshnessAt: string;
	readonly namespace: string;
	readonly rowCount: number | null;
	readonly schemaHash: string;
	readonly source: string;
	readonly storageUri: string;
};

export type SystemRemediationBacklog = {
	readonly generatedAt: string;
	readonly items: readonly {
		readonly datasetId: string;
		readonly itemId: string;
		readonly reasons: readonly string[];
		readonly severity: string;
		readonly source: string;
		readonly suggestedActions: readonly string[];
		readonly tradeDate: string | null;
	}[];
	readonly severityCounts: readonly { readonly count: number; readonly severity: string }[];
	readonly totalItems: number;
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
	readonly revokedPromotionCount: number;
	readonly selectedSources: readonly { readonly count: number; readonly source: string }[];
	readonly statusCounts: readonly { readonly count: number; readonly status: string }[];
	readonly totalReports: number;
};

export type SystemFallbackSummary = {
	readonly approvalRequiredCount: number;
	readonly executionAllowedCount: number;
	readonly previews: readonly {
		readonly datasetId: string;
		readonly defaultSource: string;
		readonly policyStatus: string;
		readonly recommendedSource: string | null;
		readonly selectedSource: string;
	}[];
	readonly statusCounts: readonly { readonly count: number; readonly status: string }[];
	readonly totalPreviews: number;
};

export type SystemPromotionReadiness = {
	readonly activePromotionCount: number;
	readonly datasetCount: number;
	readonly datasets: readonly {
		readonly currentMaturity: string | null;
		readonly datasetId: string;
		readonly missingCriteria: readonly string[];
		readonly status: string;
	}[];
	readonly promotableCount: number;
	readonly statusCounts: readonly { readonly count: number; readonly status: string }[];
};

export type SystemOverviewScope = {
	readonly datasetIds: readonly string[];
	readonly tradeDate: string;
};

export const systemOverviewKeys = {
	all: ["system", "catalog-overview"] as const,
	assets: () => [...systemOverviewKeys.all, "assets"] as const,
	scope: (scope: SystemOverviewScope) => [...systemOverviewKeys.all, scope.tradeDate, ...scope.datasetIds] as const,
	remediation: (scope: SystemOverviewScope) => [...systemOverviewKeys.scope(scope), "remediation"] as const,
	sourceHealth: (scope: SystemOverviewScope) => [...systemOverviewKeys.scope(scope), "source-health"] as const,
	fallback: (scope: SystemOverviewScope) => [...systemOverviewKeys.scope(scope), "fallback"] as const,
	promotion: (scope: SystemOverviewScope) => [...systemOverviewKeys.scope(scope), "promotion"] as const,
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

export async function fetchSystemRemediation(scope: SystemOverviewScope): Promise<SystemRemediationBacklog> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/remediation/backlog", {
		params: { query: scopedQuery(scope) },
	});
	return {
		generatedAt: response.generated_at,
		items: response.items.map((item) => ({
			datasetId: item.dataset_id,
			itemId: item.item_id,
			reasons: item.reasons ?? [],
			severity: item.severity,
			source: item.source,
			suggestedActions: item.suggested_actions ?? [],
			tradeDate: item.trade_date ?? null,
		})),
		severityCounts: response.severity_counts.map((item) => ({ count: item.count, severity: item.severity })),
		totalItems: response.total_items,
	};
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
		revokedPromotionCount: response.revoked_promotion_count,
		selectedSources: response.selected_source_counts.map((item) => ({ count: item.count, source: item.source })),
		statusCounts: response.status_counts.map((item) => ({ count: item.count, status: item.status })),
		totalReports: response.total_reports,
	};
}

export async function fetchSystemFallback(scope: SystemOverviewScope): Promise<SystemFallbackSummary> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/source-fallback/summary", {
		params: { query: scopedQuery(scope) },
	});
	return {
		approvalRequiredCount: response.approval_required_count,
		executionAllowedCount: response.execution_allowed_count,
		previews: response.previews.map((item) => ({
			datasetId: item.dataset_id,
			defaultSource: item.default_source,
			policyStatus: item.policy_status,
			recommendedSource: item.recommended_source ?? null,
			selectedSource: item.selected_source,
		})),
		statusCounts: response.policy_status_counts.map((item) => ({ count: item.count, status: item.status })),
		totalPreviews: response.total_previews,
	};
}

export async function fetchSystemPromotion(scope: SystemOverviewScope): Promise<SystemPromotionReadiness> {
	const response = await apiClient.get("/api/v1/ingestion/catalog/promotion/readiness", {
		params: { query: scopedQuery(scope) },
	});
	return {
		activePromotionCount: response.active_promotion_count,
		datasetCount: response.dataset_count,
		datasets: response.datasets.map((item) => ({
			currentMaturity: item.current_maturity ?? null,
			datasetId: item.dataset_id,
			missingCriteria: item.missing_criteria ?? [],
			status: item.promotion_status,
		})),
		promotableCount: response.promotable_count,
		statusCounts: response.status_counts.map((item) => ({ count: item.count, status: item.status })),
	};
}
