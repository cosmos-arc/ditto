/**
 * R3 live-shape review mocks（generated snake_case DTO 形态 + `{data}` 信封）。
 *
 * `mockReviewQueue` 覆盖 REVIEW 态（pending 待审查 + approved 待发布），
 * 每项携带 `experiment_id`（null 表示尚无 packet）。`mockReviewPacket` 是完整
 * ReviewPacket read model（11 hard-gate + 6 hash + lineage + rationale）。
 */
import type { components } from "@/types/generated/api";

type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
type ExperimentReviewPacketResponse = components["schemas"]["ExperimentReviewPacketResponse"];

export const mockReviewQueue: StrategyVersionResponse[] = [
	{
		strategy_id: "seed_etf_industry_rotation",
		version: 4,
		parent_version: 3,
		spec_hash: "a".repeat(64),
		state: "review",
		review_outcome: "approved",
		created_at: "2026-07-26T09:00:00Z",
		experiment_id: "exp-rotation-v4",
	},
	{
		strategy_id: "seed_etf_trend_following",
		version: 3,
		parent_version: 2,
		spec_hash: "b".repeat(64),
		state: "review",
		review_outcome: "pending",
		created_at: "2026-07-27T14:30:00Z",
		experiment_id: "exp-trend-v3",
	},
	{
		strategy_id: "seed_stock_picking",
		version: 2,
		parent_version: 1,
		spec_hash: "c".repeat(64),
		state: "review",
		review_outcome: "pending",
		created_at: "2026-07-28T10:15:00Z",
		experiment_id: null,
	},
];

const GATE_RULES: ReadonlyArray<{ rule_id: string; layer: string; outcome: string }> = [
	{ rule_id: "certified_snapshot", layer: "HARD", outcome: "pass" },
	{ rule_id: "holdout_integrity", layer: "HARD", outcome: "pass" },
	{ rule_id: "pit_discipline", layer: "HARD", outcome: "pass" },
	{ rule_id: "reproduction_fingerprint", layer: "HARD", outcome: "pass" },
	{ rule_id: "canonical_spec_hash", layer: "HARD", outcome: "pass" },
	{ rule_id: "parameter_schema_valid", layer: "HARD", outcome: "pass" },
	{ rule_id: "registry_pinned", layer: "HARD", outcome: "pass" },
	{ rule_id: "no_lookahead_bias", layer: "HARD", outcome: "pass" },
	{ rule_id: "fold_protocol_match", layer: "HARD", outcome: "pass" },
	{ rule_id: "objective_payload_signed", layer: "HARD", outcome: "pass" },
	{ rule_id: "min_fold_coverage", layer: "HARD", outcome: "pass" },
];

export const mockReviewPacket: ExperimentReviewPacketResponse = {
	experiment_id: "exp-rotation-v4",
	candidate_id: "candidate-baseline",
	bundle_hash: "d".repeat(64),
	hard_review_blocked: false,
	gate_outcomes: GATE_RULES.map((g) => ({ ...g })),
	schema_version: 2,
	fold_ids: ["fold-2024-h2", "fold-2025-h1"],
	attempt_ids: ["attempt-1", "attempt-2"],
	spec_hash: "a".repeat(64),
	resolved_spec_hash: "e".repeat(64),
	parameter_hash: "f".repeat(64),
	snapshot_hash: "1".repeat(64),
	registry_hash: "2".repeat(64),
	objective_payload_hash: "3".repeat(64),
	comparison_payload_hash: "4".repeat(64),
	r1_impact_payload_hash: "5".repeat(64),
	selection_evidence_artifact_id: "artifact-selection-1",
	selection_exposure: null,
	holdout_claim_id: "holdout-claim-1",
	candidate_rationale: "基线候选在 walk-forward 窗口净收益稳定、回撤可控，成本调整后仍优于阈值。",
	selection_trace_artifact_refs: [
		{
			artifact_kind: "fold_selection_trace",
			artifact_id: "artifact-trace-1",
			content_hash: "6".repeat(64),
		},
	],
};
