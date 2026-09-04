import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useUIPreferences } from "./use-ui-preferences";

describe("useUIPreferences store", () => {
	beforeEach(() => {
		// Reset store to defaults
		useUIPreferences.setState({
			theme: "dark",
			density: "default",
			sidebarCollapsed: false,
		});
		// Clean up document attributes
		document.documentElement.removeAttribute("data-theme");
		document.documentElement.removeAttribute("data-density");
		document.documentElement.removeAttribute("data-sidebar-collapsed");
	});

	afterEach(() => {
		document.documentElement.removeAttribute("data-sidebar-collapsed");
	});

	it("defaults to dark theme", () => {
		expect(useUIPreferences.getState().theme).toBe("dark");
	});

	it("defaults to default density", () => {
		expect(useUIPreferences.getState().density).toBe("default");
	});

	it("setTheme updates theme value", () => {
		useUIPreferences.getState().setTheme("light");
		expect(useUIPreferences.getState().theme).toBe("light");
	});

	it("setTheme syncs the DOM without a separate stale apply call", () => {
		useUIPreferences.getState().setTheme("light");
		expect(document.documentElement).toHaveAttribute("data-theme", "light");
	});

	it("setDensity updates density value", () => {
		useUIPreferences.getState().setDensity("dense");
		expect(useUIPreferences.getState().density).toBe("dense");
	});

	it("setDensity syncs the DOM without a separate stale apply call", () => {
		useUIPreferences.getState().setDensity("dense");
		expect(document.documentElement).toHaveAttribute("data-density", "dense");
	});

	it("setDensity cycles through all values", () => {
		useUIPreferences.getState().setDensity("dense");
		expect(useUIPreferences.getState().density).toBe("dense");
		useUIPreferences.getState().setDensity("comfortable");
		expect(useUIPreferences.getState().density).toBe("comfortable");
		useUIPreferences.getState().setDensity("default");
		expect(useUIPreferences.getState().density).toBe("default");
	});

	describe("DOM sync via applyThemeToDom", () => {
		it("sets data-theme attribute on documentElement", () => {
			useUIPreferences.getState().setTheme("light");
			// Manually trigger DOM sync (simulating what the hook does)
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-theme")).toBe("light");
		});

		it("removes data-theme when theme is dark (default)", () => {
			document.documentElement.setAttribute("data-theme", "light");
			useUIPreferences.getState().setTheme("dark");
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-theme")).toBeNull();
		});

		it("sets data-density attribute on documentElement", () => {
			useUIPreferences.getState().setDensity("dense");
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-density")).toBe("dense");
		});

		it("removes data-density when density is default", () => {
			document.documentElement.setAttribute("data-density", "dense");
			useUIPreferences.getState().setDensity("default");
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-density")).toBeNull();
		});

		it("sets both attributes together", () => {
			useUIPreferences.getState().setTheme("light");
			useUIPreferences.getState().setDensity("comfortable");
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-theme")).toBe("light");
			expect(document.documentElement.getAttribute("data-density")).toBe("comfortable");
		});
	});

	describe("sidebarCollapsed", () => {
		it("defaults to false", () => {
			expect(useUIPreferences.getState().sidebarCollapsed).toBe(false);
		});

		it("toggleSidebarCollapsed toggles from false to true", () => {
			useUIPreferences.getState().toggleSidebarCollapsed();
			expect(useUIPreferences.getState().sidebarCollapsed).toBe(true);
		});

		it("toggleSidebarCollapsed toggles from true to false", () => {
			useUIPreferences.setState({ sidebarCollapsed: true });
			useUIPreferences.getState().toggleSidebarCollapsed();
			expect(useUIPreferences.getState().sidebarCollapsed).toBe(false);
		});

		it("sets data-sidebar-collapsed attribute when true", () => {
			useUIPreferences.setState({ sidebarCollapsed: true });
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-sidebar-collapsed")).toBe("");
		});

		it("removes data-sidebar-collapsed attribute when false", () => {
			document.documentElement.setAttribute("data-sidebar-collapsed", "");
			useUIPreferences.setState({ sidebarCollapsed: false });
			useUIPreferences.getState().applyThemeToDom();
			expect(document.documentElement.getAttribute("data-sidebar-collapsed")).toBeNull();
		});
	});
});
