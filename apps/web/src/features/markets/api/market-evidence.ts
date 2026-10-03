import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export type MacroIndicator = components["schemas"]["Indicator"];
export type MarketContext = components["schemas"]["MarketContextResponse"];

export type MarketContextScope = {
	readonly asOf: string;
	readonly knowledgeCutoff: string;
	readonly publicationCutoff: string;
	readonly sourceSnapshotIds: readonly string[];
};

function assertMarketContextScope(scope: MarketContextScope): void {
	// 空快照集合法：服务端解析 observed 快照集；非空时仍要求唯一精确身份。
	if (new Set(scope.sourceSnapshotIds).size !== scope.sourceSnapshotIds.length) {
		throw new Error("market context requires unique exact source snapshot IDs");
	}
}

export function fetchMarketContext(scope: MarketContextScope): Promise<MarketContext> {
	assertMarketContextScope(scope);
	// openapi-fetch 跳过空数组参数，因此空快照集不会发出 source_snapshot_id 查询参数。
	return apiClient.get("/api/v1/market/context", {
		params: {
			query: {
				as_of: scope.asOf,
				knowledge_cutoff: scope.knowledgeCutoff,
				publication_cutoff: scope.publicationCutoff,
				source_snapshot_id: [...scope.sourceSnapshotIds],
			},
		},
	});
}

/** Calendar dataset ingestion status projection (see backend DatasetStatusResponse). */
export type MarketCalendarStatus = {
	readonly dataset: string;
	readonly latest_date: string | null;
	readonly latest_status: string | null;
	readonly record_count: number;
	readonly catalog_freshness_at: string | null;
};

export async function fetchCalendarStatus(): Promise<MarketCalendarStatus> {
	const response = await apiClient.get("/api/v1/ingestion/status");
	const calendar = response.datasets.find((dataset) => dataset.dataset === "calendar");
	if (!calendar) throw new Error("ingestion status does not report the calendar dataset");
	return {
		dataset: calendar.dataset,
		latest_date: calendar.latest_date ?? null,
		latest_status: calendar.latest_status ?? null,
		record_count: calendar.record_count,
		catalog_freshness_at: calendar.catalog_freshness_at ?? null,
	};
}

export type MacroEvidenceRange = {
	readonly allowExperimentalData: boolean;
	readonly endDate: string;
	readonly startDate: string;
};

export function fetchMacroEvidence(range: MacroEvidenceRange): Promise<readonly MacroIndicator[]> {
	if (!range.allowExperimentalData) throw new Error("experimental macro data must be explicitly enabled");
	if (!range.startDate || !range.endDate || range.startDate > range.endDate) throw new Error("宏观查询日期范围无效");

	return apiClient.get("/api/v1/macro/indicators/metadata", {
		params: {
			query: {
				allow_experimental_data: true,
				end: range.endDate,
				start: range.startDate,
			},
		},
	});
}
