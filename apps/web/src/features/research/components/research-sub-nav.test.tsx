import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchSubNav } from "./research-sub-nav";

// Mock TanStack Router's useLocation + Link (mirrors rail.test.tsx)
const mockUseLocation = vi.fn().mockReturnValue({ pathname: "/research" });
vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useLocation: () => mockUseLocation(),
		Link: ({ children, to, ...props }: { children: React.ReactNode; to: string; [key: string]: unknown }) => (
			<a href={to} data-testid={`link-${to}`} {...props}>
				{children}
			</a>
		),
	};
});

const SECTION_LABELS = ["总览", "因子", "策略", "实验", "审查", "回测", "Regime", "股票池"] as const;

describe("ResearchSubNav", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders the 8 main research section entries", () => {
		render(<ResearchSubNav />);
		for (const label of SECTION_LABELS) {
			expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
		}
	});

	it("does not render the node-descriptors placeholder entry", () => {
		render(<ResearchSubNav />);
		expect(screen.queryByRole("link", { name: "节点描述符" })).not.toBeInTheDocument();
	});

	it("marks overview active on exact /research match", () => {
		mockUseLocation.mockReturnValue({ pathname: "/research" });
		render(<ResearchSubNav />);
		expect(screen.getByRole("link", { name: "总览" })).toHaveAttribute("aria-current", "page");
	});

	it("marks factors active and overview inactive on a child route", () => {
		mockUseLocation.mockReturnValue({ pathname: "/research/factors" });
		render(<ResearchSubNav />);
		expect(screen.getByRole("link", { name: "因子" })).toHaveAttribute("aria-current", "page");
		expect(screen.getByRole("link", { name: "总览" })).not.toHaveAttribute("aria-current", "page");
	});

	it("marks strategies active on a nested detail route via prefix match", () => {
		mockUseLocation.mockReturnValue({ pathname: "/research/strategies/exp-123" });
		render(<ResearchSubNav />);
		expect(screen.getByRole("link", { name: "策略" })).toHaveAttribute("aria-current", "page");
		expect(screen.getByRole("link", { name: "总览" })).not.toHaveAttribute("aria-current", "page");
	});

	it("renders links with correct href paths and omits node-descriptors", () => {
		render(<ResearchSubNav />);
		expect(screen.getByTestId("link-/research")).toBeInTheDocument();
		expect(screen.getByTestId("link-/research/factors")).toBeInTheDocument();
		expect(screen.getByTestId("link-/research/strategies")).toBeInTheDocument();
		expect(screen.getByTestId("link-/research/reviews")).toBeInTheDocument();
		expect(screen.queryByTestId("link-/research/node-descriptors")).not.toBeInTheDocument();
	});
});
