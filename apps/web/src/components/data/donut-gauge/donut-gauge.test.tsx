import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DonutGauge } from "./donut-gauge";

describe("DonutGauge", () => {
	/* ── 基础渲染 ── */

	it("renders an SVG element", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		expect(svg.tagName).toBe("svg");
	});

	it("has data-slot='donut-gauge' on root SVG", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("data-slot", "donut-gauge");
	});

	it("has role='img' for accessibility", () => {
		render(<DonutGauge value={0.75} />);
		const svg = screen.getByRole("img");
		expect(svg).toBeInTheDocument();
	});

	it("has aria-label for accessibility", () => {
		render(<DonutGauge value={0.75} label="Progress" />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("aria-label", "Progress 75%");
	});

	it("has default aria-label when label is omitted", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("aria-label", "50%");
	});

	/* ── 默认尺寸与 viewBox ── */

	it("uses default size of 64", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("width", "64");
		expect(svg).toHaveAttribute("height", "64");
		expect(svg).toHaveAttribute("viewBox", "0 0 64 64");
	});

	it("applies custom size", () => {
		render(<DonutGauge value={0.5} size={100} />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("width", "100");
		expect(svg).toHaveAttribute("height", "100");
		expect(svg).toHaveAttribute("viewBox", "0 0 100 100");
	});

	/* ── SVG 圆环结构 ── */

	it("renders two circle elements (track + value)", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		const circles = svg.querySelectorAll("circle");
		expect(circles).toHaveLength(2);
	});

	it("renders track circle as background ring", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		const trackCircle = svg.querySelector("circle:first-child");
		expect(trackCircle).toBeInTheDocument();
		// Track circle: no stroke-dasharray, no stroke-dashoffset
		expect(trackCircle?.hasAttribute("stroke-dasharray")).toBe(false);
	});

	it("renders value circle with stroke-dasharray and stroke-dashoffset", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		expect(valueCircle).toBeInTheDocument();
		expect(valueCircle?.getAttribute("stroke-dasharray")).toBeTruthy();
		expect(valueCircle?.getAttribute("stroke-dashoffset")).toBeTruthy();
	});

	/* ── 颜色 ── */

	it("uses default color var(--color-accent) for value circle", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		expect(valueCircle).toHaveAttribute("stroke", "var(--color-accent)");
	});

	it("applies custom color to value circle", () => {
		render(<DonutGauge value={0.5} color="var(--color-market-up)" />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		expect(valueCircle).toHaveAttribute("stroke", "var(--color-market-up)");
	});

	/* ── SVG 数学验证 ── */

	it("computes correct stroke-width proportional to size (12%)", () => {
		render(<DonutGauge value={0.5} size={100} />);
		const svg = screen.getByRole("img");
		const circles = svg.querySelectorAll("circle");
		const expectedStrokeWidth = 100 * 0.12; // 12
		for (const circle of circles) {
			expect(circle).toHaveAttribute("stroke-width", String(expectedStrokeWidth));
		}
	});

	it("computes correct radius from size and stroke-width", () => {
		render(<DonutGauge value={0.5} size={100} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		const strokeWidth = 100 * 0.12; // 12
		const expectedRadius = (100 - strokeWidth) / 2; // 44
		const expectedCx = 100 / 2; // 50
		expect(valueCircle).toHaveAttribute("cx", String(expectedCx));
		expect(valueCircle).toHaveAttribute("cy", String(expectedCx));
		expect(valueCircle).toHaveAttribute("r", String(expectedRadius));
	});

	it("computes correct stroke-dasharray as circumference", () => {
		render(<DonutGauge value={0.5} size={100} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		const strokeWidth = 100 * 0.12;
		const radius = (100 - strokeWidth) / 2;
		const expectedCircumference = 2 * Math.PI * radius;
		expect(valueCircle).toHaveAttribute("stroke-dasharray", String(expectedCircumference));
	});

	it("computes correct stroke-dashoffset for value=0.5", () => {
		render(<DonutGauge value={0.5} size={100} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		const strokeWidth = 100 * 0.12;
		const radius = (100 - strokeWidth) / 2;
		const circumference = 2 * Math.PI * radius;
		const expectedOffset = circumference * (1 - 0.5);
		expect(valueCircle).toHaveAttribute("stroke-dashoffset", String(expectedOffset));
	});

	it("shows full ring when value=1", () => {
		render(<DonutGauge value={1} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		const offset = Number(valueCircle?.getAttribute("stroke-dashoffset"));
		expect(offset).toBe(0);
	});

	it("shows empty ring when value=0", () => {
		render(<DonutGauge value={0} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		const dashArray = Number(valueCircle?.getAttribute("stroke-dasharray"));
		const offset = Number(valueCircle?.getAttribute("stroke-dashoffset"));
		expect(offset).toBeCloseTo(dashArray, 5);
	});

	/* ── value 钳制 ── */

	it("clamps value above 1 to 1", () => {
		render(<DonutGauge value={1.5} />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("aria-label", "100%");
	});

	it("clamps negative value to 0", () => {
		render(<DonutGauge value={-0.5} />);
		const svg = screen.getByRole("img");
		expect(svg).toHaveAttribute("aria-label", "0%");
	});

	/* ── 中心文本 ── */

	it("shows percentage text in center when label is provided", () => {
		render(<DonutGauge value={0.75} label="Score" />);
		expect(screen.getByText("75%")).toBeInTheDocument();
	});

	it("does not show percentage text when label is omitted", () => {
		render(<DonutGauge value={0.75} />);
		expect(screen.queryByText("75%")).not.toBeInTheDocument();
	});

	it("uses font-data tabular-nums for percentage text", () => {
		render(<DonutGauge value={0.75} label="Score" />);
		const text = screen.getByText("75%");
		// SVG <text> className is SVGAnimatedString; use getAttribute instead
		const classStr = text.getAttribute("class") ?? "";
		expect(classStr).toContain("font-data");
		expect(classStr).toContain("tabular-nums");
	});

	/* ── value 圆环旋转方向 ── */

	it("rotates value circle to start from top (-90deg)", () => {
		render(<DonutGauge value={0.5} />);
		const svg = screen.getByRole("img");
		const valueCircle = svg.querySelectorAll("circle")[1];
		expect(valueCircle).toHaveAttribute("transform", "rotate(-90 32 32)");
	});
});
