import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components, operations } from "@/types/generated/api";
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

type VersionDetailPath = operations["design_strategy_version_detail"]["parameters"]["path"];

/** 读取一个 immutable 历史版本的 canonical payload，不回退当前策略详情。 */
export function fetchStrategyVersionDetail(
	strategyId: VersionDetailPath["strategy_id"],
	version: VersionDetailPath["version"],
): Promise<StrategyVersionDetailResponse> {
	return apiClient.get<StrategyVersionDetailResponse>(
		`/v1/strategies/${encodeURIComponent(strategyId)}/versions/${version}`,
	);
}

/** 读取版本 vs parent 的字段级 canonical spec diff（`GET /v1/strategies/{id}/versions/{v}/diff`）。 */
export function fetchVersionDiff(strategyId: string, version: number): Promise<StrategyVersionDiffResponse> {
	return apiClient.get<StrategyVersionDiffResponse>(
		`/v1/strategies/${encodeURIComponent(strategyId)}/versions/${version}/diff`,
	);
}

export type StrategyActiveResponse = components["schemas"]["StrategyActiveResponse"];

/** 读取 active pointer（`GET /v1/strategies/{id}/active`）；无 active 时后端返 404。 */
export function fetchActive(strategyId: string): Promise<StrategyActiveResponse> {
	return apiClient.get<StrategyActiveResponse>(`/v1/strategies/${encodeURIComponent(strategyId)}/active`);
}

export function fetchStrategyEvents(
	strategyId: string,
	afterEventId: string | null,
	limit: number,
): Promise<StrategyGovernanceEventResponse[]> {
	return apiClient.get<StrategyGovernanceEventResponse[]>(
		withQueryParams(`/v1/strategies/${encodeURIComponent(strategyId)}/events`, {
			after_event_id: afterEventId,
			limit,
		}),
	);
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
