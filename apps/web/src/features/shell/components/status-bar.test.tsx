import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StatusBar } from "./status-bar";

describe("StatusBar", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date("2025-06-15T14:32:00"));
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it("renders with data-slot='status-bar'", () => {
		const { container } = render(<StatusBar />);
		const bar = container.firstChild as HTMLElement;
		expect(bar.getAttribute("data-slot")).toBe("status-bar");
	});

	it("displays LIVE indicator with pulsing dot", () => {
		const { container } = render(<StatusBar />);
		expect(screen.getByText("LIVE")).toBeInTheDocument();

		// The pulsing dot is a span next to "LIVE" text
		const dot = container.querySelector('[class*="animate-[status-breathe"]');
		expect(dot).toBeInTheDocument();
		expect(dot?.className).toContain("rounded-full");
		expect(dot?.className).toContain("bg-(--color-status-led-healthy)");
	});

	it("displays connection status text", () => {
		render(<StatusBar />);
		expect(screen.getByText("已连接")).toBeInTheDocument();
	});

	it("displays latency text", () => {
		render(<StatusBar />);
		expect(screen.getByText("12ms")).toBeInTheDocument();
	});

	it("displays current time formatted as HH:MM", () => {
		render(<StatusBar />);
		expect(screen.getByText("14:32")).toBeInTheDocument();
	});

	it("displays shortcut hint", () => {
		render(<StatusBar />);
		expect(screen.getByText("⌘K 搜索")).toBeInTheDocument();
	});

	it("has correct layout classes", () => {
		const { container } = render(<StatusBar />);
		const bar = container.firstChild as HTMLElement;
		expect(bar.className).toContain("flex");
		expect(bar.className).toContain("items-center");
		expect(bar.className).toContain("h-[var(--height-status-bar)]");
	});

	it("can span the rail for prototypes whose status bar starts at the viewport edge", () => {
		const { container } = render(<StatusBar spanRail />);
		const bar = container.firstChild as HTMLElement;

		expect(bar.className).toContain("left-0");
		expect(bar.className).toContain("right-0");
		expect(bar.className).not.toContain("left-(--width-rail)");
	});

	it("can span the left rail while reserving a right rail boundary", () => {
		const { container } = render(<StatusBar reserveRightRail />);
		const bar = container.firstChild as HTMLElement;

		expect(bar.className).toContain("left-0");
		expect(bar.className).toContain("right-(--width-rail)");
	});

	it("has border-top with subtle color", () => {
		const { container } = render(<StatusBar />);
		const bar = container.firstChild as HTMLElement;
		expect(bar.className).toContain("border-t");
		expect(bar.className).toContain("border-(--color-border-subtle)");
	});

	it("uses small text size", () => {
		const { container } = render(<StatusBar />);
		const bar = container.firstChild as HTMLElement;
		expect(bar.className).toContain("text-xs");
	});

	it("has a spacer that pushes time and shortcut to the right", () => {
		const { container } = render(<StatusBar />);
		const spacer = container.querySelector('[class*="flex-1"]');
		expect(spacer).toBeInTheDocument();
	});
});
