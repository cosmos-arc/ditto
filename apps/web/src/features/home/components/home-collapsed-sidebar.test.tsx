import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HomeCollapsedSidebar } from "./home-collapsed-sidebar";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";

describe("HomeCollapsedSidebar", () => {
	beforeEach(() => {
		useUIPreferences.setState({ sidebarCollapsed: true });
	});

	it("renders three section buttons", () => {
		render(<HomeCollapsedSidebar />);
		expect(screen.getByLabelText("市场脉搏")).toBeInTheDocument();
		expect(screen.getByLabelText(/全局预警/)).toBeInTheDocument();
		expect(screen.getByLabelText(/数据健康/)).toBeInTheDocument();
	});

	it("shows alert count badge", () => {
		render(<HomeCollapsedSidebar alertCount={3} />);
		expect(screen.getByText("3")).toBeInTheDocument();
	});

	it("shows 9+ for alert count over 9", () => {
		render(<HomeCollapsedSidebar alertCount={12} />);
		expect(screen.getByText("9+")).toBeInTheDocument();
	});

	it("does not show badge when alert count is 0", () => {
		render(<HomeCollapsedSidebar alertCount={0} />);
		expect(screen.queryByText("0")).not.toBeInTheDocument();
	});

	it("calls onExpand when section button is clicked", async () => {
		const user = userEvent.setup();
		const onExpand = vi.fn();
		render(<HomeCollapsedSidebar onExpand={onExpand} />);
		await user.click(screen.getByLabelText("市场脉搏"));
		expect(onExpand).toHaveBeenCalledOnce();
	});

	it("has data-slot sidebar-collapsed", () => {
		render(<HomeCollapsedSidebar />);
		const el = document.querySelector("[data-slot='sidebar-collapsed']");
		expect(el).toBeTruthy();
	});

	it("renders SidebarToggle at bottom", () => {
		render(<HomeCollapsedSidebar />);
		expect(screen.getByLabelText("展开侧边栏")).toBeInTheDocument();
	});
});
