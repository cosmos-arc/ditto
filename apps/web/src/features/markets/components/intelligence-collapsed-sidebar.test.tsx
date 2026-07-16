import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IntelligenceCollapsedSidebar } from "./intelligence-collapsed-sidebar";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";

describe("IntelligenceCollapsedSidebar", () => {
	beforeEach(() => {
		useUIPreferences.setState({ sidebarCollapsed: true });
	});

	it("renders AI insight button", () => {
		render(<IntelligenceCollapsedSidebar />);
		expect(screen.getByLabelText("AI 解读")).toBeInTheDocument();
	});

	it("renders related targets button", () => {
		render(<IntelligenceCollapsedSidebar />);
		expect(screen.getByLabelText(/关联标的/)).toBeInTheDocument();
	});

	it("shows target count badge", () => {
		render(<IntelligenceCollapsedSidebar targetCount={5} />);
		expect(screen.getByText("5")).toBeInTheDocument();
	});

	it("shows 9+ for target count over 9", () => {
		render(<IntelligenceCollapsedSidebar targetCount={12} />);
		expect(screen.getByText("9+")).toBeInTheDocument();
	});

	it("does not show badge when target count is 0", () => {
		render(<IntelligenceCollapsedSidebar targetCount={0} />);
		expect(screen.queryByText("0")).not.toBeInTheDocument();
	});

	it("calls onExpand when section button is clicked", async () => {
		const user = userEvent.setup();
		const onExpand = vi.fn();
		render(<IntelligenceCollapsedSidebar onExpand={onExpand} />);
		await user.click(screen.getByLabelText("AI 解读"));
		expect(onExpand).toHaveBeenCalledOnce();
	});

	it("has data-slot sidebar-collapsed", () => {
		render(<IntelligenceCollapsedSidebar />);
		const el = document.querySelector("[data-slot='sidebar-collapsed']");
		expect(el).toBeTruthy();
	});

	it("renders SidebarToggle at bottom", () => {
		render(<IntelligenceCollapsedSidebar />);
		expect(screen.getByLabelText("展开侧边栏")).toBeInTheDocument();
	});

	it("renders filter active count badge when activeFilterCount > 0", () => {
		render(<IntelligenceCollapsedSidebar activeFilterCount={3} />);
		expect(screen.getByText("3")).toBeInTheDocument();
	});

	it("does not render filter badge when activeFilterCount is 0", () => {
		render(<IntelligenceCollapsedSidebar activeFilterCount={0} />);
		expect(screen.queryByText("0")).not.toBeInTheDocument();
	});
});
