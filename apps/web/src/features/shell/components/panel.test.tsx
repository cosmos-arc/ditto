import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Panel, PanelHeader, PanelBody } from "./panel";

describe("Panel", () => {
	it("renders with correct background, border, and border-radius", () => {
		const { container } = render(
			<Panel>
				<div>content</div>
			</Panel>,
		);
		const panel = container.firstChild as HTMLElement;
		expect(panel.className).toContain("bg-(--color-surface-panel-base)");
		expect(panel.className).toContain("border");
		expect(panel.className).toContain("border-(--color-border-subtle)");
		expect(panel.className).toContain("rounded-(--radius-md)");
	});

	it("applies flex-col layout", () => {
		const { container } = render(<Panel />);
		const panel = container.firstChild as HTMLElement;
		expect(panel.className).toContain("flex");
		expect(panel.className).toContain("flex-col");
	});

	it("accepts className prop for grid-area placement", () => {
		const { container } = render(<Panel className="col-span-2" />);
		const panel = container.firstChild as HTMLElement;
		expect(panel.className).toContain("col-span-2");
	});
});

describe("PanelHeader", () => {
	it("renders the title text with text-primary color (not tertiary)", () => {
		render(<PanelHeader title="Market Overview" />);
		const title = screen.getByText("Market Overview");
		expect(title).toBeInTheDocument();
		expect(title.className).toContain("text-(--color-foreground)");
		expect(title.className).not.toContain("uppercase");
	});

	it("renders subtitle when provided", () => {
		render(<PanelHeader title="Market Overview" subtitle="Real-time data" />);
		expect(screen.getByText("Real-time data")).toBeInTheDocument();
	});

	it("does not render subtitle when not provided", () => {
		const { container } = render(<PanelHeader title="Market Overview" />);
		expect(container.querySelector("[data-testid='panel-subtitle']")).toBeNull();
	});

	it("renders count badge when provided", () => {
		render(<PanelHeader title="Items" count={5} />);
		const count = screen.getByTestId("panel-count");
		expect(count).toBeInTheDocument();
		expect(count).toHaveTextContent("5");
	});

	it("renders actions slot when provided", () => {
		render(
			<PanelHeader
				title="Market Overview"
				actions={<button type="button">Settings</button>}
			/>,
		);
		expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument();
	});

	it("does not render actions when not provided", () => {
		const { container } = render(<PanelHeader title="Market Overview" />);
		expect(container.querySelector("[data-testid='panel-actions']")).toBeNull();
	});

	it("applies border-bottom separator", () => {
		const { container } = render(<PanelHeader title="Title" />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("border-b");
	});

	it("applies correct padding", () => {
		const { container } = render(<PanelHeader title="Title" />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("py-2");
		expect(header.className).toContain("px-3");
	});
});

describe("PanelBody", () => {
	it("renders children", () => {
		render(<PanelBody>Hello World</PanelBody>);
		expect(screen.getByText("Hello World")).toBeInTheDocument();
	});

	it("applies flex-1 and overflow styles", () => {
		const { container } = render(<PanelBody>content</PanelBody>);
		const body = container.firstChild as HTMLElement;
		expect(body.className).toContain("flex-1");
		expect(body.className).toContain("overflow-y-auto");
		expect(body.className).toContain("overflow-x-hidden");
	});
});
