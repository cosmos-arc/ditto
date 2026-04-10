import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ShellHeader } from "./header";

// Mock TanStack Router's useMatches and useRouter
const mockUseMatches = vi.fn().mockReturnValue([]);
const mockRoutesById: Record<string, { options?: { handle?: { title?: string } } }> = {};

vi.mock("@tanstack/react-router", async () => {
	const actual =
		await vi.importActual<typeof import("@tanstack/react-router")>(
			"@tanstack/react-router",
		);
	return {
		...actual,
		useMatches: () => mockUseMatches(),
		useRouter: () => ({ routesById: mockRoutesById }),
	};
});

describe("ShellHeader", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		// Reset routes by id
		for (const key of Object.keys(mockRoutesById)) {
			delete mockRoutesById[key];
		}
	});

	it("renders the header container with correct height class", () => {
		const { container } = render(<ShellHeader />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("h-[var(--height-header)]");
	});

	it("shows title text derived from route handle", () => {
		mockRoutesById["/markets"] = { options: { handle: { title: "市场" } } };
		mockUseMatches.mockReturnValue([{ routeId: "/markets" }]);
		render(<ShellHeader />);
		expect(screen.getByText("市场")).toBeInTheDocument();
	});

	it("shows no title when route handle has no title", () => {
		mockRoutesById["/x"] = { options: { handle: {} } };
		mockUseMatches.mockReturnValue([{ routeId: "/x" }]);
		render(<ShellHeader />);
		expect(screen.queryByRole("heading")).not.toBeInTheDocument();
	});

	it("shows no title when no route matches have handle", () => {
		mockUseMatches.mockReturnValue([{ routeId: "/unknown" }]);
		render(<ShellHeader />);
		expect(screen.queryByRole("heading")).not.toBeInTheDocument();
	});

	it("picks the last match with a title (most specific route)", () => {
		mockRoutesById["/trading"] = { options: { handle: { title: "交易" } } };
		mockRoutesById["/trading/orders"] = { options: { handle: { title: "订单管理" } } };
		mockUseMatches.mockReturnValue([
			{ routeId: "/trading" },
			{ routeId: "/trading/orders" },
		]);
		render(<ShellHeader />);
		expect(screen.getByText("订单管理")).toBeInTheDocument();
	});

	it("renders search placeholder button", () => {
		render(<ShellHeader />);
		expect(screen.getByLabelText("搜索")).toBeInTheDocument();
	});

	it("renders notification placeholder button", () => {
		render(<ShellHeader />);
		expect(screen.getByLabelText("通知")).toBeInTheDocument();
	});

	it("renders avatar placeholder button", () => {
		render(<ShellHeader />);
		expect(screen.getByLabelText("用户头像")).toBeInTheDocument();
	});

	it("has border-bottom styling", () => {
		const { container } = render(<ShellHeader />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("border-b");
		expect(header.className).toContain(
			"border-[var(--color-border-subtle)]",
		);
	});

	it("applies background color", () => {
		const { container } = render(<ShellHeader />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("bg-(--color-surface-frosted)");
	});

	it("has z-index for stacking context", () => {
		const { container } = render(<ShellHeader />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("z-5");
	});
});
