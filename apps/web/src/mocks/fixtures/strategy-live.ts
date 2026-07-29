/**
 * R3 live-shape strategy mocks（generated snake_case DTO 形态）。
 *
 * 与 {@link "./strategy"} 中的 prototype mock（旧 view-model 形状）并存：新
 * `/api/v1/strategies/*` handler 消费本文件，旧 `/api/strategies/*` handler 保留
 * 给未迁移组件。组件迁移完成后旧 prototype mock 一并清理。
 *
 * `spec_json` 用后端 legacy `StrategySpec` asdict 形态（template/scorer/selector/
 * execution/constraints/params），与真实 seed 一致。
 */
import type { components } from "@/types/generated/api";

type StrategyResponse = components["schemas"]["StrategyResponse"];
type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
type StrategyVersionDiffResponse = components["schemas"]["StrategyVersionDiffResponse"];
type NodeDescriptorResponse = components["schemas"]["NodeDescriptorResponse"];

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
		cost_model: { commission_rate: 0.0003, slippage_bps: 5.0 },
	},
	constraints: [
		{ type: "max_weight_per_instrument", params: { max_weight: 0.3 } },
		{ type: "max_turnover", params: { max_turnover: 0.5 } },
	],
	params: { lookback: 252, vol_window: 60 },
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

export const mockNodeDescriptorList: NodeDescriptorResponse[] = [
	{
		node_type: "universe_filter",
		version: "1.0",
		category: "UNIVERSE",
		display_name: "股票池过滤",
		implementation_key: "static_universe",
		config_schema: { universe: "string", exclude_st: "boolean" },
		default_config: { universe: "csi300", exclude_st: true },
		required_datasets: ["universe_constituents"],
		capability_tags: ["filtering"],
		deterministic: true,
	},
	{
		node_type: "factor_combine",
		version: "1.0",
		category: "SCORER",
		display_name: "因子合成",
		implementation_key: "rank_then_combine",
		config_schema: { method: "string", normalize: "boolean" },
		default_config: { method: "rank_then_combine", normalize: true },
		required_datasets: ["factor_scores"],
		capability_tags: ["scoring", "combiner"],
		deterministic: true,
	},
	{
		node_type: "top_k_selector",
		version: "1.0",
		category: "SELECTOR",
		display_name: "Top-K 选取",
		implementation_key: "top_k",
		config_schema: { k: "integer" },
		default_config: { k: 5 },
		required_datasets: ["factor_scores"],
		capability_tags: ["selection"],
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
