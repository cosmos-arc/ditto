import { describe, expect, it } from "vitest";
import { parseInstrumentSearch } from "./$id";

describe("parseInstrumentSearch", () => {
	it("解析合法观察日锚点（自选/筛选带入图表截至日期）", () => {
		const search = parseInstrumentSearch({ tab: "chart", observeDate: "2026-03-10" });
		expect(search.tab).toBe("chart");
		expect(search.observeDate).toBe("2026-03-10");
	});

	it("缺失或非法观察日不产生锚点，不封死默认窗口", () => {
		expect(parseInstrumentSearch({ observeDate: undefined }).observeDate).toBeUndefined();
		expect(parseInstrumentSearch({}).observeDate).toBeUndefined();
		expect(parseInstrumentSearch({ observeDate: "not-a-date" }).observeDate).toBeUndefined();
		expect(parseInstrumentSearch({ observeDate: "2026-3-10" }).observeDate).toBeUndefined();
	});

	it("既有 tab 与回测下钻参数不受影响", () => {
		const search = parseInstrumentSearch({
			tab: "technical",
			selectionRunId: "run-1",
			focusDate: "2026-03-09",
			drillRunId: "bt-1",
			drillAsOf: "2026-03-27",
			drillDirection: "sell",
			observeDate: "2026-03-10",
		});
		expect(search).toMatchObject({
			drill: { date: "2026-03-09", runId: "bt-1", asOf: "2026-03-27", direction: "sell" },
			observeDate: "2026-03-10",
			selectionRunId: "run-1",
			tab: "technical",
		});
	});
});
