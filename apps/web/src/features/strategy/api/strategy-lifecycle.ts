import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import type { StrategyResponse } from "./strategies";

export type StrategySpecValidateRequest = components["schemas"]["StrategySpecValidateRequest"];
export type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
export type CreateStrategyRequest = components["schemas"]["CreateStrategyRequest"];
export type UpdateStrategyRequest = components["schemas"]["UpdateStrategyRequest"];
export type GovernanceDecisionRequest = components["schemas"]["GovernanceDecisionRequest"];
export type ReactivateStrategyRequest = components["schemas"]["ReactivateStrategyRequest"];
export type PublishStrategyVersionRequest = components["schemas"]["PublishStrategyVersionRequest"];
export type StrategyVersionStateResponse = components["schemas"]["StrategyVersionStateResponse"];
export type StrategyActivePointerResponse = components["schemas"]["StrategyActivePointerResponse"];

/** 版本化治理路径前缀（`/v1/strategies/{id}/versions/{v}`）。 */
function versionedPath(strategyId: string, version: number): string {
	return `/v1/strategies/${encodeURIComponent(strategyId)}/versions/${version}`;
}

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
	return apiClient.post<StrategySpecValidationResponse>(`${versionedPath(strategyId, version)}/validate`, {
		spec_json: specJson,
	} satisfies StrategySpecValidateRequest);
}

/** 创建新策略（`POST /v1/strategies`），用于 Studio 新建 draft。 */
export function createStrategy(payload: CreateStrategyRequest): Promise<StrategyResponse> {
	return apiClient.post<StrategyResponse>("/v1/strategies", payload);
}

/** 更新策略（`PUT /v1/strategies/{id}`），version 字段为乐观锁，走 governance create_draft(parent)。 */
export function updateStrategy(
	strategyId: string,
	payload: UpdateStrategyRequest,
	idempotencyKey: string,
): Promise<StrategyResponse> {
	return apiClient.put<StrategyResponse>(`/v1/strategies/${encodeURIComponent(strategyId)}`, payload, {
		headers: { "Idempotency-Key": idempotencyKey },
	});
}

// === 治理 mutations（T20 版本治理动作面板）===

/** 提交版本审查（`POST .../submit-review`），draft → review。 */
export function submitStrategyReview(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post<StrategyVersionStateResponse>(`${versionedPath(strategyId, version)}/submit-review`, body);
}

/** 批准审查（`POST .../approve`），review → approved。 */
export function approveStrategyReview(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post<StrategyVersionStateResponse>(`${versionedPath(strategyId, version)}/approve`, body);
}

/** 驳回审查（`POST .../reject`）；驳回后只能 clone 新 draft。 */
export function rejectStrategyReview(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post<StrategyVersionStateResponse>(`${versionedPath(strategyId, version)}/reject`, body);
}

/** 弃用版本（`POST .../deprecate`）；弃用后不可再激活。 */
export function deprecateStrategyVersion(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post<StrategyVersionStateResponse>(`${versionedPath(strategyId, version)}/deprecate`, body);
}

/**
 * 重新激活已发布版本（`POST .../reactivate`，乐观指针 CAS）。
 *
 * 需 `expected_pointer_revision`（最后读到的 active pointer revision）+ confirmation 确认句。
 */
export function reactivateStrategyVersion(
	strategyId: string,
	version: number,
	body: ReactivateStrategyRequest,
): Promise<StrategyActivePointerResponse> {
	return apiClient.post<StrategyActivePointerResponse>(`${versionedPath(strategyId, version)}/reactivate`, body);
}

/**
 * 发布版本（`POST .../publish`，evidence-gated）。
 *
 * 需 `bundle_hash`（实验 ReviewPacket 的 content hash）；后端加载 packet 并执行 hard gate。
 * 本次前端 UI 不直接调用（无 bundle_hash 来源），adapter 备齐供 review-detail 后续使用。
 */
export function publishStrategyVersion(
	strategyId: string,
	version: number,
	body: PublishStrategyVersionRequest,
): Promise<StrategyActivePointerResponse> {
	return apiClient.post<StrategyActivePointerResponse>(`${versionedPath(strategyId, version)}/publish`, body);
}
