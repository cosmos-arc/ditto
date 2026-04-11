import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { Rail } from "./rail";

// Mock TanStack Router's useLocation
const mockUseLocation = vi.fn().mockReturnValue({ pathname: "/" });
vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>(
		"@tanstack/react-router",
	);
	return {
		...actual,
		useLocation: () => mockUseLocation(),
		Link: ({
			children,
			to,
			...props
		}: {
			children: React.ReactNode;
			to: string;
			[key: string]: unknown;
		}) => (
			<a href={to} data-testid={`link-${to}`} {...props}>
				{children}
			</a>
		),
	};
});

describe("Rail", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders the rail container with correct width class", () => {
		const { container } = render(<Rail />);
		const rail = container.firstChild as HTMLElement;
		expect(rail.className).toContain("w-(--width-rail)");
	});

	it("renders the logo 'D' at the top", () => {
		render(<Rail />);
		expect(screen.getByText("D")).toBeInTheDocument();
	});

	it("renders navigation links for all 6 domains", () => {
		render(<Rail />);
		// Each domain has a Link with aria-label
		expect(screen.getByLabelText("首页")).toBeInTheDocument();
		expect(screen.getByLabelText("市场")).toBeInTheDocument();
		expect(screen.getByLabelText("研究")).toBeInTheDocument();
		expect(screen.getByLabelText("交易")).toBeInTheDocument();
		expect(screen.getByLabelText("AI")).toBeInTheDocument();
		expect(screen.getByLabelText("平台")).toBeInTheDocument();
	});

	it("marks home as active when pathname is /", () => {
		mockUseLocation.mockReturnValue({ pathname: "/" });
		render(<Rail />);
		const homeLink = screen.getByLabelText("首页").closest("a");
		expect(homeLink?.className).toContain("bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)]");
	});

	it("marks markets as active when pathname starts with /markets", () => {
		mockUseLocation.mockReturnValue({ pathname: "/markets" });
		render(<Rail />);
		const marketsLink = screen.getByLabelText("市场").closest("a");
		expect(marketsLink?.className).toContain("bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)]");
	});

	it("marks trading as active when pathname starts with /trading/something", () => {
		mockUseLocation.mockReturnValue({ pathname: "/trading/orders" });
		render(<Rail />);
		const tradingLink = screen.getByLabelText("交易").closest("a");
		expect(tradingLink?.className).toContain("bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)]");
	});

	it("does not mark other domains active when on /research", () => {
		mockUseLocation.mockReturnValue({ pathname: "/research" });
		render(<Rail />);
		const homeLink = screen.getByLabelText("首页").closest("a");
		const marketsLink = screen.getByLabelText("市场").closest("a");
		expect(homeLink?.className).not.toContain("bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)]");
		expect(marketsLink?.className).not.toContain("bg-[color-mix(in_oklch,var(--color-accent)_10%,transparent)]");
	});

	it("renders placeholder icons at the bottom (settings and user)", () => {
		render(<Rail />);
		expect(screen.getByLabelText("设置")).toBeInTheDocument();
		expect(screen.getByLabelText("用户")).toBeInTheDocument();
	});

	it("renders links with correct href paths", () => {
		render(<Rail />);
		expect(screen.getByTestId("link-/")).toBeInTheDocument();
		expect(screen.getByTestId("link-/markets")).toBeInTheDocument();
		expect(screen.getByTestId("link-/research")).toBeInTheDocument();
		expect(screen.getByTestId("link-/trading")).toBeInTheDocument();
		expect(screen.getByTestId("link-/ai")).toBeInTheDocument();
		expect(screen.getByTestId("link-/platform")).toBeInTheDocument();
	});

	it("applies background and border styles", () => {
		const { container } = render(<Rail />);
		const rail = container.firstChild as HTMLElement;
		expect(rail.className).toContain("bg-(--color-surface-app)");
		expect(rail.className).toContain("border-r");
	});
});
