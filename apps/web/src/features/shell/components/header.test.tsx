import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ShellHeader } from "./header";

// Mock TanStack Router's useMatches and useRouter
const mockUseMatches = vi.fn().mockReturnValue([]);
const mockRoutesById: Record<string, { options?: { staticData?: { title?: string } } }> = {};

vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
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

	it("shows title text derived from route static data", () => {
		mockRoutesById["/markets"] = { options: { staticData: { title: "市场" } } };
		mockUseMatches.mockReturnValue([{ routeId: "/markets" }]);
		render(<ShellHeader />);
		expect(screen.getByText("市场")).toBeInTheDocument();
	});

	it("shows no title when route static data has no title", () => {
		mockRoutesById["/x"] = { options: { staticData: {} } };
		mockUseMatches.mockReturnValue([{ routeId: "/x" }]);
		render(<ShellHeader />);
		expect(screen.queryByRole("heading")).not.toBeInTheDocument();
	});

	it("shows no title when no route matches have static data", () => {
		mockUseMatches.mockReturnValue([{ routeId: "/unknown" }]);
		render(<ShellHeader />);
		expect(screen.queryByRole("heading")).not.toBeInTheDocument();
	});

	it("picks the last match with a title (most specific route)", () => {
		mockRoutesById["/trading"] = { options: { staticData: { title: "交易" } } };
		mockRoutesById["/trading/orders"] = { options: { staticData: { title: "订单管理" } } };
		mockUseMatches.mockReturnValue([{ routeId: "/trading" }, { routeId: "/trading/orders" }]);
		render(<ShellHeader />);
		expect(screen.getByText("订单管理")).toBeInTheDocument();
	});

	it("renders global command button", () => {
		render(<ShellHeader />);
		expect(screen.getByLabelText("打开全局命令")).toHaveAttribute("data-search-scope", "global");
	});

	it("renders the fixed global utility bar", () => {
		render(<ShellHeader />);

		expect(screen.getByRole("button", { name: "打开全局命令" })).toHaveAttribute("data-shell-utility", "command");
		expect(screen.getByRole("button", { name: "打开 Copilot" })).toHaveAttribute("data-shell-utility", "copilot");
		expect(screen.getByRole("button", { name: "通知" })).toHaveAttribute("data-shell-utility", "notifications");
		expect(screen.getByRole("button", { name: "帮助" })).toHaveAttribute("data-shell-utility", "help");
		expect(screen.getByRole("button", { name: "账户与视图偏好" })).toHaveAttribute("data-shell-utility", "account");
	});

	it("does not render permanent density or theme segmented controls in the header", () => {
		render(<ShellHeader />);

		expect(screen.queryByRole("button", { name: "紧凑" })).not.toBeInTheDocument();
		expect(screen.queryByRole("button", { name: "亮色" })).not.toBeInTheDocument();
	});

	it("renders notification placeholder button", () => {
		render(<ShellHeader />);
		expect(screen.getByLabelText("通知")).toBeInTheDocument();
	});

	it("renders account preferences button", () => {
		render(<ShellHeader />);
		expect(screen.getByLabelText("账户与视图偏好")).toBeInTheDocument();
	});

	it("has border-bottom styling", () => {
		const { container } = render(<ShellHeader />);
		const header = container.firstChild as HTMLElement;
		expect(header.className).toContain("border-b");
		expect(header.className).toContain("border-[var(--color-border-subtle)]");
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
