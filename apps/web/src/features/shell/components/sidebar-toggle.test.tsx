import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useUIPreferences } from "../hooks/use-ui-preferences";
import { SidebarToggle } from "./sidebar-toggle";

describe("SidebarToggle", () => {
	beforeEach(() => {
		useUIPreferences.setState({ sidebarCollapsed: false });
	});

	it("renders with collapse aria-label when expanded", () => {
		render(<SidebarToggle />);
		expect(screen.getByLabelText("折叠侧边栏")).toBeInTheDocument();
	});

	it("renders with expand aria-label when collapsed", () => {
		useUIPreferences.setState({ sidebarCollapsed: true });
		render(<SidebarToggle />);
		expect(screen.getByLabelText("展开侧边栏")).toBeInTheDocument();
	});

	it("toggles sidebarCollapsed on click", async () => {
		const user = userEvent.setup();
		render(<SidebarToggle />);
		await user.click(screen.getByLabelText("折叠侧边栏"));
		expect(useUIPreferences.getState().sidebarCollapsed).toBe(true);
	});

	it("has data-slot attribute", () => {
		render(<SidebarToggle />);
		expect(screen.getByLabelText("折叠侧边栏")).toHaveAttribute("data-slot", "sidebar-toggle");
	});
});
