import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StrategySpec } from "@/types/strategy";
import { StrategySpecForm } from "./strategy-spec-form";

const SAMPLE_SPEC: StrategySpec = {
	strategyId: "seed_etf_industry_rotation",
	name: "ETF 行业轮动",
	template: "etf_rotation",
	universe: "csi_etf_broad",
	assetClass: "etf",
	benchmark: "000300.SH",
	scorer: { method: "rank_then_combine", params: {} },
	selector: { method: "top_k", params: { k: 5 } },
	execution: {
		frequency: "M",
		method: "calendar",
		defaultOrderType: "market",
		costModel: { commissionRate: 0.0003, slippageBps: 5.0, impactModel: "none" },
	},
	constraints: [],
	params: { lookback: 252 },
	signalExpressions: [],
	signalWeights: [],
	paramConstraints: [],
};

describe("StrategySpecForm", () => {
	it("renders scalar fields populated with current spec values", () => {
		render(<StrategySpecForm spec={SAMPLE_SPEC} onChange={vi.fn()} />);
		expect(screen.getByLabelText("名称")).toHaveValue("ETF 行业轮动");
		expect(screen.getByLabelText("模板")).toHaveValue("etf_rotation");
	});

	it("fires onChange with an updater that sets the edited name", () => {
		const onChange = vi.fn();
		render(<StrategySpecForm spec={SAMPLE_SPEC} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("名称"), { target: { value: "新策略" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(SAMPLE_SPEC).name).toBe("新策略");
	});

	it("fires onChange with an updater that updates a selector.params scalar", () => {
		const onChange = vi.fn();
		render(<StrategySpecForm spec={SAMPLE_SPEC} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("k"), { target: { value: "10" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(SAMPLE_SPEC).selector.params).toEqual({ k: 10 });
	});

	it("fires onChange with an updater that updates execution.defaultOrderType", () => {
		const onChange = vi.fn();
		render(<StrategySpecForm spec={SAMPLE_SPEC} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("下单类型"), { target: { value: "limit" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(SAMPLE_SPEC).execution.defaultOrderType).toBe("limit");
	});
});
