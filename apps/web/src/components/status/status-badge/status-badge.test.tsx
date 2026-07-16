import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./status-badge";

const STATUS_VARIANTS = [
	"default",
	"healthy",
	"degraded",
	"warning",
	"critical",
	"live",
	"idle",
	"error",
	"trade",
	"risk",
	"research",
	"platform",
	"data",
	"priority",
	"regime-on",
	"regime-off",
	"regime-mixed",
	"active",
	"inactive",
] as const;

/** Helper: get the StatusDot element inside a rendered badge */
function getDot(container: HTMLElement): Element | null {
	return container.querySelector('[data-slot="status-dot"]');
}

describe("StatusBadge", () => {
	// ── Rendering ──

	it("renders a badge with dot and label", () => {
		render(<StatusBadge label="Healthy" variant="healthy" />);
		const badge = screen.getByText("Healthy").closest("[data-slot]");
		expect(badge).toBeTruthy();
		expect(badge?.tagName).toBe("SPAN");
	});

	it("renders with default size md", () => {
		const { container } = render(<StatusBadge label="Test" variant="healthy" />);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge).toHaveAttribute("data-size", "md");
	});

	it("renders a StatusDot inside the badge", () => {
		const { container } = render(<StatusBadge label="Live" variant="live" />);
		const dot = getDot(container);
		expect(dot).toBeTruthy();
	});

	// ── Size variants ──

	it.each([["sm"], ["md"]] as const)(
		"applies correct data-size for size=%s",
		(size) => {
			const { container } = render(
				<StatusBadge label="Test" variant="healthy" size={size} />,
			);
			const badge = container.firstElementChild as HTMLElement;
			expect(badge).toHaveAttribute("data-size", size);
		},
	);

	it("applies text-xs class for size=sm", () => {
		const { container } = render(
			<StatusBadge label="Test" variant="healthy" size="sm" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge.className).toContain("text-xs");
	});

	it("applies text-sm class for size=md", () => {
		const { container } = render(
			<StatusBadge label="Test" variant="healthy" size="md" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge.className).toContain("text-sm");
	});

	// ── Variant data-attribute ──

	it.each(STATUS_VARIANTS)(
		"applies data-variant for variant=%s",
		(variant) => {
			const { container } = render(
				<StatusBadge label="Label" variant={variant} />,
			);
			const badge = container.firstElementChild as HTMLElement;
			expect(badge).toHaveAttribute("data-variant", variant);
		},
	);

	// ── Dot variant passthrough ──

	it.each([
		["healthy", "healthy"],
		["degraded", "degraded"],
		["warning", "warning"],
		["critical", "critical"],
		["live", "live"],
		["idle", "idle"],
		["error", "error"],
		["trade", "live"],
		["risk", "critical"],
		["research", "info"],
		["platform", "idle"],
		["data", "degraded"],
		["priority", "error"],
		["regime-on", "healthy"],
		["regime-off", "idle"],
		["regime-mixed", "warning"],
		["active", "live"],
		["inactive", "idle"],
	] as const)(
		"maps badge variant=%s to dot variant=%s",
		(badgeVariant, expectedDotVariant) => {
			const { container } = render(
				<StatusBadge label="Label" variant={badgeVariant} />,
			);
			const dot = getDot(container);
			expect(dot).toHaveAttribute("data-variant", expectedDotVariant);
		},
	);

	// ── Default variant ──

	it("uses healthy as default variant for dot", () => {
		const { container } = render(<StatusBadge label="Default" />);
		const dot = getDot(container);
		expect(dot).toHaveAttribute("data-variant", "healthy");
	});

	// ── Background color ──

	it("applies background color class with 8% opacity", () => {
		const { container } = render(
			<StatusBadge label="Test" variant="healthy" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge.className).toContain("bg-(--color-status-led-healthy)/8");
	});

	it("applies business token background for trade variant", () => {
		const { container } = render(
			<StatusBadge label="Trade" variant="trade" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge.className).toContain("bg-(--color-execution-filled)/8");
	});

	// ── Layout ──

	it("renders dot and label in a horizontal row", () => {
		const { container } = render(
			<StatusBadge label="Label" variant="healthy" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge.className).toContain("inline-flex");
		expect(badge.className).toContain("items-center");
		expect(badge.className).toContain("gap-1.5");
	});

	// ── Data attributes ──

	it("renders with data-slot attribute", () => {
		const { container } = render(
			<StatusBadge label="Test" variant="healthy" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge).toHaveAttribute("data-slot", "status-badge");
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(
			<StatusBadge label="Test" variant="healthy" className="extra-class" />,
		);
		const badge = container.firstElementChild as HTMLElement;
		expect(badge.classList.contains("extra-class")).toBe(true);
	});

	// ── Dot size passthrough ──

	it("passes sm size to dot when badge is sm", () => {
		const { container } = render(
			<StatusBadge label="Small" variant="healthy" size="sm" />,
		);
		const dot = getDot(container);
		expect(dot).toHaveAttribute("data-size", "sm");
	});

	it("passes md size to dot when badge is md", () => {
		const { container } = render(
			<StatusBadge label="Medium" variant="healthy" size="md" />,
		);
		const dot = getDot(container);
		expect(dot).toHaveAttribute("data-size", "md");
	});
});
