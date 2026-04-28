import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useUIPreferences } from "../hooks/use-ui-preferences";
import { ViewPreferencesMenu } from "./view-preferences-menu";

describe("ViewPreferencesMenu", () => {
	beforeEach(() => {
		useUIPreferences.setState({ theme: "dark", density: "default", sidebarCollapsed: false });
		document.documentElement.removeAttribute("data-theme");
		document.documentElement.removeAttribute("data-density");
	});

	it("opens account and view preferences from one utility trigger", async () => {
		const user = userEvent.setup();
		render(<ViewPreferencesMenu />);

		await user.click(screen.getByRole("button", { name: "账户与视图偏好" }));

		expect(screen.getByRole("menu", { name: "账户与视图偏好" })).toBeInTheDocument();
		expect(screen.getByRole("menuitemradio", { name: "紧凑" })).toBeInTheDocument();
		expect(screen.getByRole("menuitemradio", { name: "亮色" })).toBeInTheDocument();
	});

	it("updates density and theme DOM attributes immediately", async () => {
		const user = userEvent.setup();
		render(<ViewPreferencesMenu />);

		await user.click(screen.getByRole("button", { name: "账户与视图偏好" }));
		await user.click(screen.getByRole("menuitemradio", { name: "紧凑" }));
		await user.click(screen.getByRole("menuitemradio", { name: "亮色" }));

		expect(document.documentElement).toHaveAttribute("data-density", "dense");
		expect(document.documentElement).toHaveAttribute("data-theme", "light");
	});
});
