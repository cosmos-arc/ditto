import { apiClient } from "@/api";
import type { components, operations } from "@/api/generated/schema";
import type { StrategyGovernanceEvent } from "@/types/strategy";

export type StrategyResponse = components["schemas"]["StrategyResponse"];
export type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
export type StrategyVersionDetailResponse = components["schemas"]["StrategyVersionDetailResponse"];
export type StrategyVersionDiffResponse = components["schemas"]["StrategyVersionDiffResponse"];
export type StrategyGovernanceEventResponse = components["schemas"]["StrategyGovernanceEventResponse"];

export type FetchStrategiesParams = {
	readonly limit?: number;
	readonly offset?: number;
};

/** 列出策略（`GET /api/v1/strategies`）。 */
export function fetchStrategies(params: FetchStrategiesParams = {}): Promise<StrategyResponse[]> {
	return apiClient.get("/api/v1/strategies", {
		params: {
			query: {
				...(params.limit === undefined ? {} : { limit: params.limit }),
				...(params.offset === undefined ? {} : { offset: params.offset }),
			},
		},
	});
}

/** 读取单个策略详情（`GET /api/v1/strategies/{id}`）。 */
export function fetchStrategy(strategyId: string): Promise<StrategyResponse> {
	return apiClient.get("/api/v1/strategies/{strategy_id}", { params: { path: { strategy_id: strategyId } } });
}

/** 列出策略的治理版本（`GET /api/v1/strategies/{id}/versions`）。 */
export function fetchStrategyVersions(strategyId: string): Promise<StrategyVersionResponse[]> {
	return apiClient.get("/api/v1/strategies/{strategy_id}/versions", {
		params: { path: { strategy_id: strategyId } },
	});
}

type VersionDetailPath = operations["design_strategy_version_detail"]["parameters"]["path"];

/** 读取一个 immutable 历史版本的 canonical payload，不回退当前策略详情。 */
export function fetchStrategyVersionDetail(
	strategyId: VersionDetailPath["strategy_id"],
	version: VersionDetailPath["version"],
): Promise<StrategyVersionDetailResponse> {
	return apiClient.get("/api/v1/strategies/{strategy_id}/versions/{version}", {
		params: { path: { strategy_id: strategyId, version } },
	});
}

/** 读取版本 vs parent 的字段级 canonical spec diff（`GET /api/v1/strategies/{id}/versions/{v}/diff`）。 */
export function fetchVersionDiff(strategyId: string, version: number): Promise<StrategyVersionDiffResponse> {
	return apiClient.get("/api/v1/strategies/{strategy_id}/versions/{version}/diff", {
		params: { path: { strategy_id: strategyId, version } },
	});
}

export type StrategyActiveResponse = components["schemas"]["StrategyActiveResponse"];

/** 读取 active pointer（`GET /api/v1/strategies/{id}/active`）；无 active 时后端返 404。 */
export function fetchActive(strategyId: string): Promise<StrategyActiveResponse> {
	return apiClient.get("/api/v1/strategies/{strategy_id}/active", {
		params: { path: { strategy_id: strategyId } },
	});
}

export function fetchStrategyEvents(
	strategyId: string,
	afterEventId: string | null,
	limit: number,
): Promise<StrategyGovernanceEventResponse[]> {
	return apiClient.get("/api/v1/strategies/{strategy_id}/events", {
		params: {
			path: { strategy_id: strategyId },
			query: { ...(afterEventId ? { after_event_id: afterEventId } : {}), limit },
		},
	});
}

export function mapStrategyGovernanceEvent(dto: StrategyGovernanceEventResponse): StrategyGovernanceEvent {
	return {
		eventId: dto.event_id,
		strategyId: dto.strategy_id,
		targetVersion: dto.target_version,
		eventType: dto.event_type,
		kind: dto.decision_or_activation_kind,
		actor: dto.actor,
		reason: dto.reason,
		occurredAt: dto.occurred_at,
	};
}
