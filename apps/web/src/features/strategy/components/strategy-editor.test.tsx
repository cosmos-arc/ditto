import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StrategySpec } from "@/types/strategy";
import { StrategyEditor } from "./strategy-editor";

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
	constraints: [{ type: "max_weight_per_instrument", params: { max_weight: 0.3 } }],
	params: { lookback: 252 },
	signalExpressions: [],
	signalWeights: [],
	paramConstraints: [],
};

describe("StrategyEditor", () => {
	it("renders the spec form and constraints pipeline in form mode", () => {
		render(<StrategyEditor spec={SAMPLE_SPEC} mode="form" selectedKey={null} onChange={vi.fn()} onSelect={vi.fn()} />);
		expect(screen.getByLabelText("名称")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "添加约束" })).toBeInTheDocument();
	});

	it("renders a read-only JSON preview of the serialized spec in code mode", () => {
		render(<StrategyEditor spec={SAMPLE_SPEC} mode="code" selectedKey={null} onChange={vi.fn()} onSelect={vi.fn()} />);
		expect(screen.getByText(/"strategy_id"/)).toBeInTheDocument();
	});

	it("renders the signal-expressions and param-constraints editors in form mode", () => {
		render(<StrategyEditor spec={SAMPLE_SPEC} mode="form" selectedKey={null} onChange={vi.fn()} onSelect={vi.fn()} />);
		expect(screen.getByRole("button", { name: "添加信号" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "添加参数约束" })).toBeInTheDocument();
	});
});
