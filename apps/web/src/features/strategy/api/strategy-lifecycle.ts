import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";
import type { StrategyResponse } from "./strategies";

export type StrategySpecValidateRequest = components["schemas"]["StrategySpecValidateRequest"];
export type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
export type StrategyAuthorPreviewRequest = components["schemas"]["StrategyAuthorPreviewRequest"];
export type StrategyAuthorPreviewResponse = components["schemas"]["StrategyAuthorPreviewResponse"];
export type CreateStrategyRequest = components["schemas"]["CreateStrategyRequest"];
export type UpdateStrategyRequest = components["schemas"]["UpdateStrategyRequest"];
export type GovernanceDecisionRequest = components["schemas"]["GovernanceDecisionRequest"];
export type SubmitReviewRequest = components["schemas"]["SubmitReviewRequest"];
export type ReactivateStrategyRequest = components["schemas"]["ReactivateStrategyRequest"];
export type PublishStrategyVersionRequest = components["schemas"]["PublishStrategyVersionRequest"];
export type StrategyVersionStateResponse = components["schemas"]["StrategyVersionStateResponse"];
export type StrategyActivePointerResponse = components["schemas"]["StrategyActivePointerResponse"];

function versionParams(strategyId: string, version: number) {
	return { strategy_id: strategyId, version };
}

/**
 * Pre-save candidate spec 校验（`POST /api/v1/strategies/{id}/versions/{v}/validate`）。
 *
 * 后端对非法 candidate 返 200 + `valid=false`（不抛）；仅 version 不存在时 404。
 */
export function validateSpec(
	strategyId: string,
	version: number,
	specJson: StrategySpecValidateRequest["spec_json"],
): Promise<StrategySpecValidationResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/validate", {
		body: { spec_json: specJson } satisfies StrategySpecValidateRequest,
		params: { path: versionParams(strategyId, version) },
	});
}

/** Run every detached Author stage without saving, reviewing, or publishing. */
export function previewStrategyAuthor(
	strategyId: string,
	version: number,
	payload: StrategyAuthorPreviewRequest,
): Promise<StrategyAuthorPreviewResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/author-preview", {
		body: payload,
		params: { path: versionParams(strategyId, version) },
	});
}

/** 创建新策略（`POST /api/v1/strategies`），用于 Studio 新建 draft。 */
export function createStrategy(payload: CreateStrategyRequest, idempotencyKey: string): Promise<StrategyResponse> {
	return apiClient.post("/api/v1/strategies", {
		body: payload,
		params: { header: { "Idempotency-Key": idempotencyKey } },
	});
}

/** 更新策略（`PUT /api/v1/strategies/{id}`），version 字段为乐观锁，走 governance create_draft(parent)。 */
export function updateStrategy(
	strategyId: string,
	payload: UpdateStrategyRequest,
	idempotencyKey: string,
): Promise<StrategyResponse> {
	return apiClient.put("/api/v1/strategies/{strategy_id}", {
		body: payload,
		params: { path: { strategy_id: strategyId }, header: { "Idempotency-Key": idempotencyKey } },
	});
}

// === 治理 mutations（T20 版本治理动作面板）===

/** 提交版本审查（`POST .../submit-review`），draft → review。 */
export function submitStrategyReview(
	strategyId: string,
	version: number,
	body: SubmitReviewRequest,
	idempotencyKey: string,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/submit-review", {
		body,
		params: {
			path: versionParams(strategyId, version),
			header: { "Idempotency-Key": idempotencyKey },
		},
	});
}

/** 批准审查（`POST .../approve`），review → approved。 */
export function approveStrategyReview(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
	idempotencyKey: string,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/approve", {
		body,
		params: { path: versionParams(strategyId, version), header: { "Idempotency-Key": idempotencyKey } },
	});
}

/** 驳回审查（`POST .../reject`）；驳回后只能 clone 新 draft。 */
export function rejectStrategyReview(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
	idempotencyKey: string,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/reject", {
		body,
		params: { path: versionParams(strategyId, version), header: { "Idempotency-Key": idempotencyKey } },
	});
}

/** 弃用版本（`POST .../deprecate`）；弃用后不可再激活。 */
export function deprecateStrategyVersion(
	strategyId: string,
	version: number,
	body: GovernanceDecisionRequest,
	idempotencyKey: string,
): Promise<StrategyVersionStateResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/deprecate", {
		body,
		params: { path: versionParams(strategyId, version), header: { "Idempotency-Key": idempotencyKey } },
	});
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
	idempotencyKey: string,
): Promise<StrategyActivePointerResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/reactivate", {
		body,
		params: { path: versionParams(strategyId, version), header: { "Idempotency-Key": idempotencyKey } },
	});
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
	idempotencyKey: string,
): Promise<StrategyActivePointerResponse> {
	return apiClient.post("/api/v1/strategies/{strategy_id}/versions/{version}/publish", {
		body,
		params: { path: versionParams(strategyId, version), header: { "Idempotency-Key": idempotencyKey } },
	});
}
