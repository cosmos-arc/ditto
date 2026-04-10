import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeSwitcher } from "./theme-switcher";
import { useUIPreferences } from "../hooks/use-ui-preferences";

describe("ThemeSwitcher", () => {
	beforeEach(() => {
		useUIPreferences.setState({ theme: "dark", density: "default" });
	});

	it("renders with data-slot='theme-switcher'", () => {
		const { container } = render(<ThemeSwitcher />);
		expect(container.firstChild).toHaveAttribute("data-slot", "theme-switcher");
	});

	it("renders density group with 3 buttons", () => {
		render(<ThemeSwitcher />);
		expect(screen.getByLabelText("紧凑")).toBeInTheDocument();
		expect(screen.getByLabelText("标准")).toBeInTheDocument();
		expect(screen.getByLabelText("宽松")).toBeInTheDocument();
	});

	it("renders theme group with 2 buttons", () => {
		render(<ThemeSwitcher />);
		expect(screen.getByLabelText("亮色")).toBeInTheDocument();
		expect(screen.getByLabelText("暗色")).toBeInTheDocument();
	});

	it("marks current density as active", () => {
		render(<ThemeSwitcher />);
		const standardBtn = screen.getByLabelText("标准");
		expect(standardBtn).toHaveAttribute("data-active", "true");
	});

	it("marks current theme as active", () => {
		render(<ThemeSwitcher />);
		const darkBtn = screen.getByLabelText("暗色");
		expect(darkBtn).toHaveAttribute("data-active", "true");
	});

	it("calls setDensity on density button click", async () => {
		const user = userEvent.setup();
		render(<ThemeSwitcher />);
		await user.click(screen.getByLabelText("紧凑"));
		expect(useUIPreferences.getState().density).toBe("dense");
	});

	it("calls setTheme on theme button click", async () => {
		const user = userEvent.setup();
		render(<ThemeSwitcher />);
		await user.click(screen.getByLabelText("亮色"));
		expect(useUIPreferences.getState().theme).toBe("light");
	});

	it("updates active state after density change", async () => {
		const user = userEvent.setup();
		render(<ThemeSwitcher />);
		await user.click(screen.getByLabelText("宽松"));
		expect(screen.getByLabelText("宽松")).toHaveAttribute("data-active", "true");
		expect(screen.getByLabelText("标准")).toHaveAttribute("data-active", "false");
	});

	it("updates active state after theme change", async () => {
		const user = userEvent.setup();
		render(<ThemeSwitcher />);
		await user.click(screen.getByLabelText("亮色"));
		expect(screen.getByLabelText("亮色")).toHaveAttribute("data-active", "true");
		expect(screen.getByLabelText("暗色")).toHaveAttribute("data-active", "false");
	});
});
