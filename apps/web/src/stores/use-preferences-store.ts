import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "dark" | "light";
type Density = "compact" | "comfortable" | "ultra-compact";

interface PreferencesState {
	theme: Theme;
	density: Density;
	setTheme: (theme: Theme) => void;
	setDensity: (density: Density) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
	persist(
		(set) => ({
			theme: "dark",
			density: "compact",
			setTheme: (theme) => set({ theme }),
			setDensity: (density) => set({ density }),
		}),
		{
			name: "ditto-preferences",
		},
	),
);
