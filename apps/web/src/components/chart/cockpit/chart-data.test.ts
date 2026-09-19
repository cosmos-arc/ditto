import { describe, expect, it } from "vitest";
import {
	buildPngFooterLines,
	type CockpitBar,
	directionBetween,
	directionColorToken,
	findGapRanges,
	formatReadoutTime,
	freshnessBucket,
	lastNonNullClose,
	splitByFreshness,
	toCsvExport,
	toLineSeriesData,
	toVolumeSeriesData,
} from "./chart-data";

const MINUTE = 60_000;

describe("freshnessBucket", () => {
	it("maps ages onto the token-documented boundaries", () => {
		expect(freshnessBucket(4_999)).toBe("live");
		expect(freshnessBucket(5_000)).toBe("recent");
		expect(freshnessBucket(29_999)).toBe("recent");
		expect(freshnessBucket(30_000)).toBe("aging");
		expect(freshnessBucket(300_000 - 1)).toBe("aging");
		expect(freshnessBucket(300_000)).toBe("stale");
		expect(freshnessBucket(1_800_000 - 1)).toBe("stale");
		expect(freshnessBucket(1_800_000)).toBe("expired");
	});
});

describe("toLineSeriesData", () => {
	it("maps missing closes to whitespace points so gaps render without interpolation", () => {
		const bars: CockpitBar[] = [
			{ time: 100, close: 10.5, volume: 100 },
			{ time: 200, close: null, volume: null },
			{ time: 300, close: null, volume: null },
			{ time: 400, close: 11, volume: 90 },
		];
		const points = toLineSeriesData(bars);
		expect(points).toEqual([{ time: 100, value: 10.5 }, { time: 200 }, { time: 300 }, { time: 400, value: 11 }]);
		expect("value" in points[1]!).toBe(false);
		expect("value" in points[2]!).toBe(false);
	});

	it("sorts bars by time before mapping", () => {
		const bars: CockpitBar[] = [
			{ time: 300, close: 3, volume: null },
			{ time: 100, close: 1, volume: null },
		];
		expect(toLineSeriesData(bars).map((p) => p.time)).toEqual([100, 300]);
	});
});

describe("splitByFreshness", () => {
	it("partitions points into contiguous bucket runs in order", () => {
		const now = 10 * MINUTE;
		const bars: CockpitBar[] = [
			{ time: 0, close: 1, volume: null }, // age 10min → stale
			{ time: 420, close: 2, volume: null }, // age 3min → aging
			{ time: 430, close: 3, volume: null }, // age 2m50s → aging
			{ time: 580, close: 4, volume: null }, // age 20s → recent
		];
		const segments = splitByFreshness(bars, now);
		expect(segments.map((s) => s.bucket)).toEqual(["stale", "aging", "recent"]);
		const flat = segments.flatMap((s) => s.points);
		expect(flat.filter((p, i) => flat.indexOf(p) === i)).toHaveLength(4);
	});

	it("carries the previous run's last point as a connector so the line stays continuous", () => {
		const now = 10 * MINUTE;
		const bars: CockpitBar[] = [
			{ time: 0, close: 1, volume: null }, // age 10min → stale
			{ time: 580, close: 4, volume: null }, // age 20s → recent
		];
		const segments = splitByFreshness(bars, now);
		expect(segments.map((s) => s.bucket)).toEqual(["stale", "recent"]);
		expect(segments[1]!.points[0]).toEqual(bars[0]);
		expect(segments[1]!.points.at(-1)).toEqual(bars[1]);
	});
});

describe("direction mapping", () => {
	it("derives direction from previous close with flat defaults", () => {
		expect(directionBetween(null, 5)).toBe("flat");
		expect(directionBetween(5, 6)).toBe("up");
		expect(directionBetween(5, 4)).toBe("down");
		expect(directionBetween(5, 5)).toBe("flat");
	});

	it("maps direction onto the chart-layer market color tokens", () => {
		expect(directionColorToken("up")).toBe("var(--chart-series-up)");
		expect(directionColorToken("down")).toBe("var(--chart-series-down)");
		expect(directionColorToken("flat")).toBe("var(--chart-series-neutral)");
	});
});

describe("toVolumeSeriesData", () => {
	it("colors bars by close direction and keeps missing volume as whitespace", () => {
		const bars: CockpitBar[] = [
			{ time: 1, close: 10, volume: 100 },
			{ time: 2, close: 11, volume: 120 },
			{ time: 3, close: 11, volume: null },
			{ time: 4, close: 10, volume: 80 },
			{ time: 5, close: null, volume: 50 },
		];
		const points = toVolumeSeriesData(bars, (direction) => `c-${direction}`);
		expect(points).toEqual([
			{ time: 1, value: 100, color: "c-flat" },
			{ time: 2, value: 120, color: "c-up" },
			{ time: 3 },
			{ time: 4, value: 80, color: "c-down" },
			{ time: 5, value: 50, color: "c-flat" },
		]);
	});
});

describe("lastNonNullClose", () => {
	it("returns the newest bar with a close, scanning backwards", () => {
		const bars: CockpitBar[] = [
			{ time: 1, close: 1, volume: null },
			{ time: 2, close: null, volume: null },
			{ time: 3, close: null, volume: null },
		];
		expect(lastNonNullClose(bars)).toEqual(bars[0]);
		expect(lastNonNullClose([])).toBeNull();
	});
});

describe("findGapRanges", () => {
	it("reports contiguous missing ranges bounded by the next available bar", () => {
		const bars: CockpitBar[] = [
			{ time: 100, close: 1, volume: null },
			{ time: 200, close: null, volume: null },
			{ time: 300, close: null, volume: null },
			{ time: 400, close: 2, volume: null },
			{ time: 500, close: 3, volume: null },
			{ time: 600, close: null, volume: null },
		];
		expect(findGapRanges(bars)).toEqual([
			{ from: 200, to: 400 },
			{ from: 600, to: 600 },
		]);
		expect(findGapRanges([{ time: 1, close: 1, volume: 1 }])).toEqual([]);
	});
});

describe("toCsvExport", () => {
	it("emits gap rows as empty cells and carries full PIT identity columns", () => {
		const csv = toCsvExport(
			[
				{
					id: "price",
					bars: [
						{ time: 100, close: 10.5, volume: 100 },
						{ time: 200, close: null, volume: null },
					],
				},
			],
			{
				asOf: 300,
				snapshotId: "snap-0123456789abcdef-フル",
				knowledgeCutoff: "2026-09-17T00:00:00Z",
				publicationCutoff: null,
				dataSourceName: "tushare",
				productVersion: "0.1.0",
				exportedAtMs: Date.UTC(2026, 8, 18, 8, 0, 0),
			},
		);
		const lines = csv.split("\n");
		expect(lines[0]).toBe(
			"time,close_price,volume,as_of,snapshot_id,knowledge_cutoff,publication_cutoff,data_source,exported_at,product_version",
		);
		expect(lines[1]).toContain("1970-01-01T00:01:40Z,10.5,100,1970-01-01T00:05:00Z");
		expect(lines[1]).toContain("snap-0123456789abcdef-フル");
		expect(lines[2]).toContain("1970-01-01T00:03:20Z,,");
		expect(lines.slice(1).every((line) => line.endsWith(",tushare,2026-09-18T08:00:00.000Z,0.1.0"))).toBe(true);
	});
});

describe("formatReadoutTime", () => {
	it("formats UTC wall time for readouts", () => {
		expect(formatReadoutTime(Date.UTC(2026, 8, 17, 1, 30) / 1000)).toBe("2026-09-17 01:30");
	});
});

describe("buildPngFooterLines", () => {
	it("carries full PIT identity without truncating the snapshot id", () => {
		const [pitLine, sourceLine] = buildPngFooterLines({
			asOf: 1_000,
			snapshotId: "snap-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
			knowledgeCutoff: "2026-09-17T00:00:00Z",
			publicationCutoff: null,
			dataSourceName: "tushare",
			productVersion: "0.1.0",
			exportedAtMs: Date.UTC(2026, 8, 18, 8, 0, 0),
		});
		expect(pitLine).toContain("as_of 1970-01-01T00:16:40Z");
		expect(pitLine).toContain("snapshot snap-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
		expect(sourceLine).toContain("cutoff k=2026-09-17T00:00:00Z p=—");
		expect(sourceLine).toContain("source tushare");
		expect(sourceLine).toContain("exported 2026-09-18T08:00:00.000Z");
		expect(sourceLine).toContain("v0.1.0");
	});
});
