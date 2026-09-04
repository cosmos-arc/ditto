import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type TechnicalAnalysisQueryBody = components["schemas"]["TechnicalAnalysisQueryBody"];
export type TechnicalAnalysisSnapshot = components["schemas"]["TechnicalAnalysisSnapshotResponse"];

export function queryTechnicalAnalysis(body: TechnicalAnalysisQueryBody): Promise<TechnicalAnalysisSnapshot> {
	return apiClient.post<TechnicalAnalysisSnapshot>("/v1/technical-analysis/snapshots/query", body);
}
