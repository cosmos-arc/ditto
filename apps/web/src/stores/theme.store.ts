import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

type Theme = "dark" | "light" | "system";
type ResolvedTheme = "dark" | "light";

type ThemeState = {
	readonly theme: Theme;
	readonly resolvedTheme: ResolvedTheme;
};

type ThemeActions = {
	readonly setTheme: (theme: Theme) => void;
	readonly toggleTheme: () => void;
};

type ThemeStore = ThemeState & ThemeActions;

function resolveTheme(theme: Theme): ResolvedTheme {
	if (theme !== "system") return theme;
	return window.matchMedia("(prefers-color-scheme: dark)").matches
		? "dark"
		: "light";
}

export const useThemeStore = create<ThemeStore>()(
	devtools(
		persist(
			(set, get) => ({
				theme: "dark",
				resolvedTheme: "dark",

				setTheme: (theme: Theme) => {
					set({ theme, resolvedTheme: resolveTheme(theme) });
				},

				toggleTheme: () => {
					const current = get().resolvedTheme;
					const next: Theme = current === "dark" ? "light" : "dark";
					set({ theme: next, resolvedTheme: next });
				},
			}),
			{ name: "ditto-theme" },
		),
		{ name: "theme" },
	),
);
