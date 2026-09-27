import { describe, expect, it } from "vitest";
import type { CockpitBar } from "@/components/chart";
import { formatTradeDate, primaryAnswerFromBars, toCockpitBars, tradeDateToUnix } from "./chart-mapping";

const day = (iso: string) => tradeDateToUnix(iso);

describe("toCockpitBars", () => {
	it("maps DTO rows ascending with UTC unix time and full OHLCV", () => {
		const bars = toCockpitBars([
			{
				first_trade_date: "2026-03-10",
				last_trade_date: "2026-03-10",
				available_at: "2026-03-10T08:00:00Z",
				published_at: "2026-03-10T08:00:00Z",
				partial: false,
				source_snapshot_ids: ["bars-1"],
				trade_date: "2026-03-10",
				open: 1744.6,
				high: 1768.8,
				low: 1738.4,
				close: 1750.2,
				volume: 3_210_000,
				amount: 5_632_000_000,
			},
			{
				first_trade_date: "2026-03-09",
				last_trade_date: "2026-03-09",
				available_at: "2026-03-09T08:00:00Z",
				published_at: "2026-03-09T08:00:00Z",
				partial: false,
				source_snapshot_ids: ["bars-1"],
				trade_date: "2026-03-09",
				open: 1752,
				high: 1760,
				low: 1732.1,
				close: 1746.3,
				volume: 3_140_000,
				amount: 5_490_000_000,
			},
		]);
		expect(bars.map((bar) => bar.time)).toEqual([day("2026-03-09"), day("2026-03-10")]);
		expect(bars[1]).toMatchObject({ open: 1744.6, high: 1768.8, low: 1738.4, close: 1750.2, volume: 3_210_000 });
	});
});

describe("primaryAnswerFromBars", () => {
	it("derives close, change vs previous close, window range and direction", () => {
		const bars: CockpitBar[] = [
			{ time: day("2026-03-09"), open: 10, high: 11, low: 9, close: 100, volume: 1 },
			{ time: day("2026-03-10"), open: 10, high: 12.5, low: 9.5, close: 103.5, volume: 2 },
		];
		const answer = primaryAnswerFromBars(bars);
		expect(answer).toMatchObject({
			tradeDate: "2026-03-10",
			close: 103.5,
			previousClose: 100,
			change: 3.5,
			windowLow: 9,
			windowHigh: 12.5,
			direction: "up",
		});
		expect(answer?.changePercent).toBeCloseTo(3.5, 10);
		expect(primaryAnswerFromBars([])).toBeNull();
	});
});

describe("formatTradeDate", () => {
	it("renders UTC calendar dates", () => {
		expect(formatTradeDate(day("2026-03-09"))).toBe("2026-03-09");
	});
});
