/**
 * Experiment adapter（research 域，R3 live-shape）。
 *
 * 列表、只读 preflight 与 launch 均只消费 frozen generated DTO；完整 detail/control
 * query graph 由 experiment workbench adapter 扩展。
 */

import { apiClient } from "@/lib/api-client";
import type { ExperimentListItem } from "@/types";
import type { components, operations } from "@/types/generated/api";

export type ExperimentSummaryResponse = components["schemas"]["ExperimentSummaryResponse"];
type ExperimentPlanningOperation = operations["research_preflight_experiment"];
type ExperimentLaunchOperation = operations["research_launch_experiment"];
export type ExperimentPlanningRequest = ExperimentPlanningOperation["requestBody"]["content"]["application/json"];
export type ExperimentPreflightResponse = components["schemas"]["ExperimentPreflightResponse"];
export type ExperimentLaunchResponse = components["schemas"]["ExperimentLaunchResponse"];
type ExperimentLaunchRequest = ExperimentLaunchOperation["requestBody"]["content"]["application/json"];

export type ExperimentConfigDraft = {
	readonly experimentId: string;
	readonly researchCycleId: string;
	readonly researchCycleHash: string;
	readonly strategyId: string;
	readonly strategyVersion: number;
	readonly strategySpecHash: string;
	readonly strategySpecJson: string;
	readonly snapshotId: string;
	readonly snapshotManifestHash: string;
	readonly validationJson: string;
	readonly baselineDescriptorType: string;
	readonly baselineSchemaVersion: number;
	readonly baselinePayloadJson: string;
	readonly axesJson: string;
	readonly candidateLimit: number;
	readonly promotionObjectiveJson: string;
	readonly datasetRequirementsJson: string;
	readonly bytesPerRun: number;
	readonly bytesPerTradingSession: number;
	readonly foldRunLimit: number;
	readonly tradingSessionLimit: number;
	readonly diskByteLimit: number;
	readonly seed: number;
	readonly workerCount: 2 | 4;
	readonly failurePolicy: "continue_candidate_failures" | "fail_fast";
	readonly createdAt: string;
};

export type ExperimentPreflightCheck = {
	readonly ruleId: string;
	readonly outcome: string;
	readonly code: string | null;
	readonly reason: string | null;
	readonly remediation: string | null;
	readonly observed: Readonly<Record<string, unknown>>;
	readonly policy: Readonly<Record<string, unknown>>;
};

export type ExperimentPreflight = {
	readonly status: string;
	readonly planHash: string | null;
	readonly checks: readonly ExperimentPreflightCheck[];
	readonly candidateCount: number;
	readonly plannedFoldCount: number;
	readonly budgetRunCount: number;
	readonly estimatedTradingSessions: number;
	readonly estimatedDiskBytes: number;
	readonly eligibleMonthCount: number;
	readonly isolationWidthSessions: number;
};

export type ExperimentLaunchReceipt = {
	readonly experimentId: string;
	readonly status: string;
	readonly queueOrdinal: number;
	readonly revision: number;
	readonly planHash: string;
	readonly candidateCount: number;
	readonly foldCount: number;
};

function parseRecord(value: string, label: string): Record<string, unknown> {
	const parsed = JSON.parse(value) as unknown;
	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
		throw new Error(`${label} 必须是 JSON object`);
	}
	return parsed as Record<string, unknown>;
}

function parseArray(value: string, label: string): unknown[] {
	const parsed = JSON.parse(value) as unknown;
	if (!Array.isArray(parsed)) throw new Error(`${label} 必须是 JSON array`);
	return parsed;
}

export function createDefaultExperimentDraft(): ExperimentConfigDraft {
	return {
		experimentId: "r3-experiment",
		researchCycleId: "r3-cycle",
		researchCycleHash: "a".repeat(64),
		strategyId: "seed_stock_selection",
		strategyVersion: 1,
		strategySpecHash: "b".repeat(64),
		strategySpecJson: JSON.stringify({ strategy_id: "seed_stock_selection" }, null, 2),
		snapshotId: "certified-snapshot-r3",
		snapshotManifestHash: "c".repeat(64),
		validationJson: JSON.stringify({ trading_sessions: ["2026-07-30"] }, null, 2),
		baselineDescriptorType: "active-strategy",
		baselineSchemaVersion: 1,
		baselinePayloadJson: JSON.stringify({ strategy_id: "seed_stock_selection" }, null, 2),
		axesJson: JSON.stringify(
			[
				{
					name: "selector.top_k",
					values: [
						{ type: "int", value: 5 },
						{ type: "int", value: 10 },
					],
				},
			],
			null,
			2,
		),
		candidateLimit: 128,
		promotionObjectiveJson: JSON.stringify({ schema_id: "r3-promotion-objective", schema_version: 1 }, null, 2),
		datasetRequirementsJson: JSON.stringify(
			[
				{
					dataset_id: "stock_daily",
					expected_snapshot_ids: ["provider-snapshot-r3"],
					requires_pit_universe: true,
					certified_from: "2016-01-01",
				},
			],
			null,
			2,
		),
		bytesPerRun: 100,
		bytesPerTradingSession: 2,
		foldRunLimit: 1000,
		tradingSessionLimit: 1_000_000,
		diskByteLimit: 100_000_000,
		seed: 42,
		workerCount: 2,
		failurePolicy: "continue_candidate_failures",
		createdAt: new Date().toISOString(),
	};
}

export function estimateCandidateCount(axesJson: string): number | null {
	try {
		const axes = parseArray(axesJson, "Matrix axes");
		if (axes.length === 0) return 1;
		const combinations = axes.reduce<number>((count, axis) => {
			if (typeof axis !== "object" || axis === null || Array.isArray(axis)) throw new Error("invalid axis");
			const values = (axis as Record<string, unknown>).values;
			if (!Array.isArray(values) || values.length === 0) throw new Error("invalid axis values");
			return count * values.length;
		}, 1);
		return 1 + combinations;
	} catch {
		return null;
	}
}

/** Canonical planning document construction lives here and nowhere in the component tree. */
export function buildExperimentPlanningRequest(draft: ExperimentConfigDraft): ExperimentPlanningRequest {
	return {
		experiment_id: draft.experimentId.trim(),
		research_cycle_id: draft.researchCycleId.trim(),
		research_cycle_hash: draft.researchCycleHash.trim(),
		strategy: {
			strategy_id: draft.strategyId.trim(),
			version: draft.strategyVersion,
			spec_hash: draft.strategySpecHash.trim(),
			spec_json: parseRecord(draft.strategySpecJson, "Strategy spec"),
		},
		snapshot: { snapshot_id: draft.snapshotId.trim(), manifest_hash: draft.snapshotManifestHash.trim() },
		validation: parseRecord(draft.validationJson, "Validation"),
		matrix: {
			baseline: {
				descriptor_type: draft.baselineDescriptorType.trim(),
				payload: parseRecord(draft.baselinePayloadJson, "Baseline payload"),
				schema_version: draft.baselineSchemaVersion,
			},
			axes: parseArray(draft.axesJson, "Matrix axes") as ExperimentPlanningRequest["matrix"]["axes"],
			candidate_limit: draft.candidateLimit,
		},
		promotion_objective: parseRecord(draft.promotionObjectiveJson, "Promotion objective"),
		dataset_requirements: parseArray(
			draft.datasetRequirementsJson,
			"Dataset requirements",
		) as ExperimentPlanningRequest["dataset_requirements"],
		cost_model: {
			bytes_per_run: draft.bytesPerRun,
			bytes_per_trading_session: draft.bytesPerTradingSession,
		},
		budget: {
			candidate_limit: draft.candidateLimit,
			fold_run_limit: draft.foldRunLimit,
			trading_session_limit: draft.tradingSessionLimit,
			disk_byte_limit: draft.diskByteLimit,
		},
		seed: draft.seed,
		worker_count: draft.workerCount,
		failure_policy: draft.failurePolicy,
		created_at: draft.createdAt,
	};
}

export function preflightExperiment(planning: ExperimentPlanningRequest): Promise<ExperimentPreflightResponse> {
	return apiClient.post<ExperimentPreflightResponse>(
		`/v1/research/experiments/${encodeURIComponent(planning.experiment_id)}/preflight`,
		planning,
	);
}

export function launchExperiment(
	planning: ExperimentPlanningRequest,
	confirmedPlanHash: string,
	idempotencyKey: string,
): Promise<ExperimentLaunchResponse> {
	const request: ExperimentLaunchRequest = { ...planning, confirmed_plan_hash: confirmedPlanHash };
	return apiClient.post<ExperimentLaunchResponse>("/v1/research/experiments", request, {
		headers: { "Idempotency-Key": idempotencyKey },
	});
}

export function mapExperimentPreflight(dto: ExperimentPreflightResponse): ExperimentPreflight {
	return {
		status: dto.status,
		planHash: dto.plan_hash,
		checks: dto.checks.map((check) => ({
			ruleId: check.rule_id,
			outcome: check.outcome,
			code: check.code,
			reason: check.reason,
			remediation: check.remediation,
			observed: { ...check.observed },
			policy: { ...check.policy },
		})),
		candidateCount: dto.candidate_count,
		plannedFoldCount: dto.planned_fold_count,
		budgetRunCount: dto.budget_run_count,
		estimatedTradingSessions: dto.estimated_trading_sessions,
		estimatedDiskBytes: dto.estimated_disk_bytes,
		eligibleMonthCount: dto.eligible_month_count,
		isolationWidthSessions: dto.isolation_width_sessions,
	};
}

export function mapExperimentLaunchReceipt(dto: ExperimentLaunchResponse): ExperimentLaunchReceipt {
	return {
		experimentId: dto.experiment_id,
		status: dto.status,
		queueOrdinal: dto.queue_ordinal,
		revision: dto.revision,
		planHash: dto.plan_hash,
		candidateCount: dto.candidate_count,
		foldCount: dto.fold_count,
	};
}

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
