import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NumberField, TextField } from "./spec-fields";

describe("spec-fields", () => {
	it("TextField renders label and current value, fires onChange with the new string", () => {
		const onChange = vi.fn();
		render(<TextField label="名称" value="ETF 轮动" onChange={onChange} />);

		expect(screen.getByText("名称")).toBeInTheDocument();
		expect(screen.getByDisplayValue("ETF 轮动")).toBeInTheDocument();
		fireEvent.change(screen.getByLabelText("名称"), { target: { value: "新名称" } });

		expect(onChange).toHaveBeenLastCalledWith("新名称");
	});

	it("NumberField parses numeric input and fires onChange with a number", () => {
		const onChange = vi.fn();
		render(<NumberField label="K" value={5} onChange={onChange} />);

		fireEvent.change(screen.getByLabelText("K"), { target: { value: "10" } });

		expect(onChange).toHaveBeenLastCalledWith(10);
	});

	it("NumberField falls back to 0 for empty/non-numeric input", () => {
		const onChange = vi.fn();
		render(<NumberField label="窗口" value={60} onChange={onChange} />);

		fireEvent.change(screen.getByLabelText("窗口"), { target: { value: "" } });

		expect(onChange).toHaveBeenLastCalledWith(0);
	});
});
