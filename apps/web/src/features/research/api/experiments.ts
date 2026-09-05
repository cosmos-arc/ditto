/**
 * Experiment adapter（research 域，R3 live-shape）。
 *
 * 列表、只读 preflight 与 launch 均只消费 frozen generated DTO；完整 detail/control
 * query graph 由 experiment workbench adapter 扩展。
 */

import { apiClient, preserveExactJson } from "@/api";
import type { components, operations } from "@/api/generated/schema";
import type { ExperimentListItem } from "@/types";

export type ExperimentSummaryResponse = components["schemas"]["ExperimentSummaryResponse"];
export type ExperimentDetailResponse = components["schemas"]["ExperimentDetailResponse"];
export type ExperimentCandidateResponse = components["schemas"]["ExperimentCandidateResponse"];
export type ExperimentGateResponse = components["schemas"]["ExperimentGateResponse"];
export type ExperimentComparisonResponse = components["schemas"]["ExperimentComparisonResponse"];
export type ExperimentArtifactResponse = components["schemas"]["ExperimentArtifactResponse"];
export type ExperimentSelectionEvidenceResponse = components["schemas"]["ExperimentSelectionEvidenceResponse"];
export type ExperimentFoldResponse = components["schemas"]["ExperimentFoldResponse"];
export type ExperimentSelectionStateResponse = components["schemas"]["ExperimentSelectionStateResponse"];
export type ExperimentControlReceiptResponse = components["schemas"]["ExperimentControlReceiptResponse"];
export type CandidateSelectionRequest = components["schemas"]["CandidateSelectionRequest"];
export type CandidateSelectionReceiptResponse = components["schemas"]["CandidateSelectionReceiptResponse"];
export type HoldoutEvaluationRequest = components["schemas"]["HoldoutEvaluationRequest"];
export type HoldoutEvaluationReceiptResponse = components["schemas"]["HoldoutEvaluationReceiptResponse"];
type ExperimentPlanningOperation = operations["research_preflight_experiment"];
type ExperimentLaunchOperation = operations["research_launch_experiment"];
export type ExperimentPlanningRequest = ExperimentPlanningOperation["requestBody"]["content"]["application/json"];
export type ExperimentPreflightResponse = components["schemas"]["ExperimentPreflightResponse"];
export type ExperimentLaunchResponse = components["schemas"]["ExperimentLaunchResponse"];
type ExperimentLaunchRequest = ExperimentLaunchOperation["requestBody"]["content"]["application/json"];

const rawPlanningJsonByRequest = new WeakMap<object, string>();

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

export type ExperimentControlAction = "pause" | "cancel" | "resume";

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

function encodeScalar(value: string | number | boolean | null, label: string): string {
	if (typeof value === "number" && !Number.isFinite(value)) throw new Error(`${label} 必须是有限数值`);
	const encoded = JSON.stringify(value);
	if (encoded === undefined) throw new Error(`${label} 无法编码为 JSON`);
	return encoded;
}

function serializeExperimentPlanningDraft(draft: ExperimentConfigDraft): string {
	const strategySpec = draft.strategySpecJson.trim();
	const validation = draft.validationJson.trim();
	const baselinePayload = draft.baselinePayloadJson.trim();
	const axes = draft.axesJson.trim();
	const promotionObjective = draft.promotionObjectiveJson.trim();
	const datasetRequirements = draft.datasetRequirementsJson.trim();
	return `{${[
		`"experiment_id":${encodeScalar(draft.experimentId.trim(), "Experiment ID")}`,
		`"research_cycle_id":${encodeScalar(draft.researchCycleId.trim(), "Research cycle ID")}`,
		`"research_cycle_hash":${encodeScalar(draft.researchCycleHash.trim(), "Research cycle hash")}`,
		`"strategy":{"strategy_id":${encodeScalar(draft.strategyId.trim(), "Strategy ID")},"version":${encodeScalar(draft.strategyVersion, "Strategy version")},"spec_hash":${encodeScalar(draft.strategySpecHash.trim(), "Strategy spec hash")},"spec_json":${strategySpec}}`,
		`"snapshot":{"snapshot_id":${encodeScalar(draft.snapshotId.trim(), "Snapshot ID")},"manifest_hash":${encodeScalar(draft.snapshotManifestHash.trim(), "Snapshot manifest hash")}}`,
		`"validation":${validation}`,
		`"matrix":{"baseline":{"descriptor_type":${encodeScalar(draft.baselineDescriptorType.trim(), "Baseline descriptor")},"payload":${baselinePayload},"schema_version":${encodeScalar(draft.baselineSchemaVersion, "Baseline schema version")}},"axes":${axes},"candidate_limit":${encodeScalar(draft.candidateLimit, "Candidate limit")}}`,
		`"promotion_objective":${promotionObjective}`,
		`"dataset_requirements":${datasetRequirements}`,
		`"cost_model":{"bytes_per_run":${encodeScalar(draft.bytesPerRun, "Bytes per run")},"bytes_per_trading_session":${encodeScalar(draft.bytesPerTradingSession, "Bytes per trading session")}}`,
		`"budget":{"candidate_limit":${encodeScalar(draft.candidateLimit, "Candidate limit")},"fold_run_limit":${encodeScalar(draft.foldRunLimit, "Fold run limit")},"trading_session_limit":${encodeScalar(draft.tradingSessionLimit, "Trading session limit")},"disk_byte_limit":${encodeScalar(draft.diskByteLimit, "Disk byte limit")}}`,
		`"seed":${encodeScalar(draft.seed, "Seed")}`,
		`"worker_count":${encodeScalar(draft.workerCount, "Worker count")}`,
		`"failure_policy":${encodeScalar(draft.failurePolicy, "Failure policy")}`,
		`"created_at":${encodeScalar(draft.createdAt, "Created at")}`,
	].join(",")}}`;
}

export function createDefaultExperimentDraft(): ExperimentConfigDraft {
	return {
		experimentId: "r3-experiment",
		researchCycleId: "r3-cycle",
		researchCycleHash: "a".repeat(64),
		strategyId: "seed_stock_selection_rotation",
		strategyVersion: 1,
		strategySpecHash: "b".repeat(64),
		strategySpecJson: JSON.stringify({ strategy_id: "seed_stock_selection_rotation" }, null, 2),
		snapshotId: "certified-snapshot-r3",
		snapshotManifestHash: "c".repeat(64),
		validationJson: JSON.stringify({ trading_sessions: ["2026-07-30"] }, null, 2),
		baselineDescriptorType: "active-strategy",
		baselineSchemaVersion: 1,
		baselinePayloadJson: JSON.stringify({ strategy_id: "seed_stock_selection_rotation" }, null, 2),
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
			const values = (axis as Record<string, unknown>)["values"];
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
	const request: ExperimentPlanningRequest = {
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
	rawPlanningJsonByRequest.set(request, serializeExperimentPlanningDraft(draft));
	return request;
}

export function planningRequestIdentity(planning: ExperimentPlanningRequest): string {
	return rawPlanningJsonByRequest.get(planning) ?? JSON.stringify(planning);
}

export function preflightExperiment(planning: ExperimentPlanningRequest): Promise<ExperimentPreflightResponse> {
	return apiClient.post("/api/v1/research/experiments/{experiment_id}/preflight", {
		body: planning,
		exactJson: preserveExactJson(planning, planningRequestIdentity(planning)),
		params: { path: { experiment_id: planning.experiment_id } },
	});
}

export function launchExperiment(
	planning: ExperimentPlanningRequest,
	confirmedPlanHash: string,
	idempotencyKey: string,
): Promise<ExperimentLaunchResponse> {
	const request: ExperimentLaunchRequest = { ...planning, confirmed_plan_hash: confirmedPlanHash };
	const planningJson = planningRequestIdentity(planning);
	const rawBody = `${planningJson.slice(0, -1)},"confirmed_plan_hash":${encodeScalar(request.confirmed_plan_hash, "Confirmed plan hash")}}`;
	return apiClient.post("/api/v1/research/experiments", {
		body: request,
		exactJson: preserveExactJson(request, rawBody),
		params: { header: { "Idempotency-Key": idempotencyKey } },
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

/** 列出实验（`GET /api/v1/research/experiments`）。 */
export function fetchExperiments(): Promise<ExperimentSummaryResponse[]> {
	return apiClient.get("/api/v1/research/experiments");
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

export function fetchExperiment(experimentId: string): Promise<ExperimentDetailResponse> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}", {
		params: { path: { experiment_id: experimentId } },
	});
}

export function fetchExperimentCandidates(experimentId: string): Promise<ExperimentCandidateResponse[]> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}/candidates", {
		params: { path: { experiment_id: experimentId } },
	});
}

export function fetchExperimentGates(experimentId: string): Promise<ExperimentGateResponse[]> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}/gates", {
		params: { path: { experiment_id: experimentId } },
	});
}

export function fetchExperimentComparison(experimentId: string): Promise<ExperimentComparisonResponse> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}/comparison", {
		params: { path: { experiment_id: experimentId } },
	});
}

export function fetchExperimentArtifacts(experimentId: string): Promise<ExperimentArtifactResponse[]> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}/artifacts", {
		params: { path: { experiment_id: experimentId } },
	});
}

export function fetchExperimentSelectionEvidence(experimentId: string): Promise<ExperimentSelectionEvidenceResponse> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}/selection-evidence", {
		params: { path: { experiment_id: experimentId } },
	});
}

export function controlExperiment(
	experimentId: string,
	action: ExperimentControlAction,
	expectedRevision: number,
	idempotencyKey: string,
): Promise<ExperimentControlReceiptResponse> {
	const init = {
		body: { expected_revision: expectedRevision },
		params: {
			path: { experiment_id: experimentId },
			header: { "Idempotency-Key": idempotencyKey },
		},
	};
	switch (action) {
		case "pause":
			return apiClient.post("/api/v1/research/experiments/{experiment_id}/pause", init);
		case "cancel":
			return apiClient.post("/api/v1/research/experiments/{experiment_id}/cancel", init);
		case "resume":
			return apiClient.post("/api/v1/research/experiments/{experiment_id}/resume", init);
	}
}

export function retryExperimentFold(
	experimentId: string,
	request: components["schemas"]["ExperimentRetryFoldRequest"],
	idempotencyKey: string,
): Promise<ExperimentControlReceiptResponse> {
	return apiClient.post("/api/v1/research/experiments/{experiment_id}/retry-fold", {
		body: request,
		params: {
			path: { experiment_id: experimentId },
			header: { "Idempotency-Key": idempotencyKey },
		},
	});
}

export function selectExperimentCandidate(
	experimentId: string,
	request: CandidateSelectionRequest,
	idempotencyKey: string,
): Promise<CandidateSelectionReceiptResponse> {
	return apiClient.post("/api/v1/research/experiments/{experiment_id}/candidate-selection", {
		body: request,
		params: {
			path: { experiment_id: experimentId },
			header: { "Idempotency-Key": idempotencyKey },
		},
	});
}

export function evaluateExperimentHoldout(
	experimentId: string,
	request: HoldoutEvaluationRequest,
	idempotencyKey: string,
): Promise<HoldoutEvaluationReceiptResponse> {
	return apiClient.post("/api/v1/research/experiments/{experiment_id}/holdout-evaluations", {
		body: request,
		params: {
			path: { experiment_id: experimentId },
			header: { "Idempotency-Key": idempotencyKey },
		},
	});
}
