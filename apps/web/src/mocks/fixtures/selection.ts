import type {
	CreateSelectionRunBody,
	IndustryRotation,
	SelectionRun,
	SelectionRunDiff,
	SelectionWorkspaceReceipt,
} from "@/features/selection/api";

export const selectionRunInputFixture = {
	as_of: "2026-08-31T07:00:00Z",
	industries: [],
	instruments: [],
	knowledge_cutoff: "2026-08-31T07:00:00Z",
	market_context_feature_set_id: null,
	membership_version: "sw-l1:2026-08-31",
	publication_cutoff: "2026-08-31T06:30:00Z",
	rotation_algorithm_version: "industry-rotation-v1",
	rotation_missing_inputs: ["industry_inputs"],
	rotation_source_snapshot_ids: ["stock-daily:sha256:a"],
	seed: 17,
	selection_source_snapshot_ids: ["stock-daily:sha256:a"],
	selection_spec: {
		asset_kind: "stock",
		excluded_limit_states: ["limit_up", "limit_down"],
		factor_weights: [{ name: "momentum", weight: 1 }],
		min_average_turnover: 20_000_000,
		min_listing_days: 120,
		spec_id: "a-share-stock-discovery",
		spec_version: "1",
		top_k: 10,
	},
	universe_snapshot_id: "universe:sha256:stock-core",
} satisfies CreateSelectionRunBody;

export const selectionRotationFixture = {
	algorithm_version: "industry-rotation-v1",
	as_of: "2026-08-31T07:00:00Z",
	input_hash: "a".repeat(64),
	knowledge_cutoff: "2026-08-31T07:00:00Z",
	market_context_feature_set_id: "market-regime:sha256:ctx",
	membership_version: "sw-l1:2026-08-31",
	missing_inputs: [],
	publication_cutoff: "2026-08-31T06:30:00Z",
	rankings: [
		{
			contributions: [
				{ contribution: 0.24, metric: "relative_strength_20d", value: 0.8, weight: 0.3 },
				{ contribution: 0.12, metric: "breadth", value: 0.6, weight: 0.2 },
			],
			industry_id: "801080",
			industry_name: "电子",
			missing_inputs: [],
			rank: 1,
			score: 0.72,
		},
		{
			contributions: [
				{ contribution: 0.18, metric: "relative_strength_20d", value: 0.6, weight: 0.3 },
				{ contribution: 0.08, metric: "breadth", value: 0.4, weight: 0.2 },
			],
			industry_id: "801760",
			industry_name: "传媒",
			missing_inputs: ["fundamental_score"],
			rank: 2,
			score: 0.51,
		},
	],
	snapshot_id: "industry-rotation:sha256:rotation-one",
	source_snapshot_ids: ["stock-daily:sha256:a", "index-membership:sha256:b"],
	status: "ready",
} satisfies IndustryRotation;

export const selectionRunFixtures = [
	{
		as_of: "2026-08-31T07:00:00Z",
		asset_kind: "stock",
		candidates: [
			{
				factor_contributions: [
					{ contribution: 0.54, factor_name: "momentum", value: 0.9, weight: 0.6 },
					{ contribution: 0.24, factor_name: "quality", value: 0.6, weight: 0.4 },
				],
				industry_id: "801080",
				instrument_id: 600519,
				instrument_name: "贵州茅台",
				rank: 1,
				score: 0.78,
			},
			{
				factor_contributions: [
					{ contribution: 0.42, factor_name: "momentum", value: 0.7, weight: 0.6 },
					{ contribution: 0.2, factor_name: "quality", value: 0.5, weight: 0.4 },
				],
				industry_id: "801080",
				instrument_id: 300750,
				instrument_name: "宁德时代",
				rank: 2,
				score: 0.62,
			},
		],
		exclusions: [
			{
				detail: "average_turnover below 20000000",
				instrument_id: 600001,
				instrument_name: "邯郸钢铁",
				reason_code: "insufficient_liquidity",
				stage: "hard_filter",
			},
		],
		industry_rotation_snapshot_id: selectionRotationFixture.snapshot_id,
		input_hash: "b".repeat(64),
		knowledge_cutoff: "2026-08-31T07:00:00Z",
		missing_inputs: [],
		publication_cutoff: "2026-08-31T06:30:00Z",
		run_id: "selection-run:sha256:run-one",
		seed: 17,
		source_snapshot_ids: ["stock-daily:sha256:a"],
		spec_hash: "c".repeat(64),
		spec_id: "a-share-stock-discovery",
		spec_version: "1",
		status: "ready",
		universe_snapshot_id: "universe:sha256:stock-core",
	},
	{
		as_of: "2026-08-30T07:00:00Z",
		asset_kind: "stock",
		candidates: [
			{
				factor_contributions: [{ contribution: 0.48, factor_name: "momentum", value: 0.8, weight: 0.6 }],
				industry_id: "801080",
				instrument_id: 300750,
				instrument_name: "宁德时代",
				rank: 1,
				score: 0.68,
			},
		],
		exclusions: [],
		industry_rotation_snapshot_id: "industry-rotation:sha256:rotation-previous",
		input_hash: "d".repeat(64),
		knowledge_cutoff: "2026-08-30T07:00:00Z",
		missing_inputs: [],
		publication_cutoff: "2026-08-30T06:30:00Z",
		run_id: "selection-run:sha256:run-previous",
		seed: 17,
		source_snapshot_ids: ["stock-daily:sha256:previous"],
		spec_hash: "c".repeat(64),
		spec_id: "a-share-stock-discovery",
		spec_version: "1",
		status: "ready",
		universe_snapshot_id: "universe:sha256:stock-core",
	},
] as const satisfies readonly SelectionRun[];

export const selectionDiffFixture = {
	added_candidate_ids: [600519],
	after_run_id: selectionRunFixtures[0].run_id,
	before_run_id: selectionRunFixtures[1].run_id,
	data_changed: true,
	exclusion_changes: [{ after_reason: null, before_reason: "below_top_k", instrument_id: 600519 }],
	industry_rotation_changed: true,
	rank_changes: [{ after_rank: 2, before_rank: 1, instrument_id: 300750 }],
	removed_candidate_ids: [],
	seed_changed: false,
	spec_changed: false,
} satisfies SelectionRunDiff;

export const selectionReceiptFixture = {
	industry_rotation: selectionRotationFixture,
	selection_run: selectionRunFixtures[0],
} satisfies SelectionWorkspaceReceipt;
