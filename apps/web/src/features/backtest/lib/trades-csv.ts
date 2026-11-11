import type { BacktestTradeRecord } from "../types";

/** CSV 单元格转义：含逗号/引号/换行时按 RFC 4180 加引号（值内引号翻倍）。 */
function csvCell(value: string | number): string {
	const text = String(value);
	if (/[",\r\n]/u.test(text)) return `"${text.replaceAll('"', '""')}"`;
	return text;
}

/**
 * 成交记录表的同源 CSV 导出：行数据直接来自成交表消费的同一读取结果，
 * 不重算、不排序、不补列；身份以注释行携带，便于导出物独立归因。
 */
export function toTradesCsv(runId: string, trades: readonly BacktestTradeRecord[]): string {
	const header = [
		"trade_date",
		"instrument_id",
		"direction",
		"entry_date",
		"entry_price",
		"exit_date",
		"exit_price",
		"quantity",
		"pnl",
	];
	const rows = trades.map((trade) =>
		[
			trade.tradeDate,
			trade.instrumentId,
			trade.direction,
			trade.entryDate,
			trade.entryPrice,
			trade.exitDate,
			trade.exitPrice,
			trade.quantity,
			trade.pnl,
		]
			.map((cell) => csvCell(cell))
			.join(","),
	);
	return [
		`# run_id=${runId}`,
		`# source=GET /api/v1/backtests/runs/${runId}/trades（与成交记录表同一读取结果）`,
		header.join(","),
		...rows,
	].join("\r\n");
}
