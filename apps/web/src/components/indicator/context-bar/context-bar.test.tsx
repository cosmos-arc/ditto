import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ContextBar, ContextBarItem, ContextBarSep } from "./context-bar";

describe("ContextBar", () => {
	// ── Rendering ──

	it("renders with data-slot attribute", () => {
		const { container } = render(
			<ContextBar>
				<ContextBarItem label="Price" value="150.00" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "context-bar");
	});

	it("renders children inside the bar", () => {
		render(
			<ContextBar>
				<ContextBarItem label="Price" value="150.00" />
				<ContextBarItem label="Volume" value="2.4M" />
			</ContextBar>,
		);
		expect(screen.getByText("150.00")).toBeInTheDocument();
		expect(screen.getByText("2.4M")).toBeInTheDocument();
	});

	// ── Default variant (non-frosted) ──

	it("applies default variant classes when frosted is not set", () => {
		const { container } = render(
			<ContextBar>
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("bg-(--color-surface-strip)");
		expect(root.className).toContain("border-b");
		expect(root.className).toContain("border-(--color-border-subtle)");
	});

	it("does not apply frosted classes by default", () => {
		const { container } = render(
			<ContextBar>
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).not.toContain("backdrop-blur");
	});

	// ── Frosted variant ──

	it("applies frosted variant classes when frosted is true", () => {
		const { container } = render(
			<ContextBar frosted>
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("bg-(--color-surface-frosted)");
		expect(root.className).toContain("backdrop-blur-[var(--blur-frosted)]");
	});

	it("does not apply default border classes when frosted", () => {
		const { container } = render(
			<ContextBar frosted>
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).not.toContain("border-b");
	});

	// ── Layout classes ──

	it("applies flex layout classes", () => {
		const { container } = render(
			<ContextBar>
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("flex");
		expect(root.className).toContain("items-center");
		expect(root.className).toContain("gap-3");
	});

	it("applies height and padding from design tokens", () => {
		const { container } = render(
			<ContextBar>
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("h-[var(--height-context-bar)]");
		expect(root.className).toContain("px-[var(--spacing-4)]");
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(
			<ContextBar className="extra-class">
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.classList.contains("extra-class")).toBe(true);
	});

	// ── Extra props passthrough ──

	it("passes through extra HTML attributes", () => {
		const { container } = render(
			<ContextBar data-testid="my-bar" aria-label="Market context">
				<ContextBarItem label="Price" value="100" />
			</ContextBar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-testid", "my-bar");
		expect(root).toHaveAttribute("aria-label", "Market context");
	});
});

describe("ContextBarItem", () => {
	// ── Rendering ──

	it("renders label and value text", () => {
		render(<ContextBarItem label="PRICE" value="150.00" />);
		expect(screen.getByText("PRICE")).toBeInTheDocument();
		expect(screen.getByText("150.00")).toBeInTheDocument();
	});

	it("renders numeric value as string", () => {
		render(<ContextBarItem label="Volume" value={2400000} />);
		expect(screen.getByText("2400000")).toBeInTheDocument();
	});

	// ── Label styling ──

	it("applies label styling classes", () => {
		render(<ContextBarItem label="PRICE" value="100" />);
		const label = screen.getByText("PRICE");
		expect(label.className).toContain("text-xs");
		expect(label.className).toContain("uppercase");
		expect(label.className).toContain("text-(--color-foreground-tertiary)");
		expect(label.className).toContain("tracking-wide");
	});

	// ── Value styling ──

	it("applies default value styling", () => {
		render(<ContextBarItem label="Price" value="100" />);
		const value = screen.getByText("100");
		expect(value.className).toContain("text-sm");
		expect(value.className).toContain("font-medium");
		expect(value.className).toContain("text-(--color-foreground)");
	});

	// ── Color variants ──

	it("applies up color class", () => {
		render(<ContextBarItem label="Change" value="+2.5%" color="up" />);
		const value = screen.getByText("+2.5%");
		expect(value.className).toContain("text-(--color-market-up)");
	});

	it("applies down color class", () => {
		render(<ContextBarItem label="Change" value="-1.3%" color="down" />);
		const value = screen.getByText("-1.3%");
		expect(value.className).toContain("text-(--color-market-down)");
	});

	it("applies muted color class", () => {
		render(<ContextBarItem label="Status" value="--" color="muted" />);
		const value = screen.getByText("--");
		expect(value.className).toContain("text-(--color-foreground-tertiary)");
	});

	it("applies default color (foreground) when color is not specified", () => {
		render(<ContextBarItem label="Price" value="100" />);
		const value = screen.getByText("100");
		expect(value.className).toContain("text-(--color-foreground)");
	});

	it("applies default color when color=default", () => {
		render(<ContextBarItem label="Price" value="100" color="default" />);
		const value = screen.getByText("100");
		expect(value.className).toContain("text-(--color-foreground)");
	});

	// ── data-slot ──

	it("renders with data-slot attribute", () => {
		const { container } = render(
			<ContextBarItem label="Price" value="100" />,
		);
		const item = container.querySelector("[data-slot='context-bar-item']");
		expect(item).toBeInTheDocument();
	});

	// ── className merging ──

	it("merges custom className", () => {
		const { container } = render(
			<ContextBarItem label="Price" value="100" className="extra" />,
		);
		const item = container.querySelector("[data-slot='context-bar-item']");
		expect(item!.classList.contains("extra")).toBe(true);
	});
});

describe("ContextBarSep", () => {
	// ── Rendering ──

	it("renders a separator element", () => {
		const { container } = render(<ContextBarSep />);
		const sep = container.firstElementChild as HTMLElement;
		expect(sep).toBeInTheDocument();
	});

	it("applies separator styling classes", () => {
		const { container } = render(<ContextBarSep />);
		const sep = container.firstElementChild as HTMLElement;
		expect(sep.className).toContain("w-px");
		expect(sep.className).toContain("h-4");
		expect(sep.className).toContain("bg-(--color-border)");
	});

	it("renders as a span element", () => {
		const { container } = render(<ContextBarSep />);
		const sep = container.firstElementChild as HTMLElement;
		expect(sep.tagName).toBe("SPAN");
	});

	// ── aria-hidden ──

	it("has aria-hidden attribute for accessibility", () => {
		const { container } = render(<ContextBarSep />);
		const sep = container.firstElementChild as HTMLElement;
		expect(sep).toHaveAttribute("aria-hidden", "true");
	});
});

describe("ContextBar composition", () => {
	it("renders a full context bar with items and separators", () => {
		render(
			<ContextBar>
				<ContextBarItem label="LAST" value="4,215.50" />
				<ContextBarSep />
				<ContextBarItem label="CHG" value="+1.24%" color="up" />
				<ContextBarSep />
				<ContextBarItem label="VOL" value="12.8M" />
			</ContextBar>,
		);

		expect(screen.getByText("4,215.50")).toBeInTheDocument();
		expect(screen.getByText("+1.24%")).toBeInTheDocument();
		expect(screen.getByText("12.8M")).toBeInTheDocument();

		const value = screen.getByText("+1.24%");
		expect(value.className).toContain("text-(--color-market-up)");
	});
});
