import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SparklineCell } from "./sparkline-cell";

describe("SparklineCell", () => {
	it("renders a Sparkline SVG when data is provided", () => {
		render(<SparklineCell data={[1, 3, 2, 5, 4]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toBeInTheDocument();
		expect(svg).toHaveAttribute("data-slot", "sparkline");
	});

	it("passes color prop to Sparkline", () => {
		render(<SparklineCell data={[1, 2, 3]} color="up" />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toHaveAttribute("data-variant", "up");
	});

	it("passes gradient prop to Sparkline", () => {
		render(<SparklineCell data={[1, 2, 3]} gradient />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg.querySelector("linearGradient")).toBeInTheDocument();
	});

	it("has data-slot attribute on wrapper", () => {
		render(<SparklineCell data={[1, 2, 3]} />);
		const wrapper = screen.getByTestId("sparkline-cell-root");
		expect(wrapper).toHaveAttribute("data-slot", "sparkline-cell");
	});
});
