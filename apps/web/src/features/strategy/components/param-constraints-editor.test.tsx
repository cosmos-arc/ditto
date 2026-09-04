import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ParamConstraintSpec, StrategySpec } from "@/types/strategy";
import { ParamConstraintsEditor } from "./param-constraints-editor";

const INT_CONSTRAINT: ParamConstraintSpec = {
	name: "lookback",
	dtype: "int",
	minValue: 21,
	maxValue: 504,
	step: 1,
	allowedValues: [],
};
const STR_CONSTRAINT: ParamConstraintSpec = { name: "mode", dtype: "str", allowedValues: ["fast", "slow"] };

function specWith(constraints: readonly ParamConstraintSpec[]): StrategySpec {
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
		constraints: [],
		params: {},
		signalExpressions: [],
		signalWeights: [],
		paramConstraints: constraints,
	};
}

describe("ParamConstraintsEditor", () => {
	it("renders name / dtype / min / max / step for a numeric constraint", () => {
		render(<ParamConstraintsEditor spec={specWith([INT_CONSTRAINT])} onChange={vi.fn()} />);
		expect(screen.getByLabelText("参数名 1")).toHaveValue("lookback");
		expect(screen.getByLabelText("类型 1")).toHaveValue("int");
		expect(screen.getByLabelText("最小值 1")).toHaveValue(21);
		expect(screen.getByLabelText("最大值 1")).toHaveValue(504);
		expect(screen.getByLabelText("步长 1")).toHaveValue(1);
	});

	it("renders allowedValues as a comma-joined string", () => {
		render(<ParamConstraintsEditor spec={specWith([STR_CONSTRAINT])} onChange={vi.fn()} />);
		expect(screen.getByLabelText("允许值 1")).toHaveValue("fast, slow");
	});

	it("hides min/max/step when dtype is str (non-numeric)", () => {
		render(<ParamConstraintsEditor spec={specWith([STR_CONSTRAINT])} onChange={vi.fn()} />);
		expect(screen.queryByLabelText("最小值 1")).toBeNull();
		expect(screen.queryByLabelText("最大值 1")).toBeNull();
		expect(screen.queryByLabelText("步长 1")).toBeNull();
	});

	it("add appends a new constraint with default name and dtype", () => {
		const onChange = vi.fn();
		const base = specWith([INT_CONSTRAINT]);
		render(<ParamConstraintsEditor spec={base} onChange={onChange} />);
		fireEvent.click(screen.getByRole("button", { name: "添加参数约束" }));

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		const next = updater(base);
		expect(next.paramConstraints).toHaveLength(2);
		expect(next.paramConstraints[1]).toEqual({ name: "", dtype: "int", allowedValues: [] });
	});

	it("remove drops the constraint at the index", () => {
		const onChange = vi.fn();
		const base = specWith([INT_CONSTRAINT, STR_CONSTRAINT]);
		render(<ParamConstraintsEditor spec={base} onChange={onChange} />);
		fireEvent.click(screen.getByLabelText("删除约束 1"));

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).paramConstraints).toEqual([STR_CONSTRAINT]);
	});

	it("move down swaps two constraints", () => {
		const onChange = vi.fn();
		const base = specWith([INT_CONSTRAINT, STR_CONSTRAINT]);
		render(<ParamConstraintsEditor spec={base} onChange={onChange} />);
		fireEvent.click(screen.getByLabelText("下移约束 1"));

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).paramConstraints).toEqual([STR_CONSTRAINT, INT_CONSTRAINT]);
	});

	it("editing the name input updates only the name", () => {
		const onChange = vi.fn();
		const base = specWith([INT_CONSTRAINT]);
		render(<ParamConstraintsEditor spec={base} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("参数名 1"), { target: { value: "window" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).paramConstraints[0].name).toBe("window");
		expect(updater(base).paramConstraints[0].dtype).toBe("int");
	});

	it("changing dtype to float shows min/max/step fields", () => {
		const onChange = vi.fn();
		const base = specWith([INT_CONSTRAINT]);
		render(<ParamConstraintsEditor spec={base} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("类型 1"), { target: { value: "float" } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).paramConstraints[0].dtype).toBe("float");
	});

	it("editing allowedValues splits comma-separated text into a string array", () => {
		const onChange = vi.fn();
		const base = specWith([STR_CONSTRAINT]);
		render(<ParamConstraintsEditor spec={base} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("允许值 1"), { target: { value: "x, y ,z," } });

		const updater = onChange.mock.calls[0][0] as (d: StrategySpec) => StrategySpec;
		expect(updater(base).paramConstraints[0].allowedValues).toEqual(["x", "y", "z"]);
	});
});
