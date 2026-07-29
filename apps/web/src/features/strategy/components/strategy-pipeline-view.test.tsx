import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConstraintSpec, StrategySpec } from "@/types/strategy";
import { ConstraintsPipeline } from "./strategy-pipeline-view";

const CONSTRAINT_A: ConstraintSpec = { type: "max_weight_per_instrument", params: { max_weight: 0.3 } };
const CONSTRAINT_B: ConstraintSpec = { type: "max_turnover", params: { max_turnover: 0.5 } };

function baseSpec(constraints: readonly ConstraintSpec[]): StrategySpec {
	return {
		strategyId: "s",
		name: "n",
		template: "t",
		universe: "u",
		assetClass: "etf",
		benchmark: "",
		scorer: { method: "m", params: {} },
		selector: { method: "m", params: {} },
		execution: { frequency: "M", method: "calendar", defaultOrderType: "market" },
		constraints,
		params: {},
		signalExpressions: [],
		signalWeights: [],
		paramConstraints: [],
	};
}

describe("ConstraintsPipeline", () => {
	it("renders each constraint type plus an add button", () => {
		render(
			<ConstraintsPipeline
				constraints={[CONSTRAINT_A, CONSTRAINT_B]}
				onChange={vi.fn()}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		expect(screen.getByText("max_weight_per_instrument")).toBeInTheDocument();
		expect(screen.getByText("max_turnover")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "添加约束" })).toBeInTheDocument();
	});

	it("appends a new constraint via onChange updater", () => {
		const onChange = vi.fn();
		const base = baseSpec([CONSTRAINT_A]);
		render(
			<ConstraintsPipeline constraints={base.constraints} onChange={onChange} onSelect={vi.fn()} selectedKey={null} />,
		);
		fireEvent.click(screen.getByRole("button", { name: "添加约束" }));

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).constraints).toHaveLength(2);
		expect(updater(base).constraints[1].type).toBe("new_constraint");
	});

	it("removes a constraint via onChange updater", () => {
		const onChange = vi.fn();
		const base = baseSpec([CONSTRAINT_A, CONSTRAINT_B]);
		render(
			<ConstraintsPipeline constraints={base.constraints} onChange={onChange} onSelect={vi.fn()} selectedKey={null} />,
		);
		fireEvent.click(screen.getByLabelText("删除约束 1"));

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).constraints).toEqual([CONSTRAINT_B]);
	});

	it("moves a constraint down by swapping with the next", () => {
		const onChange = vi.fn();
		const base = baseSpec([CONSTRAINT_A, CONSTRAINT_B]);
		render(
			<ConstraintsPipeline constraints={base.constraints} onChange={onChange} onSelect={vi.fn()} selectedKey={null} />,
		);
		fireEvent.click(screen.getByLabelText("下移约束 1"));

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).constraints).toEqual([CONSTRAINT_B, CONSTRAINT_A]);
	});

	it("disables move-up on the first row and move-down on the last", () => {
		render(
			<ConstraintsPipeline
				constraints={[CONSTRAINT_A, CONSTRAINT_B]}
				onChange={vi.fn()}
				onSelect={vi.fn()}
				selectedKey={null}
			/>,
		);
		expect(screen.getByLabelText("上移约束 1")).toBeDisabled();
		expect(screen.getByLabelText("下移约束 2")).toBeDisabled();
	});

	it("calls onSelect with the constraint key when a row is clicked", () => {
		const onSelect = vi.fn();
		render(
			<ConstraintsPipeline constraints={[CONSTRAINT_A]} onChange={vi.fn()} onSelect={onSelect} selectedKey={null} />,
		);
		fireEvent.click(screen.getByText("max_weight_per_instrument"));
		expect(onSelect).toHaveBeenCalledWith("constraint-0");
	});
});
