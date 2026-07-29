import { describe, expect, it } from "vitest";
import type { components } from "@/types/generated/api";
import { mapStrategyDetail, parseSpecJson, serializeStrategySpec } from "../mappers";

type StrategyResponse = components["schemas"]["StrategyResponse"];

const SEED_SPEC_JSON = {
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

const baseResponse: StrategyResponse = {
	strategy_id: "seed_etf_industry_rotation",
	name: "ETF 行业轮动",
	spec_json: SEED_SPEC_JSON,
	version: 3,
	status: "published",
	created_at: "2026-04-08T15:00:00Z",
	tags: ["etf", "rotation"],
};

describe("strategy spec round-trip", () => {
	it("parse → serialize → parse is idempotent (form/code 切换保持同一 spec)", () => {
		const detail1 = mapStrategyDetail(baseResponse);
		const serialized = serializeStrategySpec(detail1.spec);
		const detail2 = mapStrategyDetail({ ...baseResponse, spec_json: serialized });

		expect(detail2.spec).toEqual(detail1.spec);
	});

	it("serialize produces legacy snake_case spec_json shape", () => {
		const spec = parseSpecJson(SEED_SPEC_JSON, { strategyId: "s", name: "n" });
		const json = serializeStrategySpec(spec);

		const execution = json.execution as Record<string, unknown>;
		expect(json).toHaveProperty("strategy_id");
		expect(json).toHaveProperty("asset_class");
		expect(execution).toHaveProperty("cost_model");
		expect(json).not.toHaveProperty("strategyId");
		expect(json).not.toHaveProperty("assetClass");
	});

	it("preserves numeric params and constraint list across round-trip", () => {
		const detail = mapStrategyDetail(baseResponse);
		const roundTripped = mapStrategyDetail({
			...baseResponse,
			spec_json: serializeStrategySpec(detail.spec),
		});

		expect(roundTripped.spec.params).toEqual({ lookback: 252, vol_window: 60 });
		expect(roundTripped.spec.constraints).toHaveLength(2);
		expect(roundTripped.spec.execution.costModel?.commissionRate).toBe(0.0003);
	});

	it("保存创建新 draft 不覆盖：不同 spec_json 产生不同 canonical payload", () => {
		const original = mapStrategyDetail(baseResponse).spec;
		const edited = parseSpecJson(
			{ ...SEED_SPEC_JSON, selector: { method: "top_k", params: { k: 10 } } },
			{ strategyId: "s", name: "n" },
		);

		expect(serializeStrategySpec(edited)).not.toEqual(serializeStrategySpec(original));
		expect(edited.selector.params).toEqual({ k: 10 });
		expect(original.selector.params).toEqual({ k: 5 });
	});
});
