import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { StatusDot } from "./status-dot";

const VARIANTS = [
	"healthy",
	"degraded",
	"warning",
	"critical",
	"live",
	"idle",
	"error",
	"info",
] as const;

describe("StatusDot", () => {
	// ── Rendering ──

	it("renders a round dot element", () => {
		const { container } = render(<StatusDot />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot.tagName).toBe("SPAN");
		expect(dot.classList.contains("rounded-full")).toBe(true);
	});

	it("renders with default size md (6px)", () => {
		const { container } = render(<StatusDot />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot).toHaveAttribute("data-size", "md");
	});

	// ── Size variants ──

	it.each([
		["sm", "6px"],
		["md", "6px"],
		["lg", "10px"],
	] as const)("applies correct size for size=%s", (size, expectedWidth) => {
		const { container } = render(<StatusDot size={size} />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot).toHaveAttribute("data-size", size);
		expect(dot.classList.contains(`w-[${expectedWidth}]`)).toBe(true);
		expect(dot.classList.contains(`h-[${expectedWidth}]`)).toBe(true);
	});

	// ── Status variants ──

	it.each(VARIANTS)("applies data-variant for variant=%s", (variant) => {
		const { container } = render(<StatusDot variant={variant} />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot).toHaveAttribute("data-variant", variant);
	});

	it.each(VARIANTS)(
		"maps variant=%s to correct CSS variable color",
		(variant) => {
			const { container } = render(<StatusDot variant={variant} />);
			const dot = container.firstElementChild as HTMLElement;
			expect(dot.style.backgroundColor).toBe("");
			// Color should come from CSS variable via class, not inline style
			const className = dot.className;
			expect(className).toContain("bg-(--color-status-led-" + variant + ")");
		},
	);

	// ── Pulse animation ──

	it("applies pulse animation when variant=live and pulse=true", () => {
		const { container } = render(<StatusDot variant="live" pulse />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot.classList.contains("animate-[dot-pulse_3s_ease-in-out_infinite]")).toBe(true);
	});

	it("does not apply pulse animation when variant=live and pulse=false", () => {
		const { container } = render(<StatusDot variant="live" pulse={false} />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot.className).not.toContain("animate-");
	});

	it("does not apply pulse animation for non-live variant with pulse=true", () => {
		const { container } = render(<StatusDot variant="healthy" pulse />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot.className).not.toContain("animate-");
	});

	it("does not apply pulse animation for non-live variant with pulse not set", () => {
		const { container } = render(<StatusDot variant="error" />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot.className).not.toContain("animate-");
	});

	// ── Data attributes ──

	it("renders with data-slot attribute", () => {
		const { container } = render(<StatusDot />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot).toHaveAttribute("data-slot", "status-dot");
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(<StatusDot className="extra-class" />);
		const dot = container.firstElementChild as HTMLElement;
		expect(dot.classList.contains("extra-class")).toBe(true);
	});
});
