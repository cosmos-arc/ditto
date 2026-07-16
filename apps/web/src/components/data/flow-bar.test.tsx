import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FlowBar } from "./flow-bar";

const CHART_COLORS = [
	"var(--color-chart-1)",
	"var(--color-chart-2)",
	"var(--color-chart-3)",
	"var(--color-chart-4)",
	"var(--color-chart-5)",
	"var(--color-chart-6)",
];

describe("FlowBar", () => {
	it("renders root element with data-slot=flow-bar", () => {
		render(<FlowBar segments={[{ value: 50 }, { value: 50 }]} />);
		const root = screen.getByTestId("flow-bar");
		expect(root).toHaveAttribute("data-slot", "flow-bar");
	});

	it("renders track with bg-(--color-border-subtle) and rounded-full", () => {
		render(<FlowBar segments={[{ value: 100 }]} />);
		const track = screen.getByTestId("flow-bar-track");
		expect(track).toHaveClass("rounded-full");
	});

	it("renders each segment as a child div inside the track", () => {
		render(
			<FlowBar
				segments={[
					{ value: 30, color: "#ff0000" },
					{ value: 70, color: "#00ff00" },
				]}
			/>,
		);
		const track = screen.getByTestId("flow-bar-track");
		const fills = track.querySelectorAll("[data-segment]");
		expect(fills).toHaveLength(2);
	});

	it("sets proportional width based on segment value", () => {
		render(
			<FlowBar
				segments={[
					{ value: 30, color: "#ff0000" },
					{ value: 70, color: "#00ff00" },
				]}
			/>,
		);
		const track = screen.getByTestId("flow-bar-track");
		const fills = track.querySelectorAll("[data-segment]");
		// 30/(30+70) = 30%, 70/(30+70) = 70%
		expect(fills[0]).toHaveStyle({ width: "30%" });
		expect(fills[1]).toHaveStyle({ width: "70%" });
	});

	it("applies last segment rounded-full, others without", () => {
		render(
			<FlowBar
				segments={[
					{ value: 30, color: "#ff0000" },
					{ value: 40, color: "#00ff00" },
					{ value: 30, color: "#0000ff" },
				]}
			/>,
		);
		const track = screen.getByTestId("flow-bar-track");
		const fills = track.querySelectorAll("[data-segment]");
		// Non-last segments: no rounded-full (they are flat)
		expect(fills[0]).not.toHaveClass("rounded-full");
		expect(fills[1]).not.toHaveClass("rounded-full");
		// Last segment: rounded-full
		expect(fills[2]).toHaveClass("rounded-full");
	});

	it("applies custom color when provided", () => {
		render(<FlowBar segments={[{ value: 100, color: "#ff0000" }]} />);
		const track = screen.getByTestId("flow-bar-track");
		const fill = track.querySelector("[data-segment]");
		expect(fill).toHaveStyle({ backgroundColor: "#ff0000" });
	});

	it("cycles through chart palette when no color specified", () => {
		render(<FlowBar segments={[{ value: 25 }, { value: 25 }, { value: 25 }]} />);
		const track = screen.getByTestId("flow-bar-track");
		const fills = track.querySelectorAll("[data-segment]");
		expect(fills[0]).toHaveStyle({ backgroundColor: CHART_COLORS[0] });
		expect(fills[1]).toHaveStyle({ backgroundColor: CHART_COLORS[1] });
		expect(fills[2]).toHaveStyle({ backgroundColor: CHART_COLORS[2] });
	});

	it("uses default height of 6px", () => {
		render(<FlowBar segments={[{ value: 100 }]} />);
		const track = screen.getByTestId("flow-bar-track");
		expect(track).toHaveStyle({ height: "6px" });
	});

	it("applies custom height", () => {
		render(<FlowBar segments={[{ value: 100 }]} height={10} />);
		const track = screen.getByTestId("flow-bar-track");
		expect(track).toHaveStyle({ height: "10px" });
	});

	it("applies className to root element", () => {
		render(<FlowBar segments={[{ value: 100 }]} className="my-custom-class" />);
		const root = screen.getByTestId("flow-bar");
		expect(root).toHaveClass("my-custom-class");
	});

	it("applies trackClassName to track element", () => {
		render(<FlowBar segments={[{ value: 100 }]} trackClassName="custom-track" />);
		const track = screen.getByTestId("flow-bar-track");
		expect(track).toHaveClass("custom-track");
	});

	it("renders nothing when segments array is empty", () => {
		const { container } = render(<FlowBar segments={[]} />);
		expect(container.innerHTML).toBe("");
	});

	it("renders single segment at full width", () => {
		render(<FlowBar segments={[{ value: 42 }]} />);
		const track = screen.getByTestId("flow-bar-track");
		const fill = track.querySelector("[data-segment]");
		expect(fill).toHaveStyle({ width: "100%" });
	});

	it("handles single segment with rounded-full", () => {
		render(<FlowBar segments={[{ value: 42 }]} />);
		const track = screen.getByTestId("flow-bar-track");
		const fill = track.querySelector("[data-segment]");
		expect(fill).toHaveClass("rounded-full");
	});

	it("sets aria-label from segment label when provided", () => {
		render(
			<FlowBar
				segments={[
					{ value: 50, label: "Inflow" },
					{ value: 50, label: "Outflow" },
				]}
			/>,
		);
		const track = screen.getByTestId("flow-bar-track");
		const fills = track.querySelectorAll("[data-segment]");
		expect(fills[0]).toHaveAttribute("aria-label", "Inflow");
		expect(fills[1]).toHaveAttribute("aria-label", "Outflow");
	});

	it("wraps chart palette colors when segments exceed palette length", () => {
		const segments = Array.from({ length: 8 }, () => ({
			value: 10,
		}));
		render(<FlowBar segments={segments} />);
		const track = screen.getByTestId("flow-bar-track");
		const fills = track.querySelectorAll("[data-segment]");
		// Index 6 should wrap back to CHART_COLORS[0]
		expect(fills[6]).toHaveStyle({ backgroundColor: CHART_COLORS[0] });
		// Index 7 should wrap back to CHART_COLORS[1]
		expect(fills[7]).toHaveStyle({ backgroundColor: CHART_COLORS[1] });
	});

	it("track has overflow-hidden", () => {
		render(<FlowBar segments={[{ value: 100 }]} />);
		const track = screen.getByTestId("flow-bar-track");
		expect(track).toHaveClass("overflow-hidden");
	});
});
