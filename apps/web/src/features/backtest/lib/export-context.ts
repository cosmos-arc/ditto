import { type BacktestReport, legacyBacktestUsage } from "../types";

/** Shared by single-run and comparison CSV/PNG source footers. */
export function backtestExportContext(runId: string, strategy: string, report: BacktestReport | undefined): string {
	const scope = report?.usageContext ?? legacyBacktestUsage;
	const identities = report?.strategyPromotion?.["data_catalog_identities"];
	const sources = Array.isArray(identities)
		? [
				...new Set(
					identities.flatMap((item: unknown) => {
						if (typeof item === "string") return [item];
						if (
							item &&
							typeof item === "object" &&
							"source_snapshot_id" in item &&
							typeof item.source_snapshot_id === "string" &&
							item.source_snapshot_id
						)
							return [item.source_snapshot_id];
						return [];
					}),
				),
			]
		: [];
	return [
		runId,
		strategy,
		scope.intendedUse === "research_protocol" ? "严格研究流程产物（资格另验）" : "受限历史研究",
		"严格历史可得性未认证；完成状态不授予策略晋级、信号启用或 Paper 授权",
		`报告区间 ${report?.periodStart || "未记录"} → ${report?.periodEnd || "未记录"}`,
		scope.samplePool === "recorded_input_union"
			? `实际输入集合 ${scope.inputInstrumentIds.length} 个标的，不代表历史全市场`
			: "样本池语义未记录",
		...scope.limitations,
		`来源快照 ${sources.join(" | ") || "未记录"}`,
		"完整标的清单、逐标的来源与时间守卫见同一 run 的 JSON 报告",
	].join(" · ");
}
