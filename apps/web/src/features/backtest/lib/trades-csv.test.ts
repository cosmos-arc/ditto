import { describe, expect, it } from "vitest";
import type { BacktestTradeRecord } from "../types";
import { toTradesCsv } from "./trades-csv";

const trades: BacktestTradeRecord[] = [
	{
		tradeDate: "2025-03-03",
		instrumentId: 600519,
		direction: "long",
		entryDate: "2025-01-06",
		exitDate: "2025-03-03",
		entryPrice: 1480.0,
		exitPrice: 1612.5,
		quantity: 400,
		pnl: 53000,
	},
	{
		tradeDate: "2025-04-10",
		instrumentId: 510300,
		direction: "short",
		entryDate: "2025-02-14",
		exitDate: "2025-04-10",
		entryPrice: 3.9,
		exitPrice: 3.72,
		quantity: 100000,
		pnl: -18000.5,
	},
];

describe("toTradesCsv", () => {
	it("mirrors the trades table source with run identity header lines", () => {
		const csv = toTradesCsv("bt-001", trades);
		const lines = csv.split("\n");
		expect(lines[0]).toBe("# run_id=bt-001");
		expect(lines[1]).toBe("# source=GET /api/v1/backtests/runs/bt-001/trades（与成交记录表同一读取结果）");
		expect(lines[2]).toBe(
			"trade_date,instrument_id,direction,entry_date,entry_price,exit_date,exit_price,quantity,pnl",
		);
		expect(lines[3]).toBe("2025-03-03,600519,long,2025-01-06,1480,2025-03-03,1612.5,400,53000");
		expect(lines[4]).toBe("2025-04-10,510300,short,2025-02-14,3.9,2025-04-10,3.72,100000,-18000.5");
	});

	it("escapes cells that could break the csv structure", () => {
		const tricky: BacktestTradeRecord[] = [
			{
				tradeDate: "2025-03-03",
				instrumentId: 1,
				direction: 'long, "quoted"',
				entryDate: "2025-01-06",
				exitDate: "2025-03-03",
				entryPrice: 1,
				exitPrice: 1,
				quantity: 1,
				pnl: 0,
			},
		];
		const line = toTradesCsv("bt-1", tricky).split("\n")[3] ?? "";
		expect(line).toContain('"long, ""quoted"""');
	});

	it("still emits identity and header when the run has no closed trades", () => {
		const csv = toTradesCsv("bt-empty", []);
		expect(csv).toContain("# run_id=bt-empty");
		expect(csv).toContain("trade_date,instrument_id,direction");
		expect(csv.split("\n")).toHaveLength(3);
	});
});
