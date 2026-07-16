import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrendCell } from "./trend-cell";

describe("TrendCell", () => {
	it("renders up arrow and market-up color for positive value", () => {
		render(<TrendCell value={5.2} />);
		const content = screen.getByTestId("trend-cell-root");
		expect(content).toHaveTextContent("▲");
		expect(content.className).toContain("text-(--color-market-up)");
	});

	it("renders down arrow and market-down color for negative value", () => {
		render(<TrendCell value={-3.1} />);
		const content = screen.getByTestId("trend-cell-root");
		expect(content).toHaveTextContent("▼");
		expect(content.className).toContain("text-(--color-market-down)");
	});

	it("renders dash and muted color for zero value", () => {
		render(<TrendCell value={0} />);
		const content = screen.getByTestId("trend-cell-root");
		expect(content).toHaveTextContent("—");
		expect(content.className).toContain("text-(--color-foreground-muted)");
	});

	it("has data-slot attribute on wrapper", () => {
		render(<TrendCell value={1.5} />);
		const wrapper = screen.getByTestId("trend-cell-root");
		expect(wrapper).toHaveAttribute("data-slot", "trend-cell");
	});
});
