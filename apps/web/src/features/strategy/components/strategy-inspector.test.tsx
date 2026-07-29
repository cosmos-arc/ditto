import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConstraintSpec, StrategySpec } from "@/types/strategy";
import { NodeInspector } from "./strategy-inspector";

const CONSTRAINT: ConstraintSpec = { type: "max_weight_per_instrument", params: { max_weight: 0.3 } };

function baseSpec(constraints: readonly ConstraintSpec[] = [CONSTRAINT]): StrategySpec {
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
		constraints,
		params: { lookback: 252 },
		signalExpressions: [],
		signalWeights: [],
		paramConstraints: [],
	};
}

describe("NodeInspector", () => {
	it("shows a read-only overview when no constraint is selected", () => {
		render(<NodeInspector spec={baseSpec()} selectedKey={null} onChange={vi.fn()} />);
		expect(screen.getByText("策略参数")).toBeInTheDocument();
		expect(screen.getByText("csi_etf_broad")).toBeInTheDocument();
	});

	it("shows a constraint editor when a constraint key is selected", () => {
		render(<NodeInspector spec={baseSpec()} selectedKey="constraint-0" onChange={vi.fn()} />);
		expect(screen.getByLabelText("约束类型")).toHaveValue("max_weight_per_instrument");
		expect(screen.getByLabelText("max_weight")).toBeInTheDocument();
	});

	it("updates the constraint type via onChange updater", () => {
		const onChange = vi.fn();
		const base = baseSpec();
		render(<NodeInspector spec={base} selectedKey="constraint-0" onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("约束类型"), { target: { value: "max_turnover" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).constraints[0].type).toBe("max_turnover");
	});

	it("updates a constraint param via onChange updater", () => {
		const onChange = vi.fn();
		const base = baseSpec();
		render(<NodeInspector spec={base} selectedKey="constraint-0" onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("max_weight"), { target: { value: "0.5" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).constraints[0].params).toEqual({ max_weight: 0.5 });
	});
});
