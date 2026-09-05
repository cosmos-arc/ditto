import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StrategySpec } from "@/types/strategy";
import { SignalExpressionsEditor } from "./signal-expressions-editor";

function specWith(expressions: readonly string[], weights: readonly number[]): StrategySpec {
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
		signalExpressions: expressions,
		signalWeights: weights,
		paramConstraints: [],
	};
}

function firstUpdater(mock: ReturnType<typeof vi.fn>): (draft: StrategySpec) => StrategySpec {
	const updater: unknown = mock.mock.calls[0]?.[0];
	if (typeof updater !== "function") throw new Error("expected an updater call");
	return updater as (draft: StrategySpec) => StrategySpec;
}

describe("SignalExpressionsEditor", () => {
	it("renders each coupled expression/weight pair", () => {
		render(<SignalExpressionsEditor spec={specWith(["momentum_1m", "reversal_1w"], [0.6, 0.4])} onChange={vi.fn()} />);
		expect(screen.getByLabelText("信号表达式 1")).toHaveValue("momentum_1m");
		expect(screen.getByLabelText("权重 1")).toHaveValue(0.6);
		expect(screen.getByLabelText("信号表达式 2")).toHaveValue("reversal_1w");
		expect(screen.getByLabelText("权重 2")).toHaveValue(0.4);
	});

	it("add appends a coupled pair so both arrays stay equal-length", () => {
		const onChange = vi.fn();
		const base = specWith(["momentum_1m"], [0.6]);
		render(<SignalExpressionsEditor spec={base} onChange={onChange} />);
		fireEvent.click(screen.getByRole("button", { name: "添加信号" }));

		const updater = firstUpdater(onChange);
		const next = updater(base);
		expect(next.signalExpressions).toEqual(["momentum_1m", "new_signal"]);
		expect(next.signalWeights).toEqual([0.6, 0]);
		expect(next.signalExpressions).toHaveLength(next.signalWeights.length);
	});

	it("remove drops both the expression and its coupled weight at the index", () => {
		const onChange = vi.fn();
		const base = specWith(["a", "b", "c"], [0.5, 0.3, 0.2]);
		render(<SignalExpressionsEditor spec={base} onChange={onChange} />);
		fireEvent.click(screen.getByLabelText("删除信号 2"));

		const updater = firstUpdater(onChange);
		const next = updater(base);
		expect(next.signalExpressions).toEqual(["a", "c"]);
		expect(next.signalWeights).toEqual([0.5, 0.2]);
	});

	it("move down swaps both expression and weight together (keeps pairing)", () => {
		const onChange = vi.fn();
		const base = specWith(["a", "b"], [0.6, 0.4]);
		render(<SignalExpressionsEditor spec={base} onChange={onChange} />);
		fireEvent.click(screen.getByLabelText("下移信号 1"));

		const updater = firstUpdater(onChange);
		const next = updater(base);
		expect(next.signalExpressions).toEqual(["b", "a"]);
		expect(next.signalWeights).toEqual([0.4, 0.6]);
	});

	it("editing an expression input updates only that expression (weight untouched)", () => {
		const onChange = vi.fn();
		const base = specWith(["a", "b"], [0.6, 0.4]);
		render(<SignalExpressionsEditor spec={base} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("信号表达式 2"), { target: { value: "b_edited" } });

		const updater = firstUpdater(onChange);
		const next = updater(base);
		expect(next.signalExpressions).toEqual(["a", "b_edited"]);
		expect(next.signalWeights).toEqual([0.6, 0.4]);
	});

	it("editing a weight input parses to a number and leaves expressions untouched", () => {
		const onChange = vi.fn();
		const base = specWith(["a"], [0.6]);
		render(<SignalExpressionsEditor spec={base} onChange={onChange} />);
		fireEvent.change(screen.getByLabelText("权重 1"), { target: { value: "0.9" } });

		const updater = firstUpdater(onChange);
		const next = updater(base);
		expect(next.signalWeights).toEqual([0.9]);
		expect(next.signalExpressions).toEqual(["a"]);
	});

	it("disables move-up on the first row and move-down on the last", () => {
		render(<SignalExpressionsEditor spec={specWith(["a", "b"], [0.6, 0.4])} onChange={vi.fn()} />);
		expect(screen.getByLabelText("上移信号 1")).toBeDisabled();
		expect(screen.getByLabelText("下移信号 2")).toBeDisabled();
	});
});
