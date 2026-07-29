import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import type { StrategyResponse } from "./strategies";

export type StrategySpecValidateRequest = components["schemas"]["StrategySpecValidateRequest"];
export type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
export type CreateStrategyRequest = components["schemas"]["CreateStrategyRequest"];
export type UpdateStrategyRequest = components["schemas"]["UpdateStrategyRequest"];

/**
 * Pre-save candidate spec 校验（`POST /v1/strategies/{id}/versions/{v}/validate`）。
 *
 * 后端对非法 candidate 返 200 + `valid=false`（不抛）；仅 version 不存在时 404。
 */
export function validateSpec(
	strategyId: string,
	version: number,
	specJson: Readonly<Record<string, unknown>>,
): Promise<StrategySpecValidationResponse> {
	return apiClient.post<StrategySpecValidationResponse>(
		`/v1/strategies/${encodeURIComponent(strategyId)}/versions/${version}/validate`,
		{ spec_json: specJson } satisfies StrategySpecValidateRequest,
	);
}

/** 创建新策略（`POST /v1/strategies`），用于 Studio 新建 draft。 */
export function createStrategy(payload: CreateStrategyRequest): Promise<StrategyResponse> {
	return apiClient.post<StrategyResponse>("/v1/strategies", payload);
}

/** 更新策略（`PUT /v1/strategies/{id}`），version 字段为乐观锁。 */
export function updateStrategy(strategyId: string, payload: UpdateStrategyRequest): Promise<StrategyResponse> {
	return apiClient.put<StrategyResponse>(`/v1/strategies/${encodeURIComponent(strategyId)}`, payload);
}
