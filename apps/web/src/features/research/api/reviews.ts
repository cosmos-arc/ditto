/**
 * Review queue adapter（research 域，R3 live-shape）。
 *
 * `GET /v1/research/reviews` → `StrategyVersionResponse[]`（REVIEW 态版本，
 * 含 experiment_id 桥接键）。adapter 返回解封后的 generated DTO，mapper 翻译为
 * camelCase view-model（`@/types/review`），组件只认 view-model。
 */
import { apiClient } from "@/lib/api-client";
import type { components } from "@/types/generated/api";
import type { ReviewQueueEntry } from "@/types/review";

export type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];

/** 列出 review queue（`GET /v1/research/reviews`）。 */
export function fetchReviews(): Promise<StrategyVersionResponse[]> {
	return apiClient.get<StrategyVersionResponse[]>("/v1/research/reviews");
}

export function mapReviewQueueEntry(dto: StrategyVersionResponse): ReviewQueueEntry {
	return {
		strategyId: dto.strategy_id,
		version: dto.version,
		parentVersion: dto.parent_version,
		specHash: dto.spec_hash,
		state: dto.state,
		reviewOutcome: dto.review_outcome,
		createdAt: dto.created_at,
		experimentId: dto.experiment_id ?? null,
	};
}
