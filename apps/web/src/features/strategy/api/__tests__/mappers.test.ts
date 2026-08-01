import { describe, expect, it } from "vitest";
import type { components } from "@/types/generated/api";
import {
	mapNodeDescriptor,
	mapSpecDiff,
	mapSpecValidation,
	mapStrategyDetail,
	mapStrategyListItem,
	mapStrategyVersion,
} from "../mappers";

type StrategyResponse = components["schemas"]["StrategyResponse"];
type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
type StrategyVersionDiffResponse = components["schemas"]["StrategyVersionDiffResponse"];
type NodeDescriptorResponse = components["schemas"]["NodeDescriptorResponse"];

const SPEC_JSON = {
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

const baseStrategy: StrategyResponse = {
	strategy_id: "seed_etf_industry_rotation",
	name: "ETF 行业轮动",
	spec_json: SPEC_JSON,
	version: 3,
	status: "published",
	created_at: "2026-04-08T15:00:00Z",
	tags: ["etf", "rotation"],
};

describe("strategy mappers", () => {
	describe("mapStrategyListItem", () => {
		it("maps snake_case DTO to camelCase view-model", () => {
			const vm = mapStrategyListItem(baseStrategy);
			expect(vm).toMatchObject({
				strategyId: "seed_etf_industry_rotation",
				name: "ETF 行业轮动",
				version: 3,
				status: "published",
				createdAt: "2026-04-08T15:00:00Z",
			});
			expect(vm.tags).toEqual(["etf", "rotation"]);
		});

		it("derives lifecycleState for known governance status", () => {
			expect(mapStrategyListItem({ ...baseStrategy, status: "draft" }).lifecycleState).toBe("draft");
			expect(mapStrategyListItem({ ...baseStrategy, status: "review" }).lifecycleState).toBe("review");
			expect(mapStrategyListItem(baseStrategy).lifecycleState).toBe("published");
		});

		it("collapses unrecognized status to unknown lifecycleState", () => {
			expect(mapStrategyListItem({ ...baseStrategy, status: "weird" }).lifecycleState).toBe("unknown");
		});
	});

	describe("mapStrategyDetail / spec_json parsing", () => {
		it("parses legacy spec_json into structured StrategySpec", () => {
			const spec = mapStrategyDetail(baseStrategy).spec;
			expect(spec).toMatchObject({
				strategyId: "seed_etf_industry_rotation",
				template: "etf_rotation",
				universe: "csi_etf_broad",
				assetClass: "etf",
				benchmark: "000300.SH",
			});
			expect(spec.scorer.method).toBe("rank_then_combine");
			expect(spec.selector.params).toEqual({ k: 5 });
			expect(spec.execution.costModel?.commissionRate).toBe(0.0003);
			expect(spec.execution.costModel?.slippageBps).toBe(5.0);
			expect(spec.constraints).toHaveLength(2);
			expect(spec.params).toEqual({ lookback: 252, vol_window: 60 });
		});

		it("preserves top-level identity (strategyId/name) when spec_json lacks them", () => {
			const dto = { ...baseStrategy, spec_json: { template: "etf_rotation" } satisfies Record<string, unknown> };
			const detail = mapStrategyDetail(dto);
			expect(detail.strategyId).toBe("seed_etf_industry_rotation");
			expect(detail.name).toBe("ETF 行业轮动");
			expect(detail.spec.template).toBe("etf_rotation");
		});

		it("falls back to neutral defaults for empty spec_json", () => {
			const spec = mapStrategyDetail({ ...baseStrategy, spec_json: {} }).spec;
			expect(spec.template).toBe("");
			expect(spec.universe).toBe("");
			expect(spec.assetClass).toBe("");
			expect(spec.benchmark).toBe("");
			expect(spec.scorer.method).toBe("");
			expect(spec.constraints).toEqual([]);
			expect(spec.params).toEqual({});
		});

		it("handles partial execution without cost_model", () => {
			const spec = mapStrategyDetail({
				...baseStrategy,
				spec_json: { execution: { frequency: "M", method: "calendar" } } satisfies Record<string, unknown>,
			}).spec;
			expect(spec.execution.frequency).toBe("M");
			expect(spec.execution.costModel).toBeUndefined();
		});

		it("parses signal_expressions / signal_weights / param_constraints from spec_json", () => {
			const spec = mapStrategyDetail({
				...baseStrategy,
				spec_json: {
					...SPEC_JSON,
					signal_expressions: ["momentum_1m", "reversal_1w"],
					signal_weights: [0.6, 0.4],
					param_constraints: [
						{ name: "lookback", dtype: "int", min_value: 21, max_value: 504, step: 1, allowed_values: [] },
						{ name: "mode", dtype: "str", allowed_values: ["fast", "slow"] },
					],
				} satisfies Record<string, unknown>,
			}).spec;
			expect(spec.signalExpressions).toEqual(["momentum_1m", "reversal_1w"]);
			expect(spec.signalWeights).toEqual([0.6, 0.4]);
			expect(spec.paramConstraints).toEqual([
				{ name: "lookback", dtype: "int", minValue: 21, maxValue: 504, step: 1, allowedValues: [] },
				{ name: "mode", dtype: "str", allowedValues: ["fast", "slow"] },
			]);
		});

		it("defaults signal/param fields to empty arrays when spec_json omits them", () => {
			const spec = mapStrategyDetail({ ...baseStrategy, spec_json: {} }).spec;
			expect(spec.signalExpressions).toEqual([]);
			expect(spec.signalWeights).toEqual([]);
			expect(spec.paramConstraints).toEqual([]);
		});

		it("gracefully handles malformed signal/param entries (non-array / non-record)", () => {
			const spec = mapStrategyDetail({
				...baseStrategy,
				spec_json: {
					signal_expressions: "not-an-array",
					signal_weights: { a: 1 },
					param_constraints: [null, "x", { dtype: "int" }, { name: "ok", dtype: "float", min_value: "bad" }],
				} satisfies Record<string, unknown>,
			}).spec;
			expect(spec.signalExpressions).toEqual([]);
			expect(spec.signalWeights).toEqual([]);
			expect(spec.paramConstraints).toEqual([
				{ name: "", dtype: "int", allowedValues: [] },
				{ name: "ok", dtype: "float", allowedValues: [] },
			]);
		});
	});

	describe("mapStrategyVersion", () => {
		const baseVersion: StrategyVersionResponse = {
			strategy_id: "seed_etf_industry_rotation",
			version: 3,
			parent_version: 2,
			spec_hash: "abc123",
			state: "approved",
			review_outcome: "approved",
			created_at: "2026-04-08T15:00:00Z",
			experiment_id: "exp-v3",
		};

		it("maps snake_case version DTO to camelCase", () => {
			expect(mapStrategyVersion(baseVersion)).toMatchObject({
				strategyId: "seed_etf_industry_rotation",
				version: 3,
				parentVersion: 2,
				specHash: "abc123",
				experimentId: "exp-v3",
			});
		});

		it("preserves null parent_version for first version", () => {
			const vm = mapStrategyVersion({ ...baseVersion, parent_version: null });
			expect(vm.parentVersion).toBeNull();
		});

		it("derives lifecycleState and reviewOutcome", () => {
			const vm = mapStrategyVersion({ ...baseVersion, state: "deprecated", review_outcome: "rejected" });
			expect(vm.lifecycleState).toBe("deprecated");
			expect(vm.reviewOutcome).toBe("rejected");
		});

		it("collapses unrecognized state/outcome to unknown", () => {
			const vm = mapStrategyVersion({ ...baseVersion, state: "?", review_outcome: "?" });
			expect(vm.lifecycleState).toBe("unknown");
			expect(vm.reviewOutcome).toBe("unknown");
		});
	});

	describe("mapSpecValidation", () => {
		it("maps validation DTO and defaults errors to empty array", () => {
			const dto: StrategySpecValidationResponse = {
				strategy_id: "seed_etf_industry_rotation",
				version: 3,
				canonical_hash: "h1",
				base_spec_hash: "h0",
				changed: true,
				valid: true,
				errors: [],
			};
			expect(mapSpecValidation(dto)).toMatchObject({
				strategyId: "seed_etf_industry_rotation",
				version: 3,
				canonicalHash: "h1",
				baseSpecHash: "h0",
				changed: true,
				valid: true,
			});
			expect(mapSpecValidation(dto).errors).toEqual([]);
		});

		it("preserves explicit errors", () => {
			const dto: StrategySpecValidationResponse = {
				strategy_id: "s",
				version: 1,
				canonical_hash: "h",
				base_spec_hash: "h",
				changed: false,
				valid: false,
				errors: ["bad pipeline", "missing universe"],
			};
			expect(mapSpecValidation(dto).errors).toEqual(["bad pipeline", "missing universe"]);
		});
	});

	describe("mapSpecDiff", () => {
		it("maps diff DTO with changes and null parent", () => {
			const dto: StrategyVersionDiffResponse = {
				strategy_id: "s",
				version: 1,
				parent_version: null,
				base_spec_hash: "h0",
				target_spec_hash: "h1",
				changed: true,
				changes: [
					{ path: "universe", op: "replace", old: "csi300", new: "hs300" },
					{ path: "params.k", op: "add", new: 5 },
				],
			};
			const vm = mapSpecDiff(dto);
			expect(vm.parentVersion).toBeNull();
			expect(vm.baseSpecHash).toBe("h0");
			expect(vm.targetSpecHash).toBe("h1");
			expect(vm.changes).toHaveLength(2);
			expect(vm.changes[0]).toMatchObject({ path: "universe", op: "replace", old: "csi300", new: "hs300" });
			expect(vm.changes[1].new).toBe(5);
		});

		it("maps empty changes to empty array", () => {
			const dto: StrategyVersionDiffResponse = {
				strategy_id: "s",
				version: 1,
				parent_version: null,
				base_spec_hash: "h",
				target_spec_hash: "h",
				changed: false,
				changes: [],
			};
			expect(mapSpecDiff(dto).changes).toEqual([]);
		});
	});

	describe("mapNodeDescriptor", () => {
		it("maps node descriptor DTO to camelCase view-model", () => {
			const dto: NodeDescriptorResponse = {
				node_type: "scorer",
				version: "1.0",
				category: "SCORER",
				display_name: "评分节点",
				implementation_key: "rank_then_combine",
				config_schema: { method: "string", normalize: "boolean" },
				default_config: { method: "rank_then_combine", normalize: true },
				required_datasets: ["factor_scores"],
				capability_tags: ["scoring", "combiner"],
				deterministic: true,
			};
			const vm = mapNodeDescriptor(dto);
			expect(vm).toMatchObject({
				nodeType: "scorer",
				version: "1.0",
				category: "SCORER",
				displayName: "评分节点",
				implementationKey: "rank_then_combine",
				deterministic: true,
			});
			expect(vm.configSchema).toEqual({ method: "string", normalize: "boolean" });
			expect(vm.requiredDatasets).toEqual(["factor_scores"]);
			expect(vm.capabilityTags).toEqual(["scoring", "combiner"]);
		});
	});
});
