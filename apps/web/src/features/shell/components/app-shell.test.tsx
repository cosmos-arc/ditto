import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./app-shell";

// Mock TanStack Router hooks used by child components (Rail, ShellHeader)
const mockUseLocation = vi.fn().mockReturnValue({ pathname: "/" });
const mockUseMatches = vi.fn().mockReturnValue([]);

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useLocation: () => mockUseLocation(),
		useMatches: () => mockUseMatches(),
		Link: ({ children, to, ...props }: { children: React.ReactNode; to: string; [key: string]: unknown }) => (
			<a href={to} data-testid={`link-${to}`} {...props}>
				{children}
			</a>
		),
	};
});

describe("AppShell", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders with h-screen w-screen", () => {
		const { container } = render(<AppShell>content</AppShell>);
		const shell = container.firstChild as HTMLElement;
		expect(shell.className).toContain("h-screen");
		expect(shell.className).toContain("w-screen");
	});

	it("contains Rail component (nav with aria-label='主导航')", () => {
		render(<AppShell>content</AppShell>);
		expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
	});

	it("contains header element", () => {
		render(<AppShell>content</AppShell>);
		expect(screen.getByRole("banner")).toBeInTheDocument();
	});

	it("contains NoiseLayer (aria-hidden overlay)", () => {
		const { container } = render(<AppShell>content</AppShell>);
		const noiseOverlay = container.querySelector('[aria-hidden="true"][class*="pointer-events-none"]');
		expect(noiseOverlay).toBeInTheDocument();
	});

	it("renders children in the content area", () => {
		render(<AppShell>Page Content</AppShell>);
		expect(screen.getByText("Page Content")).toBeInTheDocument();
	});

	it("has grid layout classes with correct template columns and rows", () => {
		const { container } = render(<AppShell>content</AppShell>);
		const shell = container.firstChild as HTMLElement;
		expect(shell.className).toContain("grid");
		expect(shell.className).toContain("grid-cols-[var(--width-rail)_1fr]");
		expect(shell.className).toContain("grid-rows-[var(--height-header)_1fr]");
	});

	it("has overflow-hidden to prevent scrolling on the shell", () => {
		const { container } = render(<AppShell>content</AppShell>);
		const shell = container.firstChild as HTMLElement;
		expect(shell.className).toContain("overflow-hidden");
	});

	it("places children in a content area with min-h-0 and overflow-hidden", () => {
		const { container } = render(<AppShell>content</AppShell>);
		// The content wrapper should have min-h-0 and overflow-hidden
		const contentArea = container.querySelector('[class*="min-h-0"]');
		expect(contentArea).toBeInTheDocument();
		expect(contentArea?.className).toContain("overflow-hidden");
	});

	it("has relative positioning for the shell container", () => {
		const { container } = render(<AppShell>content</AppShell>);
		const shell = container.firstChild as HTMLElement;
		expect(shell.className).toContain("relative");
	});

	it("does not reserve a global status row by default", () => {
		const { container } = render(<AppShell>content</AppShell>);
		const shell = container.firstElementChild;
		expect(shell?.className).toContain("grid-rows-[var(--height-header)_1fr]");
		expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
	});

	it("maps research strategy routes to the research domain", () => {
		mockUseLocation.mockReturnValue({ pathname: "/research/strategies/strat-001" });
		render(<AppShell>content</AppShell>);

		expect(document.documentElement).toHaveAttribute("data-domain", "research");
	});
});
