import { beforeEach, describe, expect, it } from "vitest";
import { useNavigationStore } from "@/features/navigation";

describe("navigationStore", () => {
	beforeEach(() => {
		useNavigationStore.setState({
			railCollapsed: false,
			collapsedSections: {},
			activeDomain: "home",
		});
	});

	it("默认 rail 未折叠", () => {
		expect(useNavigationStore.getState().railCollapsed).toBe(false);
	});

	it("默认活跃域为 home", () => {
		expect(useNavigationStore.getState().activeDomain).toBe("home");
	});

	it("toggleRail 切换折叠状态", () => {
		useNavigationStore.getState().toggleRail();
		expect(useNavigationStore.getState().railCollapsed).toBe(true);
		useNavigationStore.getState().toggleRail();
		expect(useNavigationStore.getState().railCollapsed).toBe(false);
	});

	it("setActiveDomain 设置活跃域", () => {
		useNavigationStore.getState().setActiveDomain("markets");
		expect(useNavigationStore.getState().activeDomain).toBe("markets");
	});

	it("toggleSection 切换区块折叠", () => {
		useNavigationStore.getState().toggleSection("watchlist");
		expect(useNavigationStore.getState().collapsedSections["watchlist"]).toBe(true);
		useNavigationStore.getState().toggleSection("watchlist");
		expect(useNavigationStore.getState().collapsedSections["watchlist"]).toBe(false);
	});

	it("isSectionCollapsed 查询区块折叠状态", () => {
		expect(useNavigationStore.getState().isSectionCollapsed("watchlist")).toBe(false);
		useNavigationStore.getState().toggleSection("watchlist");
		expect(useNavigationStore.getState().isSectionCollapsed("watchlist")).toBe(true);
	});
});
