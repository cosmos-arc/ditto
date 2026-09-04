/**
 * R3 live-shape strategy mocks（generated snake_case DTO 形态）。
 *
 * 与 {@link "./strategy"} 中的 prototype mock（旧 view-model 形状）并存：新
 * `/api/v1/strategies/*` handler 消费本文件，旧 `/api/strategies/*` handler 保留
 * 给未迁移组件。组件迁移完成后旧 prototype mock 一并清理。
 *
 * `spec_json` 用后端 legacy `StrategySpec` asdict 完整形态（template/scorer/selector/
 * execution/constraints/params/signal_expressions/signal_weights/param_constraints），
 * 与真实 seed（etf_industry_rotation）一致。
 */
import type { components } from "@/types/generated/api";

type StrategyResponse = components["schemas"]["StrategyResponse"];
type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
type StrategyVersionDetailResponse = components["schemas"]["StrategyVersionDetailResponse"];
type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
type StrategyVersionDiffResponse = components["schemas"]["StrategyVersionDiffResponse"];
type NodeDescriptorResponse = components["schemas"]["NodeDescriptorResponse"];
type StrategyActivePointerResponse = components["schemas"]["StrategyActivePointerResponse"];
type StrategyVersionStateResponse = components["schemas"]["StrategyVersionStateResponse"];

const seedSpecJson = {
	strategy_id: "seed_etf_industry_rotation",
	name: "ETF 行业轮动",
	template: "etf_rotation",
	universe: "csi_etf_broad",
	asset_class: "etf",
	benchmark: "000300.SH",
	scorer: { method: "rank_then_combine" },
	selector: { method: "top_k", params: { k: 5 } },
	execution: {
		frequency: "M",
		method: "calendar",
		default_order_type: "market",
		cost_model: { commission_rate: 0.0003, slippage_bps: 5.0, impact_model: "none" },
	},
	constraints: [
		{ type: "max_weight_per_instrument", params: { max_weight: 0.3 } },
		{ type: "max_turnover", params: { max_turnover: 0.5 } },
	],
	params: { lookback: 252, vol_window: 60 },
	signal_expressions: ["momentum_1m", "reversal_1w", "volatility_factor"],
	signal_weights: [0.5, 0.3, 0.2],
	param_constraints: [
		{ name: "lookback", dtype: "int", min_value: 21, max_value: 504, step: 1, allowed_values: [] },
		{ name: "top_k", dtype: "int", min_value: 1, max_value: 50, step: 1, allowed_values: [] },
	],
} satisfies Record<string, unknown>;

export const mockStrategyList: StrategyResponse[] = [
	{
		strategy_id: "seed_etf_industry_rotation",
		name: "ETF 行业轮动",
		spec_json: seedSpecJson,
		version: 3,
		status: "published",
		created_at: "2026-04-08T15:00:00Z",
		tags: ["etf", "rotation"],
	},
	{
		strategy_id: "seed_etf_trend_following",
		name: "ETF 趋势追踪",
		spec_json: {
			...seedSpecJson,
			strategy_id: "seed_etf_trend_following",
			name: "ETF 趋势追踪",
			template: "etf_trend",
		},
		version: 2,
		status: "approved",
		created_at: "2026-05-02T10:00:00Z",
		tags: ["etf", "trend"],
	},
	{
		strategy_id: "seed_stock_picking",
		name: "个股精选",
		spec_json: {
			...seedSpecJson,
			strategy_id: "seed_stock_picking",
			name: "个股精选",
			template: "stock_picking",
			asset_class: "stock",
		},
		version: 1,
		status: "draft",
		created_at: "2026-06-01T09:00:00Z",
		tags: ["stock", "multi-factor"],
	},
];

export const mockStrategyDetailDto: StrategyResponse = mockStrategyList[0];

export const mockStrategyVersionList: StrategyVersionResponse[] = [
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
		strategy_id: "seed_etf_industry_rotation",
		version: 1,
		parent_version: null,
		spec_hash: "h-v1",
		state: "deprecated",
		review_outcome: "approved",
		created_at: "2026-04-01T10:00:00Z",
	},
	{
		strategy_id: "seed_etf_industry_rotation",
		version: 2,
		parent_version: 1,
		spec_hash: "h-v2",
		state: "deprecated",
		review_outcome: "approved",
		created_at: "2026-04-05T14:30:00Z",
	},
	{
		strategy_id: "seed_etf_industry_rotation",
		version: 3,
		parent_version: 2,
		spec_hash: "h-v3",
		state: "published",
		review_outcome: "approved",
		created_at: "2026-04-08T15:00:00Z",
	},
];

export const mockStrategyVersionDetail: StrategyVersionDetailResponse = {
	strategy_id: "seed_etf_industry_rotation",
	version: 3,
	parent_version: 2,
	spec_hash: "h-v3",
	state: "published",
	review_outcome: "approved",
	created_at: "2026-04-08T15:00:00Z",
	canonical_spec: {
		schema_version: 2,
		strategy_family_id: "seed_etf_industry_rotation",
		strategy_kind: "etf_rotation",
	},
};

export const mockNodeDescriptorList: NodeDescriptorResponse[] = [
	{
		node_type: "legacy.universe",
		version: "1",
		category: "UNIVERSE",
		display_name: "Universe",
		implementation_key: "legacy.universe.v1",
		config_schema: { asset_class: "string", benchmark: "string_or_null", universe: "string" },
		default_config: { asset_class: "", benchmark: null, universe: "" },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "legacy.factor_set",
		version: "1",
		category: "FACTOR_SET",
		display_name: "Factor Set",
		implementation_key: "legacy.factor_set.v1",
		config_schema: {
			params: "object",
			required_datasets: "string_array",
			signal_expressions: "string_array",
			signal_weights: "number_array",
			template: "string",
		},
		default_config: { params: {}, required_datasets: [], signal_expressions: [], signal_weights: [], template: "" },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "builtin.trend_filter",
		version: "1",
		category: "FILTER",
		display_name: "Trend Filter",
		implementation_key: "builtin.trend_filter.v1",
		config_schema: { direction: "string", signal_column: "string", threshold: "number" },
		default_config: { direction: "long", signal_column: "signal_value", threshold: 0 },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "legacy.scorer",
		version: "1",
		category: "SCORER",
		display_name: "Scorer",
		implementation_key: "legacy.scorer.v1",
		config_schema: { method: "string", params: "object" },
		default_config: { method: "rank", params: {} },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "legacy.selector",
		version: "1",
		category: "SELECTOR",
		display_name: "Selector",
		implementation_key: "legacy.selector.v1",
		config_schema: { method: "string", params: "object" },
		default_config: { method: "top_k", params: {} },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "legacy.allocator",
		version: "1",
		category: "ALLOCATOR",
		display_name: "Allocator",
		implementation_key: "legacy.allocator.v1",
		config_schema: { constraints: "object_array" },
		default_config: { constraints: [] },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "legacy.execution_assumption",
		version: "1",
		category: "EXECUTION_ASSUMPTION",
		display_name: "Execution Assumption",
		implementation_key: "legacy.execution_assumption.v1",
		config_schema: { cost_model: "object", default_order_type: "string", frequency: "string", method: "string" },
		default_config: { cost_model: {}, default_order_type: "market", frequency: "D", method: "calendar" },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
	{
		node_type: "legacy.validation",
		version: "1",
		category: "VALIDATION",
		display_name: "Validation",
		implementation_key: "legacy.validation.v1",
		config_schema: { legacy_contract: "string" },
		default_config: { legacy_contract: "strategy_spec_v1" },
		required_datasets: [],
		capability_tags: ["r3.constrained"],
		deterministic: true,
	},
];

export const mockSpecValidationDto: StrategySpecValidationResponse = {
	strategy_id: "seed_etf_industry_rotation",
	version: 3,
	canonical_hash: "h-candidate",
	base_spec_hash: "h-v3",
	changed: true,
	valid: true,
	errors: [],
};

export const mockSpecDiffDto: StrategyVersionDiffResponse = {
	strategy_id: "seed_etf_industry_rotation",
	version: 3,
	parent_version: 2,
	base_spec_hash: "h-v2",
	target_spec_hash: "h-v3",
	changed: true,
	changes: [
		{ path: "selector.params.k", op: "replace", old: 3, new: 5 },
		{ path: "params.vol_window", op: "replace", old: 40, new: 60 },
	],
};

export const mockActivePointerDto: StrategyActivePointerResponse = {
	strategy_id: "seed_etf_industry_rotation",
	active_version: 3,
	pointer_revision: 1,
};

export const mockVersionStateDto: StrategyVersionStateResponse = {
	strategy_id: "seed_etf_industry_rotation",
	version: 3,
	state: "review",
	review_outcome: "pending",
};
