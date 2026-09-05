import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { useUIPreferences } from "../hooks/use-ui-preferences";
import { ThemeSwitcher } from "./theme-switcher";

describe("ThemeSwitcher", () => {
	beforeEach(() => {
		useUIPreferences.setState({ theme: "dark", density: "default" });
	});

	it("renders the account-scoped view preferences trigger", () => {
		render(<ThemeSwitcher />);

		expect(screen.getByRole("button", { name: "账户与视图偏好" })).toHaveAttribute("data-shell-utility", "account");
	});

	it("keeps density and theme choices inside the preferences menu", async () => {
		const user = userEvent.setup();
		render(<ThemeSwitcher />);

		expect(screen.queryByRole("menuitemradio", { name: "紧凑" })).not.toBeInTheDocument();

		await user.click(screen.getByRole("button", { name: "账户与视图偏好" }));

		expect(screen.getByRole("menuitemradio", { name: "紧凑" })).toBeInTheDocument();
		expect(screen.getByRole("menuitemradio", { name: "亮色" })).toBeInTheDocument();
	});
});
