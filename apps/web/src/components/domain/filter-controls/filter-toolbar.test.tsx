import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FilterToolbar } from "./filter-toolbar";

describe("FilterToolbar", () => {
	it("renders children content", () => {
		render(
			<FilterToolbar>
				<span>Filter Group</span>
			</FilterToolbar>,
		);
		expect(screen.getByText("Filter Group")).toBeInTheDocument();
	});

	it("renders multiple children", () => {
		render(
			<FilterToolbar>
				<span>Group 1</span>
				<span>Group 2</span>
			</FilterToolbar>,
		);
		expect(screen.getByText("Group 1")).toBeInTheDocument();
		expect(screen.getByText("Group 2")).toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		const { container } = render(
			<FilterToolbar>
				<span>Content</span>
			</FilterToolbar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root).toHaveAttribute("data-slot", "filter-toolbar");
	});

	it("applies flex layout", () => {
		const { container } = render(
			<FilterToolbar>
				<span>Content</span>
			</FilterToolbar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.className).toContain("flex");
		expect(root.className).toContain("items-center");
	});

	it("merges custom className", () => {
		const { container } = render(
			<FilterToolbar className="extra-class">
				<span>Content</span>
			</FilterToolbar>,
		);
		const root = container.firstElementChild as HTMLElement;
		expect(root.classList.contains("extra-class")).toBe(true);
	});
});
