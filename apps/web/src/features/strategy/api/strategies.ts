import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

export type StrategyResponse = components["schemas"]["StrategyResponse"];
export type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
export type StrategyVersionDiffResponse = components["schemas"]["StrategyVersionDiffResponse"];

export type FetchStrategiesParams = {
	readonly limit?: number;
	readonly offset?: number;
};

/** 列出策略（`GET /v1/strategies`）。 */
export function fetchStrategies(params: FetchStrategiesParams = {}): Promise<StrategyResponse[]> {
	return apiClient.get<StrategyResponse[]>(
		withQueryParams("/v1/strategies", { limit: params.limit, offset: params.offset }),
	);
}

/** 读取单个策略详情（`GET /v1/strategies/{id}`）。 */
export function fetchStrategy(strategyId: string): Promise<StrategyResponse> {
	return apiClient.get<StrategyResponse>(`/v1/strategies/${encodeURIComponent(strategyId)}`);
}

/** 列出策略的治理版本（`GET /v1/strategies/{id}/versions`）。 */
export function fetchStrategyVersions(strategyId: string): Promise<StrategyVersionResponse[]> {
	return apiClient.get<StrategyVersionResponse[]>(`/v1/strategies/${encodeURIComponent(strategyId)}/versions`);
}

/** 读取版本 vs parent 的字段级 canonical spec diff（`GET /v1/strategies/{id}/versions/{v}/diff`）。 */
export function fetchVersionDiff(strategyId: string, version: number): Promise<StrategyVersionDiffResponse> {
	return apiClient.get<StrategyVersionDiffResponse>(
		`/v1/strategies/${encodeURIComponent(strategyId)}/versions/${version}/diff`,
	);
}
