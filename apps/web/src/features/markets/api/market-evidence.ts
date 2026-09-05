import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

export type MacroIndicator = components["schemas"]["Indicator"];
export type MarketContext = components["schemas"]["MarketContextResponse"];

export type MarketContextScope = {
	readonly asOf: string;
	readonly knowledgeCutoff: string;
	readonly publicationCutoff: string;
	readonly sourceSnapshotIds: readonly string[];
};

function assertMarketContextScope(scope: MarketContextScope): void {
	if (
		scope.sourceSnapshotIds.length === 0 ||
		new Set(scope.sourceSnapshotIds).size !== scope.sourceSnapshotIds.length
	) {
		throw new Error("market context requires unique exact source snapshot IDs");
	}
}

export function fetchMarketContext(scope: MarketContextScope): Promise<MarketContext> {
	assertMarketContextScope(scope);
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
