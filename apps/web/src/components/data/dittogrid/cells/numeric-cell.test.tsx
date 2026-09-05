import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NumericCell } from "./numeric-cell";

describe("NumericCell", () => {
	it("renders formatted number with thousand separators", () => {
		render(<NumericCell value={1234567.89} />);
		expect(screen.getByText("1,234,567.89")).toBeInTheDocument();
	});

	it("renders integer without decimal places", () => {
		render(<NumericCell value={1000} />);
		expect(screen.getByText("1,000")).toBeInTheDocument();
	});

	it("renders negative numbers correctly", () => {
		render(<NumericCell value={-42} />);
		expect(screen.getByText("-42")).toBeInTheDocument();
	});

	it("renders zero correctly", () => {
		render(<NumericCell value={0} />);
		expect(screen.getByText("0")).toBeInTheDocument();
	});

	it("has data-slot attribute on wrapper", () => {
		render(<NumericCell value={42} />);
		const wrapper = screen.getByTestId("numeric-cell-root");
		expect(wrapper).toHaveAttribute("data-slot", "numeric-cell");
	});

	it("applies right-alignment and data font", () => {
		render(<NumericCell value={42} />);
		const wrapper = screen.getByTestId("numeric-cell-root");
		expect(wrapper.className).toContain("text-right");
		expect(wrapper.className).toContain("[font-family:var(--font-data)]");
		expect(wrapper.className).toContain("tabular-nums");
	});
});
