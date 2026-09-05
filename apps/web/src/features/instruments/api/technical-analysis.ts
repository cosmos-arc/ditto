import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

export type TechnicalAnalysisQueryBody = components["schemas"]["TechnicalAnalysisQueryBody"];
export type TechnicalAnalysisSnapshot = components["schemas"]["TechnicalAnalysisSnapshotResponse"];
export type TechnicalAnalysisSpecRequest = components["schemas"]["TechnicalAnalysisSpecRequest"];
export type TechnicalAnalysisDirection = components["schemas"]["Direction"];
export type TechnicalAnalysisIndicator = components["schemas"]["TechnicalAnalysisIndicatorResponse"];

export function queryTechnicalAnalysis(body: TechnicalAnalysisQueryBody): Promise<TechnicalAnalysisSnapshot> {
	return apiClient.post("/api/v1/technical-analysis/snapshots/query", { body });
}
