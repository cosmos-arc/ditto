/** 跨层共用的 ISO 日历日期工具（route 校验与图表/行情窗口共用）。 */

/**
 * ISO 日历日期校验：严格 `YYYY-MM-DD` 且 `Date` 往返等值——正则放行的
 * `2026-13-45`/`2026-02-30` 这类假日期在 `Date.parse` 得 NaN，进日期
 * 算术会让 `toISOString` 抛 RangeError 炸掉调用方渲染。
 */
export function isValidIsoCalendarDate(value: string): boolean {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
	const parsed = Date.parse(`${value}T00:00:00Z`);
	return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}

/** ISO 日期前推 N 年（纯 UTC 日期算术；调用方保证输入已过日历校验）。 */
export function dateYearsBefore(date: string, years: number): string {
	const parsed = new Date(`${date}T00:00:00Z`);
	parsed.setUTCFullYear(parsed.getUTCFullYear() - years);
	return parsed.toISOString().slice(0, 10);
}
