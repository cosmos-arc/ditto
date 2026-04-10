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

	it("generates an SVG path from data array", () => {
		render(<Sparkline data={[0, 5, 3, 8]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toBeInTheDocument();
		expect(path).toHaveAttribute("d");
		// Path d should start with M (moveTo)
		expect(path?.getAttribute("d")).toMatch(/^M/);
	});

	it("maps color='up' to market-up CSS variable", () => {
		render(<Sparkline data={[1, 2, 3]} color="up" />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveAttribute("stroke", "var(--color-market-up)");
	});

	it("maps color='down' to market-down CSS variable", () => {
		render(<Sparkline data={[1, 2, 3]} color="down" />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveAttribute("stroke", "var(--color-market-down)");
	});

	it("maps color='neutral' to foreground-muted CSS variable", () => {
		render(<Sparkline data={[1, 2, 3]} color="neutral" />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveAttribute("stroke", "var(--color-foreground-muted)");
	});

	it("generates gradient fill when gradient=true", () => {
		render(<Sparkline data={[1, 3, 2, 5]} gradient />);
		const svg = screen.getByRole("img", { hidden: true });
		// Should have a linearGradient definition
		const gradient = svg.querySelector("linearGradient");
		expect(gradient).toBeInTheDocument();
		// Should have an area fill path
		const areaPath = svg.querySelector("path[data-part='area']");
		expect(areaPath).toBeInTheDocument();
	});

	it("does not render gradient when gradient=false", () => {
		render(<Sparkline data={[1, 3, 2, 5]} gradient={false} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg.querySelector("linearGradient")).not.toBeInTheDocument();
		expect(svg.querySelector("path[data-part='area']")).not.toBeInTheDocument();
	});

	it("uses default strokeWidth of 1.5", () => {
		render(<Sparkline data={[1, 2, 3]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveAttribute("stroke-width", "1.5");
	});

	it("applies custom strokeWidth", () => {
		render(<Sparkline data={[1, 2, 3]} strokeWidth={2} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveAttribute("stroke-width", "2");
	});

	it("applies animate class when animate=true", () => {
		render(<Sparkline data={[1, 2, 3]} animate />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveClass("animate-sparkline");
	});

	it("does not apply animate class when animate=false", () => {
		render(<Sparkline data={[1, 2, 3]} animate={false} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).not.toHaveClass("animate-sparkline");
	});

	it("renders empty SVG gracefully when data is empty", () => {
		render(<Sparkline data={[]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toBeInTheDocument();
		expect(svg.querySelector("path")).not.toBeInTheDocument();
	});

	it("renders empty SVG gracefully when data has single element", () => {
		render(<Sparkline data={[42]} />);
		const svg = screen.getByRole("img", { hidden: true });
		expect(svg).toBeInTheDocument();
		expect(svg.querySelector("path")).not.toBeInTheDocument();
	});

	it("renders a straight line path when data has exactly 2 points", () => {
		render(<Sparkline data={[0, 10]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toBeInTheDocument();
		// 2 points → simple M ... L ... path (no curves)
		const d = path?.getAttribute("d") ?? "";
		expect(d).toMatch(/^M[\d.]+,[\d.]+ L[\d.]+,[\d.]+$/);
	});

	it("uses smooth curves for 3+ data points (Catmull-Rom)", () => {
		render(<Sparkline data={[0, 5, 3, 8, 2]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toBeInTheDocument();
		// Catmull-Rom path should contain C (cubic Bezier) commands
		const d = path?.getAttribute("d") ?? "";
		expect(d).toContain("C");
	});

	it("maps data values to correct SVG coordinate space", () => {
		render(<Sparkline data={[0, 10]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		const d = path?.getAttribute("d") ?? "";
		// First point x should be 0, last point x should be 48
		const moveTo = d.match(/^M([\d.]+),([\d.]+)/);
		const lineTo = d.match(/L([\d.]+),([\d.]+)$/);
		expect(moveTo?.[1]).toBe("0");
		expect(lineTo?.[1]).toBe("48");
	});

	it("renders stroke path without fill by default", () => {
		render(<Sparkline data={[1, 2, 3]} />);
		const svg = screen.getByRole("img", { hidden: true });
		const path = svg.querySelector("path[data-part='stroke']");
		expect(path).toHaveAttribute("fill", "none");
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
		const path = svg.querySelector("path[data-part='stroke']");
		const d = path?.getAttribute("d") ?? "";
		const moveTo = d.match(/^M([\d.]+),([\d.]+)/);
		const lineTo = d.match(/L([\d.]+),([\d.]+)$/);
		// min (0) → y = height = 20, max (10) → y = 0
		expect(moveTo?.[2]).toBe("20");
		expect(lineTo?.[2]).toBe("0");
	});

	it("uses unique gradient ID per instance via useId", () => {
		const { container: c1 } = render(<Sparkline data={[1, 2, 3]} gradient />);
		const { container: c2 } = render(<Sparkline data={[1, 2, 3]} gradient />);
		const g1 = c1.querySelector("linearGradient");
		const g2 = c2.querySelector("linearGradient");
		// Each instance should have its own gradient ID
		expect(g1?.id).toBeTruthy();
		expect(g2?.id).toBeTruthy();
		expect(g1?.id).not.toBe(g2?.id);
	});
});
