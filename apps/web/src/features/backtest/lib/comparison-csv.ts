import { CALIBER_AXIS_LABELS, type ComparabilityPartition } from "./comparability";
import type { MultiRunMetricsRow } from "./multi-run-mapping";

/** CSV 单元格转义：与成交导出同一规则（RFC 4180）。 */
function csvCell(value: string): string {
	if (/[",\r\n]/u.test(value)) return `"${value.replaceAll('"', '""')}"`;
	return value;
}

/**
 * 对比视图同源 CSV：指标列与差异表展示串一致，口径列与口径核对表一致，
 * 结论列说明并入/分开解释的原因；身份注释行携带集合与未核对轴披露。
 */
export function toComparisonCsv(rows: readonly MultiRunMetricsRow[], partition: ComparabilityPartition): string {
	const factByRun = new Map(partition.facts.map((fact) => [fact.runId, fact]));
	const reasonByRun = new Map(partition.excluded.map((item) => [item.runId, item.reasons]));
	const unverified =
		partition.unverifiedAxes.length > 0
			? `# unverified_axes=${partition.unverifiedAxes.map((axis) => CALIBER_AXIS_LABELS[axis]).join("、")}（成员双方均未记录，未核对）`
			: "# unverified_axes=无";
	const header = [
		"run_id",
		"strategy_id",
		"period",
		"initial_cash",
		"final_nav",
		"annualized_return",
		"max_drawdown",
		"sharpe",
		"report_published",
		"asset_pool",
		"currency",
		"time_sample",
		"return_definition",
		"fee_policy",
		"comparison_conclusion",
	];
	const dataRows = rows.map((row) => {
		const fact = factByRun.get(row.runId);
		const reasons = reasonByRun.get(row.runId);
		const conclusion = reasons ? `未并入叠加：${reasons.join("；")}` : "并入叠加";
		return [
			row.runId,
			row.strategyId,
			row.period,
			row.initialCash,
			row.finalNav,
			row.annualizedReturn,
			row.maxDrawdown,
			row.sharpe,
			String(row.reportPublished),
			fact?.values.assetPool ?? "未记录",
			fact?.values.currency ?? "未记录",
			fact?.values.period ?? "未记录",
			fact?.values.returnDefinition ?? "未记录",
			fact?.values.feePolicy ?? "未记录",
			conclusion,
		]
			.map((cell) => csvCell(cell))
			.join(",");
	});
	return [
		`# comparison=${rows.map((row) => row.runId).join(",")}`,
		"# caliber=资产池/币种/时间样本/收益定义/费用；同记录同值才并入同一叠加",
		unverified,
		header.join(","),
		...dataRows,
	].join("\n");
}
