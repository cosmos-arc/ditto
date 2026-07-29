import { describe, expect, it } from "vitest";
import type { components } from "@/types/generated/api";
import { mapReviewPacket } from "../api/review-packet";
import { mapReviewQueueEntry } from "../api/reviews";

type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
type ExperimentReviewPacketResponse = components["schemas"]["ExperimentReviewPacketResponse"];

describe("mapReviewQueueEntry", () => {
	it("translates snake_case DTO to camelCase view-model with experimentId bridge", () => {
		const dto: StrategyVersionResponse = {
			strategy_id: "seed_etf_rotation",
			version: 4,
			parent_version: 3,
			spec_hash: "a".repeat(64),
			state: "review",
			review_outcome: "approved",
			created_at: "2026-07-26T09:00:00Z",
			experiment_id: "exp-1",
		};

		expect(mapReviewQueueEntry(dto)).toEqual({
			strategyId: "seed_etf_rotation",
			version: 4,
			parentVersion: 3,
			specHash: "a".repeat(64),
			state: "review",
			reviewOutcome: "approved",
			createdAt: "2026-07-26T09:00:00Z",
			experimentId: "exp-1",
		});
	});

	it("coerces missing experiment_id to null (no packet yet)", () => {
		const dto: StrategyVersionResponse = {
			strategy_id: "seed_stock",
			version: 2,
			parent_version: 1,
			spec_hash: "b".repeat(64),
			state: "review",
			review_outcome: "pending",
			created_at: "2026-07-28T10:00:00Z",
			experiment_id: null,
		};

		expect(mapReviewQueueEntry(dto).experimentId).toBeNull();
	});
});

describe("mapReviewPacket", () => {
	it("translates full packet DTO with gates, hashes, lineage, and trace refs", () => {
		const dto: ExperimentReviewPacketResponse = {
			experiment_id: "exp-1",
			candidate_id: "candidate-baseline",
			bundle_hash: "d".repeat(64),
			hard_review_blocked: false,
			gate_outcomes: [
				{ rule_id: "certified_snapshot", layer: "HARD", outcome: "pass" },
				{ rule_id: "holdout_integrity", layer: "HARD", outcome: "fail" },
			],
			schema_version: 2,
			fold_ids: ["fold-1", "fold-2"],
			attempt_ids: ["attempt-1"],
			spec_hash: "a".repeat(64),
			resolved_spec_hash: "e".repeat(64),
			parameter_hash: "f".repeat(64),
			snapshot_hash: "1".repeat(64),
			registry_hash: "2".repeat(64),
			objective_payload_hash: "3".repeat(64),
			comparison_payload_hash: "4".repeat(64),
			r1_impact_payload_hash: null,
			selection_evidence_artifact_id: "artifact-1",
			holdout_claim_id: "holdout-1",
			candidate_rationale: "baseline net return stable",
			selection_trace_artifact_refs: [
				{
					artifact_kind: "fold_selection_trace",
					artifact_id: "trace-1",
					content_hash: "6".repeat(64),
				},
			],
		};

		const view = mapReviewPacket(dto);
		expect(view.bundleHash).toBe("d".repeat(64));
		expect(view.hardReviewBlocked).toBe(false);
		expect(view.gateOutcomes).toEqual([
			{ ruleId: "certified_snapshot", layer: "HARD", outcome: "pass" },
			{ ruleId: "holdout_integrity", layer: "HARD", outcome: "fail" },
		]);
		expect(view.r1ImpactPayloadHash).toBeNull();
		expect(view.comparisonPayloadHash).toBe("4".repeat(64));
		expect(view.selectionTraceArtifactRefs).toEqual([
			{ artifactKind: "fold_selection_trace", artifactId: "trace-1", contentHash: "6".repeat(64) },
		]);
	});
});
