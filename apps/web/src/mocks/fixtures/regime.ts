import type { RegimeDiagnosticsDto as RegimeDiagnosticsResponse } from "@/features/research/api/regime-diagnostics";

const observations: RegimeDiagnosticsResponse["observations"] = [
	["2026-03-16", 28, "bear", 0.3],
	["2026-03-17", 32, "bear", 0.3],
	["2026-03-18", 38, "neutral", 0.7],
	["2026-03-19", 44, "neutral", 0.7],
	["2026-03-20", 51, "neutral", 0.7],
	["2026-03-23", 59, "neutral", 0.7],
	["2026-03-24", 66, "bull", 1],
	["2026-03-25", 72, "bull", 1],
].map(([observedAt, score, label, positionRatio]) => ({
	observed_at: String(observedAt),
	score: Number(score),
	label: label as "bull" | "bear" | "neutral",
	position_ratio: Number(positionRatio),
	indicators: [{ name: "momentum", normalized_score: Number(score) / 100 }],
}));

export const mockRegimeDiagnostics: RegimeDiagnosticsResponse = {
	snapshot_id: "snapshot-regime-demo-v1",
	snapshot_manifest_hash: "a".repeat(64),
	dataset_id: "research-index-daily",
	source_snapshot_ids: ["tdx-eod-20260325-v1"],
	builder_version: "research-snapshot-builder-v1",
	known_at_policy: "sample_time",
	benchmark_instrument_id: 300001,
	start_date: "2026-03-16",
	end_date: "2026-03-25",
	knowledge_cutoff: "2026-03-26",
	model_id: "momentum-20d-v1",
	lookback_observations: 20,
	bear_threshold: 35,
	bull_threshold: 65,
	bars_input_id: "bars-csi300-20260325-v1",
	bars_content_hash: "b".repeat(64),
	bars_schema_hash: "c".repeat(64),
	current: observations.at(-1) ?? {
		observed_at: "2026-03-25",
		score: 72,
		label: "bull",
		position_ratio: 1,
		indicators: [{ name: "momentum", normalized_score: 0.72 }],
	},
	observations,
	transitions: [
		{ observed_at: "2026-03-18", from_label: "bear", to_label: "neutral" },
		{ observed_at: "2026-03-24", from_label: "neutral", to_label: "bull" },
	],
};
