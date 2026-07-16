import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FilterChip } from "./filter-chip";

describe("FilterChip", () => {
	// ── Rendering ──

	it("renders label", () => {
		render(<FilterChip label="全部" />);
		expect(screen.getByText("全部")).toBeInTheDocument();
	});

	it("renders as button element", () => {
		render(<FilterChip label="Test" />);
		expect(screen.getByRole("button")).toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		render(<FilterChip label="Test" />);
		expect(screen.getByRole("button")).toHaveAttribute("data-slot", "filter-chip");
	});

	// ── Active state ──

	it("applies active styles when active=true", () => {
		render(<FilterChip label="Test" active />);
		const btn = screen.getByRole("button");
		expect(btn).toHaveAttribute("data-active", "true");
	});

	it("does not apply active styles by default", () => {
		render(<FilterChip label="Test" />);
		const btn = screen.getByRole("button");
		expect(btn).toHaveAttribute("data-active", "false");
	});

	it("calls onClick when clicked", async () => {
		const user = userEvent.setup();
		const onClick = vi.fn();
		render(<FilterChip label="Test" onClick={onClick} />);
		await user.click(screen.getByRole("button"));
		expect(onClick).toHaveBeenCalledTimes(1);
	});

	// ── Count ──

	it("renders count badge when count is provided", () => {
		render(<FilterChip label="Signals" count={12} />);
		expect(screen.getByText("12")).toBeInTheDocument();
	});

	it("does not render count badge when count is not provided", () => {
		render(<FilterChip label="Signals" />);
		expect(screen.queryByText("12")).not.toBeInTheDocument();
	});

	// ── className merging ──

	it("merges custom className", () => {
		render(<FilterChip label="Test" className="extra-class" />);
		expect(screen.getByRole("button").classList.contains("extra-class")).toBe(true);
	});
});
