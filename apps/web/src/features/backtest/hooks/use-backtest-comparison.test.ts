import { beforeEach, describe, expect, it, vi } from "vitest";

const key = "ditto.backtest-comparison.v1";

describe("backtest comparison session", () => {
	beforeEach(() => {
		vi.resetModules();
		sessionStorage.clear();
	});

	it("deduplicates, caps at eight, restores order after reload, and persists removal", async () => {
		const { useBacktestComparison: store } = await import("./use-backtest-comparison");
		for (let id = 0; id < 8; id += 1) expect(store.getState().setIncluded(`run-${id}`, true)).toBe(true);
		expect(store.getState().setIncluded("run-0", true)).toBe(true);
		expect(store.getState().setIncluded("run-8", true)).toBe(false);
		expect(store.getState().runIds).toHaveLength(8);
		vi.resetModules();
		const { useBacktestComparison: restored } = await import("./use-backtest-comparison");
		expect(restored.getState().runIds).toEqual(store.getState().runIds);
		expect(restored.getState().setIncluded("run-3", false)).toBe(true);
		expect(restored.getState().setIncluded("run-8", true)).toBe(true);
		expect(JSON.parse(sessionStorage.getItem(key) ?? "null")).toEqual(restored.getState().runIds);
		expect(restored.getState().runIds).toEqual([
			"run-0",
			"run-1",
			"run-2",
			"run-4",
			"run-5",
			"run-6",
			"run-7",
			"run-8",
		]);
	});

	it.each([
		"invalid json",
		'{"runIds":[]}',
		'["same","same"]',
		"[null]",
		'[""]',
		JSON.stringify(Array.from({ length: 9 }, (_, id) => `run-${id}`)),
	])("rejects an invalid session and recovers on a new selection: %s", async (stored) => {
		sessionStorage.setItem(key, stored);
		const { useBacktestComparison: store } = await import("./use-backtest-comparison");
		expect(store.getState().runIds).toEqual([]);
		expect(store.getState().error).toContain("无法恢复");
		expect(store.getState().setIncluded("valid-run", true)).toBe(true);
		expect(store.getState().error).toBeNull();
		expect(JSON.parse(sessionStorage.getItem(key) ?? "null")).toEqual(["valid-run"]);
	});
});
