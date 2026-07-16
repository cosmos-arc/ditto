import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiCollapsedSidebar } from "./ai-collapsed-sidebar";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";

describe("AiCollapsedSidebar", () => {
	beforeEach(() => {
		useUIPreferences.setState({ sidebarCollapsed: true });
	});

	it("renders AI status button", () => {
		render(<AiCollapsedSidebar />);
		expect(screen.getByLabelText("AI 状态")).toBeInTheDocument();
	});

	it("renders confidence button", () => {
		render(<AiCollapsedSidebar />);
		expect(screen.getByLabelText("置信度分布")).toBeInTheDocument();
	});

	it("renders alerts button", () => {
		render(<AiCollapsedSidebar />);
		expect(screen.getByLabelText(/AI 预警/)).toBeInTheDocument();
	});

	it("shows alert count badge", () => {
		render(<AiCollapsedSidebar alertCount={3} />);
		expect(screen.getByText("3")).toBeInTheDocument();
	});

	it("shows 9+ for alert count over 9", () => {
		render(<AiCollapsedSidebar alertCount={12} />);
		expect(screen.getByText("9+")).toBeInTheDocument();
	});

	it("does not show badge when alert count is 0", () => {
		render(<AiCollapsedSidebar alertCount={0} />);
		expect(screen.queryByText("0")).not.toBeInTheDocument();
	});

	it("calls onExpand when section button is clicked", async () => {
		const user = userEvent.setup();
		const onExpand = vi.fn();
		render(<AiCollapsedSidebar onExpand={onExpand} />);
		await user.click(screen.getByLabelText("AI 状态"));
		expect(onExpand).toHaveBeenCalledOnce();
	});

	it("has data-slot sidebar-collapsed", () => {
		render(<AiCollapsedSidebar />);
		const el = document.querySelector("[data-slot='sidebar-collapsed']");
		expect(el).toBeTruthy();
	});

	it("renders SidebarToggle at bottom", () => {
		render(<AiCollapsedSidebar />);
		expect(screen.getByLabelText("展开侧边栏")).toBeInTheDocument();
	});
});
