import { describe, expect, it } from "vitest";
import { dateYearsBefore, isValidIsoCalendarDate } from "./iso-calendar-date";

describe("isValidIsoCalendarDate", () => {
	it("accepts real calendar dates only (Date round-trip, not just the shape)", () => {
		expect(isValidIsoCalendarDate("2026-11-10")).toBe(true);
		expect(isValidIsoCalendarDate("2024-02-29")).toBe(true); // 闰日真实存在
	});

	it("rejects shape-valid but fake dates that would explode date arithmetic", () => {
		expect(isValidIsoCalendarDate("2026-13-45")).toBe(false);
		expect(isValidIsoCalendarDate("2026-02-30")).toBe(false);
		expect(isValidIsoCalendarDate("2027-02-29")).toBe(false); // 非闰年
		expect(isValidIsoCalendarDate("not-a-date")).toBe(false);
		expect(isValidIsoCalendarDate("2026-3-10")).toBe(false);
	});
});

describe("dateYearsBefore", () => {
	it("shifts back one calendar year without timezone drift", () => {
		expect(dateYearsBefore("2026-11-10", 1)).toBe("2025-11-10");
		expect(dateYearsBefore("2024-03-01", 1)).toBe("2023-03-01");
	});
});
