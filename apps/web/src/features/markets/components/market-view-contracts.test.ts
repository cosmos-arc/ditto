import { describe, expect, it } from "vitest";
import type { MarketCalendarStatus } from "../api/market-evidence";
import { observationAnchorLabel } from "./market-view-contracts";

function status(latestDate: string | null, latestStatus: string | null): MarketCalendarStatus {
	return {
		dataset: "calendar",
		latest_date: latestDate,
		latest_status: latestStatus,
		record_count: 1,
		catalog_freshness_at: null,
	};
}

describe("observationAnchorLabel", () => {
	it("成功摄取的工作日直接作为最近完整交易日", () => {
		// 2026-09-30 是周三；2026-11-10 是周二。
		expect(observationAnchorLabel(status("2026-09-30", "success"), false, false)).toBe("2026-09-30");
		expect(observationAnchorLabel(status("2026-11-10", "success"), false, false)).toBe("2026-11-10");
	});

	it("latest_date 落在周末时不把它称作交易日（A股周末从不交易）", () => {
		// 2026-09-26 周六、2026-09-27 周日。
		expect(observationAnchorLabel(status("2026-09-26", "success"), false, false)).toBe("2026-09-26（非交易日）");
		expect(observationAnchorLabel(status("2026-09-27", "success"), false, false)).toBe("2026-09-27（非交易日）");
	});

	it("读取中/失败/缺失按真实结果降级，不伪装完整", () => {
		expect(observationAnchorLabel(undefined, false, true)).toBe("解析中");
		expect(observationAnchorLabel(undefined, true, false)).toBe("未解析");
		expect(observationAnchorLabel(status("2026-09-29", "failed"), false, false)).toBe("最新摄取失败（2026-09-29）");
		expect(observationAnchorLabel(status(null, null), false, false)).toBe("未报告");
	});
});
