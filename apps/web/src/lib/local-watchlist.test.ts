import { beforeEach, describe, expect, it } from "vitest";
import { addToLocalWatchlist, LOCAL_WATCHLIST_STORAGE_KEY, readLocalWatchlist } from "./local-watchlist";

beforeEach(() => localStorage.clear());

describe("readLocalWatchlist", () => {
	it("返回空数组当存储缺失或非数组", () => {
		expect(readLocalWatchlist()).toEqual([]);
		localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify({ ids: [1] }));
		expect(readLocalWatchlist()).toEqual([]);
	});

	it("过滤非法条目（非正整数）", () => {
		localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify([1, 0, -2, 1.5, "3", null]));
		expect(readLocalWatchlist()).toEqual([1]);
	});

	it("保留首次出现顺序去重重复 ID", () => {
		localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify([1000003, 1000001, 1000003, 1000001, 1000002]));
		expect(readLocalWatchlist()).toEqual([1000003, 1000001, 1000002]);
	});
});

describe("addToLocalWatchlist", () => {
	it("写入去重后的清单，不产生重复 ID", () => {
		addToLocalWatchlist(1000001);
		addToLocalWatchlist(1000002);
		addToLocalWatchlist(1000001);
		expect(readLocalWatchlist()).toEqual([1000001, 1000002]);
	});
});
