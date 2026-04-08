import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sparkline } from "./sparkline";

describe("Sparkline", () => {
	it("renders an SVG element with default dimensions", () => {
		render(<Sparkline data={[1, 2, 3, 4, 5]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg.tagName).toBe("svg");
		expect(svg).toHaveAttribute("width", "48");
		expect(svg).toHaveAttribute("height", "20");
	});

	it("has data-slot attribute on root element", () => {
		render(<Sparkline data={[1, 2, 3]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toHaveAttribute("data-slot", "sparkline");
	});

	it("generates a polyline from data array", () => {
		render(<Sparkline data={[0, 5, 3, 8]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toBeInTheDocument();
		expect(polyline).toHaveAttribute("points");
		// Points should have exactly 4 entries (one per data point)
		const points = polyline?.getAttribute("points")?.trim().split(/\s+/);
		expect(points).toHaveLength(4);
	});

	it("maps color='up' to market-up CSS variable", () => {
		render(<Sparkline data={[1, 2, 3]} color="up" />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveAttribute("stroke", "var(--color-market-up)");
	});

	it("maps color='down' to market-down CSS variable", () => {
		render(<Sparkline data={[1, 2, 3]} color="down" />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveAttribute("stroke", "var(--color-market-down)");
	});

	it("maps color='neutral' to foreground-muted CSS variable", () => {
		render(<Sparkline data={[1, 2, 3]} color="neutral" />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveAttribute("stroke", "var(--color-foreground-muted)");
	});

	it("generates gradient fill when gradient=true", () => {
		render(<Sparkline data={[1, 3, 2, 5]} gradient />);
		const svg = screen.getByRole("img", { hidden: true });
		// Should have a linearGradient definition
		const gradient = svg.querySelector("linearGradient");
		expect(gradient).toBeInTheDocument();
		// Should have a polygon for the filled area
		const polygon = svg.querySelector("polygon");
		expect(polygon).toBeInTheDocument();
	});

	it("does not render gradient when gradient=false", () => {
		render(<Sparkline data={[1, 3, 2, 5]} gradient={false} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg.querySelector("linearGradient")).not.toBeInTheDocument();
		expect(svg.querySelector("polygon")).not.toBeInTheDocument();
	});

	it("uses default strokeWidth of 1.5", () => {
		render(<Sparkline data={[1, 2, 3]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveAttribute("stroke-width", "1.5");
	});

	it("applies custom strokeWidth", () => {
		render(<Sparkline data={[1, 2, 3]} strokeWidth={2} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveAttribute("stroke-width", "2");
	});

	it("applies animate class when animate=true", () => {
		render(<Sparkline data={[1, 2, 3]} animate />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveClass("animate-sparkline");
	});

	it("does not apply animate class when animate=false", () => {
		render(<Sparkline data={[1, 2, 3]} animate={false} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).not.toHaveClass("animate-sparkline");
	});

	it("renders empty SVG gracefully when data is empty", () => {
		render(<Sparkline data={[]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toBeInTheDocument();
		expect(svg.querySelector("polyline")).not.toBeInTheDocument();
	});

	it("renders empty SVG gracefully when data has single element", () => {
		render(<Sparkline data={[42]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toBeInTheDocument();
		expect(svg.querySelector("polyline")).not.toBeInTheDocument();
	});

	it("renders a straight line when data has exactly 2 points", () => {
		render(<Sparkline data={[0, 10]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toBeInTheDocument();
		const points = polyline?.getAttribute("points")?.trim().split(/\s+/);
		expect(points).toHaveLength(2);
	});

	it("maps data values to correct SVG coordinate space", () => {
		render(<Sparkline data={[0, 10]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		const points = polyline?.getAttribute("points") ?? "";
		// First point should be at x=0 (left edge), last at x=48 (right edge)
		const [first, second] = points.trim().split(/\s+/);
		expect(first?.split(",")[0]).toBe("0");
		expect(second?.split(",")[0]).toBe("48");
	});

	it("renders polyline without fill by default", () => {
		render(<Sparkline data={[1, 2, 3]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		expect(polyline).toHaveAttribute("fill", "none");
	});

	it("applies custom className", () => {
		render(<Sparkline data={[1, 2, 3]} className="custom-class" />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toHaveClass("custom-class");
	});

	it("sets data-variant attribute matching color", () => {
		render(<Sparkline data={[1, 2, 3]} color="up" />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toHaveAttribute("data-variant", "up");
	});

	it("computes correct y coordinates for min/max normalization", () => {
		// Data [0, 10] with height 20: min maps to y=20, max maps to y=0
		render(<Sparkline data={[0, 10]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const polyline = svg.querySelector("polyline");
		const points = polyline?.getAttribute("points") ?? "";
		const [first, second] = points.trim().split(/\s+/);
		// min (0) → y = height = 20, max (10) → y = 0
		expect(first?.split(",")[1]).toBe("20");
		expect(second?.split(",")[1]).toBe("0");
	});
});
