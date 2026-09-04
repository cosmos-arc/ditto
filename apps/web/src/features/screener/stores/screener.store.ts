import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type { FilterCondition } from "@/types";

type ScreenerFilterState = {
	readonly activeFilters: readonly FilterCondition[];
	readonly selectedIds: readonly string[];
	readonly sortBy: string;
	readonly sortDirection: "asc" | "desc";
	readonly page: number;
	readonly pageSize: number;
};

type ScreenerFilterActions = {
	readonly addFilter: (filter: FilterCondition) => void;
	readonly removeFilter: (field: string) => void;
	readonly clearFilters: () => void;
	readonly toggleSelect: (id: string) => void;
	readonly clearSelection: () => void;
	readonly setSort: (sortBy: string, direction: "asc" | "desc") => void;
	readonly setPage: (page: number) => void;
};

type ScreenerStore = ScreenerFilterState & ScreenerFilterActions;

export const useScreenerStore = create<ScreenerStore>()(
	devtools(
		(set, get) => ({
			activeFilters: [],
			selectedIds: [],
			sortBy: "changePercent",
			sortDirection: "desc",
			page: 1,
			pageSize: 20,

			addFilter: (filter: FilterCondition) => {
				const existing = get().activeFilters.find((f) => f.field === filter.field);
				if (existing) {
					set({
						activeFilters: get().activeFilters.map((f) => (f.field === filter.field ? filter : f)),
					});
				} else {
					set({ activeFilters: [...get().activeFilters, filter], page: 1 });
				}
			},

			removeFilter: (field: string) => {
				set({
					activeFilters: get().activeFilters.filter((f) => f.field !== field),
					page: 1,
				});
			},

			clearFilters: () => {
				set({ activeFilters: [], page: 1 });
			},

			toggleSelect: (id: string) => {
				const ids = get().selectedIds;
				set({
					selectedIds: ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id],
				});
			},

			clearSelection: () => {
				set({ selectedIds: [] });
			},

			setSort: (sortBy: string, direction: "asc" | "desc") => {
				set({ sortBy, sortDirection: direction });
			},

			setPage: (page: number) => {
				set({ page });
			},
		}),
		{ name: "screener" },
	),
);
