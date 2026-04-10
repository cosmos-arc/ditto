import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

export type Theme = "dark" | "light";
export type Density = "dense" | "default" | "comfortable";

interface UIPreferencesState {
	readonly theme: Theme;
	readonly density: Density;
}

interface UIPreferencesActions {
	readonly setTheme: (theme: Theme) => void;
	readonly setDensity: (density: Density) => void;
	readonly applyThemeToDom: () => void;
}

export type UIPreferences = UIPreferencesState & UIPreferencesActions;

function applyAttributesToDom(theme: Theme, density: Density): void {
	const root = document.documentElement;

	if (theme === "dark") {
		root.removeAttribute("data-theme");
	} else {
		root.setAttribute("data-theme", theme);
	}

	if (density === "default") {
		root.removeAttribute("data-density");
	} else {
		root.setAttribute("data-density", density);
	}
}

export const useUIPreferences = create<UIPreferences>()(
	devtools(
		persist(
			(set, get) => ({
				theme: "dark",
				density: "default",

				setTheme: (theme: Theme) => {
					set({ theme });
				},

				setDensity: (density: Density) => {
					set({ density });
				},

				applyThemeToDom: () => {
					const { theme, density } = get();
					applyAttributesToDom(theme, density);
				},
			}),
			{ name: "ditto-ui-prefs" },
		),
		{ name: "ui-preferences" },
	),
);
