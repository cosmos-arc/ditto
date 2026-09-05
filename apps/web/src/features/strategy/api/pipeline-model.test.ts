import { describe, expect, it } from "vitest";
import { mockNodeDescriptorList } from "@/mocks/fixtures/strategy-live";
import type { StrategySpec } from "@/types/strategy";
import { mapNodeDescriptor } from "./mappers";
import {
	addDescriptorNode,
	buildStrategyPipeline,
	descriptorIdentity,
	findNodeDescriptor,
	movePipelineNode,
	removePipelineNode,
	type StrategyPipelineNode,
	updatePipelineNodeConfig,
} from "./pipeline-model";

const DESCRIPTORS = mockNodeDescriptorList.map(mapNodeDescriptor);

function spec(constraints: StrategySpec["constraints"] = []): StrategySpec {
	return {
		strategyId: "strategy-1",
		name: "Evidence strategy",
		template: "etf_rotation",
		universe: "csi_etf_broad",
		assetClass: "etf",
		benchmark: "",
		scorer: { method: "rank", params: { ascending: false } },
		selector: { method: "top_k", params: { k: 5 } },
		execution: {
			frequency: "M",
			method: "calendar",
			defaultOrderType: "market",
			costModel: { commissionRate: 0.0003, impactModel: "linear", slippageBps: 5, stampDuty: 0.001 },
		},
		constraints,
		params: { lookback: 252 },
		signalExpressions: ["momentum_1m"],
		signalWeights: [1],
		paramConstraints: [],
	};
}

function node(nodes: readonly StrategyPipelineNode[], key: string): StrategyPipelineNode {
	const found = nodes.find((candidate) => candidate.key === key);
	if (!found) throw new Error(`expected pipeline node ${key}`);
	return found;
}

describe("strategy pipeline model", () => {
	it("builds every fixed grammar slot and distinguishes registered, legacy, and unknown constraints", () => {
		const input = spec([
			{ type: "max_turnover", params: { max_turnover: 0.5 } },
			{ type: "builtin.trend_filter@1", params: { threshold: 0.2 } },
			{ type: "plugin.unknown@9", params: { threshold: 0.7 } },
		]);
		const nodes = buildStrategyPipeline(input, DESCRIPTORS);

		expect(nodes.map((item) => item.key)).toEqual([
			"fixed:legacy.universe",
			"fixed:legacy.factor_set",
			"filter:1",
			"filter:2",
			"fixed:legacy.scorer",
			"fixed:legacy.selector",
			"fixed:legacy.allocator",
			"fixed:legacy.execution_assumption",
			"fixed:legacy.validation",
		]);
		expect(node(nodes, "fixed:legacy.universe").config).toEqual({
			asset_class: "etf",
			benchmark: null,
			universe: "csi_etf_broad",
		});
		expect(node(nodes, "fixed:legacy.factor_set").config).toMatchObject({
			params: { lookback: 252 },
			signal_expressions: ["momentum_1m"],
			signal_weights: [1],
		});
		expect(node(nodes, "fixed:legacy.allocator").config).toEqual({
			constraints: [{ type: "max_turnover", params: { max_turnover: 0.5 } }],
		});
		expect(node(nodes, "fixed:legacy.execution_assumption").config).toMatchObject({
			cost_model: { commission_rate: 0.0003, impact_model: "linear", slippage_bps: 5, stamp_duty: 0.001 },
		});
		expect(node(nodes, "fixed:legacy.validation").config).toEqual({ legacy_contract: "strategy_spec_v1" });
		expect(node(nodes, "filter:1")).toMatchObject({ category: "FILTER", readOnly: false });
		expect(node(nodes, "filter:2")).toMatchObject({ category: "UNKNOWN", readOnly: true });

		const customCategory = DESCRIPTORS.map((descriptor) =>
			descriptor.nodeType === "legacy.universe" ? { ...descriptor, category: "CUSTOM" } : descriptor,
		);
		expect(node(buildStrategyPipeline(input, customCategory), "fixed:legacy.universe")).toMatchObject({
			allowedPredecessor: null,
			allowedSuccessor: null,
		});
		expect(findNodeDescriptor(DESCRIPTORS, "builtin.trend_filter@1")?.nodeType).toBe("builtin.trend_filter");
		expect(findNodeDescriptor(DESCRIPTORS, "missing")).toBeNull();
	});

	it("adds, removes, and reorders only mutable registered filter nodes", () => {
		const filter = findNodeDescriptor(DESCRIPTORS, "builtin.trend_filter");
		const scorer = findNodeDescriptor(DESCRIPTORS, "legacy.scorer");
		if (!filter || !scorer) throw new Error("expected filter and scorer descriptors");
		const base = spec([{ type: "max_turnover", params: {} }]);
		expect(addDescriptorNode(base, scorer)).toBe(base);
		const added = addDescriptorNode(base, filter);
		expect(added.constraints.at(-1)).toEqual({
			type: descriptorIdentity(filter),
			params: { ...filter.defaultConfig },
		});

		const twoFilters = addDescriptorNode(added, filter);
		const nodes = buildStrategyPipeline(twoFilters, DESCRIPTORS);
		const first = node(nodes, "filter:1");
		const second = node(nodes, "filter:2");
		expect(movePipelineNode(twoFilters, first, 1, DESCRIPTORS).constraints[1]).toEqual(twoFilters.constraints[2]);
		expect(movePipelineNode(twoFilters, first, -1, DESCRIPTORS)).toBe(twoFilters);
		expect(removePipelineNode(twoFilters, first).constraints).toHaveLength(2);
		expect(removePipelineNode(twoFilters, { ...first, fixed: true })).toBe(twoFilters);
		expect(removePipelineNode(twoFilters, { ...first, readOnly: true })).toBe(twoFilters);
		expect(removePipelineNode(twoFilters, { ...first, constraintIndex: null })).toBe(twoFilters);
		expect(movePipelineNode(twoFilters, { ...second, constraintIndex: 99 }, 1, DESCRIPTORS)).toBe(twoFilters);
	});

	it("updates descriptor-backed fixed fields without mutating unrelated strategy state", () => {
		const base = spec([{ type: "builtin.trend_filter@1", params: { threshold: 0.2 } }]);
		const nodes = buildStrategyPipeline(base, DESCRIPTORS);
		const update = (key: string, field: string, value: unknown) =>
			updatePipelineNodeConfig(base, node(nodes, key), field, value);

		expect(update("fixed:legacy.universe", "universe", "csi500").universe).toBe("csi500");
		expect(update("fixed:legacy.universe", "asset_class", "stock").assetClass).toBe("stock");
		expect(update("fixed:legacy.universe", "benchmark", null).benchmark).toBe("");
		expect(update("fixed:legacy.universe", "unknown", 1)).toBe(base);
		expect(update("fixed:legacy.factor_set", "template", "factor_rotation").template).toBe("factor_rotation");
		expect(update("fixed:legacy.factor_set", "params", { window: 20 }).params).toEqual({ window: 20 });
		expect(update("fixed:legacy.factor_set", "params", null)).toBe(base);
		expect(update("fixed:legacy.factor_set", "signal_expressions", ["alpha", 4]).signalExpressions).toEqual(["alpha"]);
		expect(update("fixed:legacy.factor_set", "signal_weights", [0.8, "bad"]).signalWeights).toEqual([0.8]);
		expect(update("fixed:legacy.factor_set", "unknown", 1)).toBe(base);
		expect(update("fixed:legacy.scorer", "method", "zscore").scorer.method).toBe("zscore");
		expect(update("fixed:legacy.scorer", "params", { winsorize: true }).scorer.params).toEqual({
			winsorize: true,
		});
		expect(update("fixed:legacy.scorer", "params", null)).toBe(base);
		expect(update("fixed:legacy.selector", "method", "threshold").selector.method).toBe("threshold");
		expect(update("fixed:legacy.selector", "params", { cutoff: 0.7 }).selector.params).toEqual({ cutoff: 0.7 });
		expect(update("fixed:legacy.selector", "params", null)).toBe(base);
		expect(update("fixed:legacy.execution_assumption", "frequency", "W").execution.frequency).toBe("W");
		expect(update("fixed:legacy.execution_assumption", "method", "signal").execution.method).toBe("signal");
		expect(update("fixed:legacy.execution_assumption", "default_order_type", "limit").execution.defaultOrderType).toBe(
			"limit",
		);
		expect(update("fixed:legacy.execution_assumption", "unknown", 1)).toBe(base);
		expect(update("fixed:legacy.allocator", "constraints", [])).toBe(base);
	});

	it("updates mutable filter config while preserving sibling constraints and rejects read-only nodes", () => {
		const base = spec([
			{ type: "builtin.trend_filter@1", params: { threshold: 0.2 } },
			{ type: "max_turnover", params: { max_turnover: 0.5 } },
		]);
		const filter = node(buildStrategyPipeline(base, DESCRIPTORS), "filter:0");
		const updated = updatePipelineNodeConfig(base, filter, "threshold", 0.4);
		expect(updated.constraints).toEqual([
			{ type: "builtin.trend_filter@1", params: { threshold: 0.4 } },
			base.constraints[1],
		]);
		expect(updatePipelineNodeConfig(base, { ...filter, readOnly: true }, "threshold", 0.9)).toBe(base);
	});
});
