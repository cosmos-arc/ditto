import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockNodeDescriptorList } from "@/mocks/fixtures/strategy-live";
import type { StrategySpec } from "@/types/strategy";
import { mapNodeDescriptor } from "../api/mappers";
import { NodeInspector } from "./strategy-inspector";

const DESCRIPTORS = mockNodeDescriptorList.map(mapNodeDescriptor);

function baseSpec(type = "builtin.trend_filter@1"): StrategySpec {
	return {
		strategyId: "s",
		name: "n",
		template: "etf_rotation",
		universe: "csi_etf_broad",
		assetClass: "etf",
		benchmark: "",
		scorer: { method: "m", params: {} },
		selector: { method: "top_k", params: { k: 5 } },
		execution: { frequency: "M", method: "calendar", defaultOrderType: "market" },
		constraints: [{ type, params: { direction: "long", signal_column: "signal_value", threshold: 0.3 } }],
		params: { lookback: 252 },
		signalExpressions: [],
		signalWeights: [],
		paramConstraints: [],
	};
}

describe("NodeInspector", () => {
	it("shows a read-only overview when no node is selected", () => {
		render(<NodeInspector spec={baseSpec()} descriptors={DESCRIPTORS} selectedKey={null} onChange={vi.fn()} />);
		expect(screen.getByText("策略参数")).toBeInTheDocument();
	});

	it("renders config fields exclusively from the selected descriptor schema", () => {
		render(<NodeInspector spec={baseSpec()} descriptors={DESCRIPTORS} selectedKey="filter:0" onChange={vi.fn()} />);
		expect(screen.getByLabelText("direction")).toHaveValue("long");
		expect(screen.getByLabelText("signal_column")).toHaveValue("signal_value");
		expect(screen.getByLabelText("threshold")).toHaveValue(0.3);
	});

	it("updates a schema-backed config field", () => {
		const onChange = vi.fn();
		const spec = baseSpec();
		render(<NodeInspector spec={spec} descriptors={DESCRIPTORS} selectedKey="filter:0" onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("threshold"), { target: { value: "0.5" } });
		const updater = onChange.mock.calls[0][0] as (draft: StrategySpec) => StrategySpec;
		expect(updater(spec).constraints[0].params.threshold).toBe(0.5);
	});

	it("shows unknown descriptor config read-only", () => {
		render(
			<NodeInspector
				spec={baseSpec("plugin.unknown@9")}
				descriptors={DESCRIPTORS}
				selectedKey="filter:0"
				onChange={vi.fn()}
			/>,
		);
		expect(screen.getByText("未知 descriptor")).toBeInTheDocument();
		expect(screen.getByText(/不可删除/)).toBeInTheDocument();
	});
});
