import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockNodeDescriptorList } from "@/mocks/fixtures/strategy-live";
import type { StrategySpec } from "@/types/strategy";
import { mapNodeDescriptor } from "../api/mappers";
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

const DESCRIPTORS = mockNodeDescriptorList.map(mapNodeDescriptor);

describe("StrategyEditor", () => {
	it("renders the spec form and constraints pipeline in form mode", () => {
		render(
			<StrategyEditor
				spec={SAMPLE_SPEC}
				mode="form"
				descriptors={DESCRIPTORS}
				selectedKey={null}
				onChange={vi.fn()}
				onSelect={vi.fn()}
			/>,
		);
		expect(screen.getByLabelText("名称")).toBeInTheDocument();
	});

	it("renders the descriptor-backed ordered editor in pipeline mode", () => {
		render(
			<StrategyEditor
				spec={SAMPLE_SPEC}
				mode="pipeline"
				descriptors={DESCRIPTORS}
				selectedKey={null}
				onChange={vi.fn()}
				onSelect={vi.fn()}
			/>,
		);
		expect(screen.getByText("受约束流水线")).toBeInTheDocument();
		expect(screen.queryByText(/"strategy_id"/)).not.toBeInTheDocument();
	});

	it("renders the signal-expressions and param-constraints editors in form mode", () => {
		render(
			<StrategyEditor
				spec={SAMPLE_SPEC}
				mode="form"
				descriptors={DESCRIPTORS}
				selectedKey={null}
				onChange={vi.fn()}
				onSelect={vi.fn()}
			/>,
		);
		expect(screen.getByRole("button", { name: "添加信号" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "添加参数约束" })).toBeInTheDocument();
	});
});
