import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, it, beforeEach, expect } from "vitest";
import { DashboardShell } from "../components/dashboard-shell";

describe("DashboardShell", () => {
	beforeEach(() => {
		document.documentElement.classList.remove("dark", "light");
		document.documentElement.removeAttribute("data-grid-density");
		localStorage.clear();
	});

	it("渲染侧边栏导航", () => {
		render(<DashboardShell />);
		expect(screen.getByRole("navigation")).toBeInTheDocument();
	});

	it("侧边栏包含 Ditto 品牌标识", () => {
		render(<DashboardShell />);
		expect(screen.getByText("Ditto")).toBeInTheDocument();
	});

	it("渲染主内容区域", () => {
		render(<DashboardShell />);
		expect(screen.getByRole("main")).toBeInTheDocument();
	});

	it("渲染顶栏", () => {
		render(<DashboardShell />);
		expect(screen.getByRole("banner")).toBeInTheDocument();
	});

	it("侧边栏包含核心导航项", () => {
		render(<DashboardShell />);
		const nav = screen.getByRole("navigation");
		expect(nav).toHaveTextContent("Dashboard");
		expect(nav).toHaveTextContent("行情数据");
		expect(nav).toHaveTextContent("策略中心");
		expect(nav).toHaveTextContent("回测中心");
		expect(nav).toHaveTextContent("风控中心");
	});

	it("顶栏包含主题切换按钮", () => {
		render(<DashboardShell />);
		expect(screen.getByRole("button", { name: "Light" })).toBeInTheDocument();
	});

	it("顶栏包含密度切换按钮", () => {
		render(<DashboardShell />);
		expect(screen.getByRole("button", { name: "compact" })).toBeInTheDocument();
	});

	it("点击主题切换按钮切换 dark/light", async () => {
		const user = userEvent.setup();
		render(<DashboardShell />);

		const themeBtn = screen.getByRole("button", { name: "Light" });
		await user.click(themeBtn);

		expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
		expect(document.documentElement.classList.contains("light")).toBe(true);
	});

	it("点击密度切换按钮循环密度", async () => {
		const user = userEvent.setup();
		render(<DashboardShell />);

		const densityBtn = screen.getByRole("button", { name: "compact" });
		await user.click(densityBtn);
		expect(screen.getByRole("button", { name: "comfortable" })).toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "comfortable" }));
		expect(screen.getByRole("button", { name: "ultra-compact" })).toBeInTheDocument();
	});

	it("展示四色域 Token 卡片", () => {
		render(<DashboardShell />);
		expect(screen.getByText("四色域 Token")).toBeInTheDocument();
		expect(screen.getByText("涨 Up")).toBeInTheDocument();
		expect(screen.getByText("跌 Down")).toBeInTheDocument();
		expect(screen.getByText("Buy")).toBeInTheDocument();
	});

	it("展示 shadcn/ui 组件卡片", () => {
		render(<DashboardShell />);
		expect(screen.getByText("shadcn/ui 组件")).toBeInTheDocument();
		expect(screen.getByText("Default")).toBeInTheDocument();
		expect(screen.getByText("Outline")).toBeInTheDocument();
		expect(screen.getByPlaceholderText("输入框示例...")).toBeInTheDocument();
	});

	it("展示 Surface 层级卡片", () => {
		render(<DashboardShell />);
		expect(screen.getByText("Surface 层级")).toBeInTheDocument();
		expect(screen.getByText("surface-app")).toBeInTheDocument();
		expect(screen.getByText("surface-elevated")).toBeInTheDocument();
	});
});
