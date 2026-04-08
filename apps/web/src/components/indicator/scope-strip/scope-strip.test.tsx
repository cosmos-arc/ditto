import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScopeStrip } from "./scope-strip";

describe("ScopeStrip", () => {
	// ── Rendering ──

	it("renders children content", () => {
		render(<ScopeStrip>Content</ScopeStrip>);
		expect(screen.getByText("Content")).toBeInTheDocument();
	});

	it("renders multiple children", () => {
		render(
			<ScopeStrip>
				<span>Item 1</span>
				<span>Item 2</span>
				<span>Item 3</span>
			</ScopeStrip>,
		);
		expect(screen.getByText("Item 1")).toBeInTheDocument();
		expect(screen.getByText("Item 2")).toBeInTheDocument();
		expect(screen.getByText("Item 3")).toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		const { container } = render(<ScopeStrip>Content</ScopeStrip>);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "scope-strip");
	});

	// ── Accessibility ──

	it("applies role=status by default", () => {
		render(<ScopeStrip>Content</ScopeStrip>);
		const root = screen.getByRole("status");
		expect(root).toBeInTheDocument();
	});

	it("accepts custom role", () => {
		render(<ScopeStrip role="toolbar">Content</ScopeStrip>);
		expect(screen.getByRole("toolbar")).toBeInTheDocument();
	});

	it("applies aria-label when provided", () => {
		render(<ScopeStrip aria-label="交易会话状态">Content</ScopeStrip>);
		const root = screen.getByRole("status");
		expect(root).toHaveAttribute("aria-label", "交易会话状态");
	});

	// ── Layout ──

	it("applies flex layout", () => {
		const { container } = render(<ScopeStrip>Content</ScopeStrip>);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("flex");
		expect(root.className).toContain("items-center");
	});

	it("applies horizontal overflow for scrolling", () => {
		const { container } = render(<ScopeStrip>Content</ScopeStrip>);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("overflow-x-auto");
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(
			<ScopeStrip className="extra-class">Content</ScopeStrip>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.classList.contains("extra-class")).toBe(true);
	});
});
