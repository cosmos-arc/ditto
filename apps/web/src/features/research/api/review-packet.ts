/**
 * Review-packet adapter（research 域，R3 live-shape）。
 *
 * `GET /api/v1/research/experiments/{id}/review-packet` → `ExperimentReviewPacketResponse`
 * （完整 ReviewPacket read model：11 hard-gate + 证据 hash + lineage + rationale）。
 * adapter 返回解封后的 generated DTO，mapper 翻译为 camelCase view-model。
 */

import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";
import type { ReviewGate, ReviewPacket, ReviewSelectionExposure, SelectionTraceRef } from "@/types/review";

export type ExperimentReviewPacketResponse = components["schemas"]["ExperimentReviewPacketResponse"];
export type ReviewGateOutcomeResponse = components["schemas"]["ReviewGateOutcomeResponse"];
export type ReviewSelectionTraceRefResponse = components["schemas"]["ReviewSelectionTraceRefResponse"];

/** 读取一个 experiment 的 review packet（`GET /api/v1/research/experiments/{id}/review-packet`）。 */
export function fetchReviewPacket(experimentId: string): Promise<ExperimentReviewPacketResponse> {
	return apiClient.get("/api/v1/research/experiments/{experiment_id}/review-packet", {
		params: { path: { experiment_id: experimentId } },
	});
}

function mapGate(dto: ReviewGateOutcomeResponse): ReviewGate {
	return { ruleId: dto.rule_id, layer: dto.layer, outcome: dto.outcome };
}

function mapSelectionTraceRef(dto: ReviewSelectionTraceRefResponse): SelectionTraceRef {
	return {
		artifactKind: dto.artifact_kind,
		artifactId: dto.artifact_id,
		contentHash: dto.content_hash,
	};
}

function mapSelectionExposure(
	dto: components["schemas"]["ReviewSelectionExposureResponse"] | null,
): ReviewSelectionExposure | null {
	if (!dto) return null;
	return {
		lane: dto.lane,
		applicability: dto.applicability,
		industryWeights: dto.industry_weights.map((entry) => ({ key: entry.key, weight: entry.weight })),
		sizeBucketWeights: dto.size_bucket_weights.map((entry) => ({ key: entry.key, weight: entry.weight })),
		artifactRefs: dto.artifact_refs.map(mapSelectionTraceRef),
	};
}

export function mapReviewPacket(dto: ExperimentReviewPacketResponse): ReviewPacket {
	return {
		experimentId: dto.experiment_id,
		candidateId: dto.candidate_id,
		bundleHash: dto.bundle_hash,
		hardReviewBlocked: dto.hard_review_blocked,
		gateOutcomes: dto.gate_outcomes.map(mapGate),
		schemaVersion: dto.schema_version,
		foldIds: dto.fold_ids,
		attemptIds: dto.attempt_ids,
		specHash: dto.spec_hash,
		resolvedSpecHash: dto.resolved_spec_hash,
		parameterHash: dto.parameter_hash,
		snapshotHash: dto.snapshot_hash,
		registryHash: dto.registry_hash,
		objectivePayloadHash: dto.objective_payload_hash,
		comparisonPayloadHash: dto.comparison_payload_hash,
		r1ImpactPayloadHash: dto.r1_impact_payload_hash,
		selectionEvidenceArtifactId: dto.selection_evidence_artifact_id,
		selectionExposure: mapSelectionExposure(dto.selection_exposure),
		holdoutClaimId: dto.holdout_claim_id,
		candidateRationale: dto.candidate_rationale,
		selectionTraceArtifactRefs: dto.selection_trace_artifact_refs.map(mapSelectionTraceRef),
	};
}
