import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { StaleIndicator } from "./stale-indicator";

describe("StaleIndicator", () => {
	// -- Rendering --

	it("renders a bar element", () => {
		const { container } = render(<StaleIndicator isStale />);
		const bar = container.querySelector("[data-testid='stale-indicator']");
		expect(bar).toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		const { container } = render(<StaleIndicator isStale />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar).toHaveAttribute("data-slot", "stale-indicator");
	});

	// -- Visibility states --

	it("applies transition classes for smooth appearance/disappearance", () => {
		const { container } = render(<StaleIndicator isStale />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar.className).toContain("transition-all");
	});

	it("renders visible when isStale is true", () => {
		const { container } = render(<StaleIndicator isStale />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar.className).toContain("h-[2px]");
		expect(bar.className).toContain("opacity-100");
	});

	it("renders hidden when isStale is false", () => {
		const { container } = render(<StaleIndicator isStale={false} />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar.className).toContain("h-0");
		expect(bar.className).toContain("opacity-0");
	});

	// -- Gradient bar styling --

	it("applies accent color gradient background", () => {
		const { container } = render(<StaleIndicator isStale />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar.className).toContain("bg-(--color-accent)");
	});

	it("has full width", () => {
		const { container } = render(<StaleIndicator isStale />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar.className).toContain("w-full");
	});

	// -- className merging --

	it("merges custom className", () => {
		const { container } = render(<StaleIndicator isStale className="extra-class" />);
		const bar = container.querySelector("[data-testid='stale-indicator']") as HTMLElement;
		expect(bar).toHaveClass("extra-class");
	});
});
