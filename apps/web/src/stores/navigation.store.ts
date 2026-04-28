import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type { DomainId } from "@/features/navigation";

type NavigationState = {
	readonly railCollapsed: boolean;
	readonly collapsedSections: Readonly<Record<string, boolean>>;
	readonly activeDomain: DomainId;
};

type NavigationActions = {
	readonly toggleRail: () => void;
	readonly setActiveDomain: (domain: DomainId) => void;
	readonly toggleSection: (sectionId: string) => void;
	readonly isSectionCollapsed: (sectionId: string) => boolean;
};

type NavigationStore = NavigationState & NavigationActions;

export const useNavigationStore = create<NavigationStore>()(
	devtools(
		(set, get) => ({
			railCollapsed: false,
			collapsedSections: {},
			activeDomain: "home",

			toggleRail: () => {
				set((state) => ({ railCollapsed: !state.railCollapsed }));
			},

			setActiveDomain: (domain: DomainId) => {
				set({ activeDomain: domain });
			},

			toggleSection: (sectionId: string) => {
				set((state) => ({
					collapsedSections: {
						...state.collapsedSections,
						[sectionId]: !state.collapsedSections[sectionId],
					},
				}));
			},

			isSectionCollapsed: (sectionId: string) => {
				return get().collapsedSections[sectionId] ?? false;
			},
		}),
		{ name: "navigation" },
	),
);
