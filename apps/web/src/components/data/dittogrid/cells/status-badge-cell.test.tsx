import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadgeCell } from "./status-badge-cell";

describe("StatusBadgeCell", () => {
	it("renders a StatusBadge with given label", () => {
		render(<StatusBadgeCell label="Healthy" variant="healthy" />);
		expect(screen.getByText("Healthy")).toBeInTheDocument();
	});

	it("passes variant to StatusBadge", () => {
		render(<StatusBadgeCell label="Warning" variant="warning" />);
		const badge = screen.getByText("Warning").closest("[data-slot]");
		expect(badge).toHaveAttribute("data-variant", "warning");
	});

	it("has data-slot attribute on wrapper", () => {
		render(<StatusBadgeCell label="Active" variant="active" />);
		const wrapper = screen.getByTestId("status-badge-cell-root");
		expect(wrapper).toHaveAttribute("data-slot", "status-badge-cell");
	});
});
