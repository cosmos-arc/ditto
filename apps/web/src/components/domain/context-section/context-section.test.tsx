import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ContextSection } from "./context-section";

describe("ContextSection", () => {
	// ── Rendering ──

	it("renders title", () => {
		render(<ContextSection title="GLOBAL ALERTS">Content</ContextSection>);
		expect(screen.getByText("GLOBAL ALERTS")).toBeInTheDocument();
	});

	it("renders children when defaultOpen=true", () => {
		render(<ContextSection title="Section">Body Content</ContextSection>);
		expect(screen.getByText("Body Content")).toBeInTheDocument();
	});

	it("hides children when defaultOpen=false", () => {
		render(
			<ContextSection title="Section" defaultOpen={false}>
				Hidden
			</ContextSection>,
		);
		expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
	});

	it("renders with data-slot attribute", () => {
		render(<ContextSection title="Test">Content</ContextSection>);
		expect(document.querySelector("[data-slot='context-section']")).toBeInTheDocument();
	});

	// ── Count & Action ──

	it("renders count when provided", () => {
		render(
			<ContextSection title="Alerts" count={5}>
				Content
			</ContextSection>,
		);
		expect(screen.getByText("5")).toBeInTheDocument();
	});

	it("renders action element", () => {
		render(
			<ContextSection title="Alerts" action={<button>View All</button>}>
				Content
			</ContextSection>,
		);
		expect(screen.getByText("View All")).toBeInTheDocument();
	});

	// ── Toggle behavior ──

	it("toggles body visibility on header click", async () => {
		const user = userEvent.setup();
		render(<ContextSection title="Section">Toggle Content</ContextSection>);
		expect(screen.getByText("Toggle Content")).toBeInTheDocument();

		const header = screen.getByRole("button");
		await user.click(header);
		expect(screen.queryByText("Toggle Content")).not.toBeInTheDocument();

		await user.click(header);
		expect(screen.getByText("Toggle Content")).toBeInTheDocument();
	});

	// ── Structure ──

	it("renders header as clickable button", () => {
		render(<ContextSection title="Test">Content</ContextSection>);
		expect(screen.getByRole("button")).toBeInTheDocument();
	});

	it("renders body section", () => {
		render(<ContextSection title="Test">Content</ContextSection>);
		const body = document.querySelector("[data-slot='context-section-body']") as HTMLElement;
		expect(body).toBeInTheDocument();
	});

	// ── className merging ──

	it("merges custom className", () => {
		render(
			<ContextSection title="Test" className="extra-class">
				Content
			</ContextSection>,
		);
		const section = document.querySelector("[data-slot='context-section']") as HTMLElement;
		expect(section.classList.contains("extra-class")).toBe(true);
	});
});
