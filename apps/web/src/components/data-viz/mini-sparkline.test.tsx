import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MiniSparkline } from "./mini-sparkline";

describe("MiniSparkline", () => {
	it("renders SVG element with accessible role", () => {
		render(<MiniSparkline data={[1, 3, 2, 5, 4]} />);
		const svg = document.querySelector("svg");
		expect(svg).toBeInTheDocument();
		expect(svg).toHaveAttribute("role", "img");
	});

	it("renders polyline with correct number of points", () => {
		render(<MiniSparkline data={[1, 3, 2, 5, 4]} />);
		const polyline = document.querySelector("polyline");
		expect(polyline).toBeInTheDocument();
		const points = polyline?.getAttribute("points")?.trim().split(" ");
		expect(points).toHaveLength(5);
	});

	it("applies default dimensions (24x12)", () => {
		render(<MiniSparkline data={[1, 3, 2]} />);
		const svg = document.querySelector("svg");
		expect(svg).toHaveAttribute("width", "24");
		expect(svg).toHaveAttribute("height", "12");
	});

	it("supports custom dimensions", () => {
		render(<MiniSparkline data={[1, 2]} width={48} height={24} />);
		const svg = document.querySelector("svg");
		expect(svg).toHaveAttribute("width", "48");
		expect(svg).toHaveAttribute("height", "24");
	});

	it("applies positive trend color class by default", () => {
		render(<MiniSparkline data={[1, 2, 3]} trend="up" />);
		const svg = document.querySelector("svg");
		expect(svg?.className.baseVal).toContain("stroke-(--color-market-up)");
	});

	it("applies negative trend color class", () => {
		render(<MiniSparkline data={[3, 2, 1]} trend="down" />);
		const svg = document.querySelector("svg");
		expect(svg?.className.baseVal).toContain("stroke-(--color-market-down)");
	});

	it("applies neutral color class", () => {
		render(<MiniSparkline data={[2, 2, 2]} trend="neutral" />);
		const svg = document.querySelector("svg");
		expect(svg?.className.baseVal).toContain("stroke-(--color-foreground-muted)");
	});

	it("renders with aria-label", () => {
		render(<MiniSparkline data={[1, 3, 2]} ariaLabel="市场脉搏趋势" />);
		const svg = document.querySelector("svg");
		expect(svg).toHaveAttribute("aria-label", "市场脉搏趋势");
	});

	it("handles single data point gracefully", () => {
		render(<MiniSparkline data={[5]} />);
		const polyline = document.querySelector("polyline");
		expect(polyline).toBeInTheDocument();
		const points = polyline?.getAttribute("points")?.trim().split(" ");
		expect(points).toHaveLength(1);
	});

	it("handles empty data array", () => {
		render(<MiniSparkline data={[]} />);
		const polyline = document.querySelector("polyline");
		expect(polyline).toBeInTheDocument();
		expect(polyline?.getAttribute("points")).toBe("");
	});
});
