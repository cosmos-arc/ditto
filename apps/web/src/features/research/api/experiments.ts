/**
 * Experiment adapter（research 域，R3 live-shape）。
 *
 * T18 仅接线 experiment 列表（`GET /v1/research/experiments` → `ExperimentSummaryResponse`）。
 * 完整 experiment 工作台（detail/candidates/gates/control）属 T19 范围。
 */

import { apiClient } from "@/lib/api-client";
import type { ExperimentListItem } from "@/types";
import type { components } from "@/types/generated/api";

export type ExperimentSummaryResponse = components["schemas"]["ExperimentSummaryResponse"];

/** 列出实验（`GET /v1/research/experiments`）。 */
export function fetchExperiments(): Promise<ExperimentSummaryResponse[]> {
	return apiClient.get<ExperimentSummaryResponse[]>("/v1/research/experiments");
}

export function mapExperimentListItem(dto: ExperimentSummaryResponse): ExperimentListItem {
	return {
		experimentId: dto.experiment_id,
		status: dto.status,
		desiredState: dto.desired_state,
		stage: dto.stage,
		failureCode: dto.failure_code,
		queueOrdinal: dto.queue_ordinal,
		revision: dto.revision,
		createdAt: dto.created_at,
		updatedAt: dto.updated_at,
	};
}
