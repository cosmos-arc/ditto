import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceBar } from "./confidence-bar";

const COLOR_CLASSES: Record<string, string> = {
	brand: "bg-(--color-brand-accent)",
	success: "bg-(--color-status-led-healthy)",
	warning: "bg-(--color-status-led-warning)",
	danger: "bg-(--color-status-led-critical)",
	neutral: "bg-(--color-foreground-secondary)",
};

describe("ConfidenceBar", () => {
	// ── Rendering ──

	it("renders track and fill elements", () => {
		render(<ConfidenceBar value={72} />);
		const track = screen.getByTestId("confidence-track");
		expect(track).toBeInTheDocument();
		expect(track).toHaveAttribute("data-slot", "confidence-track");
	});

	it("renders with data-slot attribute", () => {
		const { container } = render(<ConfidenceBar value={50} />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "confidence-bar");
	});

	it("renders data-size attribute with default md", () => {
		const { container } = render(<ConfidenceBar value={50} />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-size", "md");
	});

	// ── Single value mode ──

	it("sets fill width to value percentage", () => {
		render(<ConfidenceBar value={72} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill).toHaveStyle({ width: "72%" });
	});

	it("sets fill width relative to max prop", () => {
		render(<ConfidenceBar value={36} max={50} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill).toHaveStyle({ width: "72%" });
	});

	it("renders fill with 0% width when value is 0", () => {
		render(<ConfidenceBar value={0} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill).toHaveStyle({ width: "0%" });
	});

	it("clamps fill width to 100% when value exceeds max", () => {
		render(<ConfidenceBar value={150} max={100} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill).toHaveStyle({ width: "100%" });
	});

	// ── Color variants ──

	it.each([
		"brand",
		"success",
		"warning",
		"danger",
		"neutral",
	] as const)("applies correct color class for color=%s", (color) => {
		render(<ConfidenceBar value={50} color={color} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill.className).toContain(COLOR_CLASSES[color]);
	});

	it("applies neutral color by default", () => {
		render(<ConfidenceBar value={50} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill.className).toContain(COLOR_CLASSES.neutral);
	});

	// ── Size variants ──

	it("applies data-size sm for size=sm", () => {
		const { container } = render(<ConfidenceBar value={50} size="sm" />);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-size", "sm");
	});

	it("applies track height h-1 for size=sm", () => {
		render(<ConfidenceBar value={50} size="sm" />);
		const track = screen.getByTestId("confidence-track");
		expect(track.className).toContain("h-1");
	});

	it("applies track height h-1.5 for size=md", () => {
		render(<ConfidenceBar value={50} size="md" />);
		const track = screen.getByTestId("confidence-track");
		expect(track.className).toContain("h-1.5");
	});

	// ── Label display ──

	it("does not show label by default", () => {
		render(<ConfidenceBar value={72} />);
		expect(screen.queryByText("72%")).not.toBeInTheDocument();
	});

	it("shows percentage label when showLabel=true", () => {
		render(<ConfidenceBar value={72} showLabel />);
		expect(screen.getByText("72%")).toBeInTheDocument();
	});

	// ── Segmented mode ──

	it("renders multiple fill segments when segments are provided", () => {
		render(
			<ConfidenceBar
				value={100}
				segments={[
					{ value: 40, color: "success" },
					{ value: 35, color: "warning" },
					{ value: 25, color: "danger" },
				]}
			/>,
		);
		const segments = screen.getAllByTestId("confidence-segment");
		expect(segments).toHaveLength(3);
	});

	it("sets each segment width proportional to its value", () => {
		render(
			<ConfidenceBar
				value={100}
				segments={[
					{ value: 40, color: "success" },
					{ value: 60, color: "warning" },
				]}
			/>,
		);
		const segments = screen.getAllByTestId("confidence-segment");
		expect(segments[0]).toHaveStyle({ width: "40%" });
		expect(segments[1]).toHaveStyle({ width: "60%" });
	});

	it("applies correct color class to each segment", () => {
		render(
			<ConfidenceBar
				value={100}
				segments={[
					{ value: 50, color: "success" },
					{ value: 50, color: "danger" },
				]}
			/>,
		);
		const segments = screen.getAllByTestId("confidence-segment");
		expect(segments[0].className).toContain(COLOR_CLASSES.success);
		expect(segments[1].className).toContain(COLOR_CLASSES.danger);
	});

	it("does not render single fill in segmented mode", () => {
		render(<ConfidenceBar value={100} segments={[{ value: 100, color: "brand" }]} />);
		expect(screen.queryByTestId("confidence-fill")).not.toBeInTheDocument();
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(<ConfidenceBar value={50} className="extra-class" />);
		const root = container.firstElementChild as HTMLElement;
		expect(root.classList.contains("extra-class")).toBe(true);
	});

	// ── Transition ──

	it("applies transition to fill element", () => {
		render(<ConfidenceBar value={50} />);
		const fill = screen.getByTestId("confidence-fill");
		expect(fill.className).toContain("transition-");
	});
});
