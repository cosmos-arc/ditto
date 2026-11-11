import type { BacktestReport, BacktestRun } from "../types";

/**
 * 普通回测比较前的口径核对（资产池、币种、时间样本、收益定义、费用）。
 *
 * 全部事实直接来自各 run 已发布 report 的既读结果，不另发请求、不在前端
 * 重算金融规则：
 * - 资产池 = usage_context.input_instrument_ids（引擎清单的实际输入集合，
 *   升序去重；空集合视为未记录——真实运行至少消费一个标的）；
 * - 币种 = 逐笔费用账单或分红账本声明的币种；
 * - 时间样本 = 报告期间（start → end）；
 * - 收益定义 = 用途/历史可得性（usage_context 已记录时）；
 * - 费用口径 = 费用账单 policy。
 *
 * 合并规则：只有已发布 report 且五轴「同记录同值」的 run 才并入同一叠加；
 * 双方都未记录的轴不阻断合并，但作为未核对轴披露；任一侧记录而另一侧
 * 未记录、或双方记录不同，即为不兼容，分开解释。不改起点、不制造排名。
 */

export const CALIBER_AXES = ["assetPool", "currency", "period", "returnDefinition", "feePolicy"] as const;

export type CaliberAxis = (typeof CALIBER_AXES)[number];

export const CALIBER_AXIS_LABELS: Readonly<Record<CaliberAxis, string>> = {
	assetPool: "资产池",
	currency: "币种",
	period: "时间样本",
	returnDefinition: "收益定义",
	feePolicy: "费用口径",
};

/** report 读取结果：已发布 / 未发布（404）/ 读取中 / 读取失败。 */
export type ReportReadOutcome =
	| { readonly state: "published"; readonly report: BacktestReport }
	| { readonly state: "unpublished" }
	| { readonly state: "pending" }
	| { readonly state: "failed" };

export type CaliberFacts = {
	readonly runId: string;
	/** 轴值统一为可展示字符串；null = 该轴未记录。 */
	readonly values: Readonly<Record<CaliberAxis, string | null>>;
};

export function caliberFacts(run: BacktestRun, outcome: ReportReadOutcome): CaliberFacts {
	const report = outcome.state === "published" ? outcome.report : undefined;
	const usage = report?.usageContext;
	const inputIds = [...new Set(usage?.inputInstrumentIds ?? [])]
		.filter((id) => Number.isSafeInteger(id) && id > 0)
		.sort((left, right) => left - right);
	const usageRecorded = inputIds.length > 0;
	const period = report?.periodStart && report?.periodEnd ? `${report.periodStart} → ${report.periodEnd}` : null;
	return {
		runId: run.runId,
		values: {
			assetPool: usageRecorded ? inputIds.join(",") : null,
			currency: report?.feeStatement?.currency ?? report?.dividendStatement?.currency ?? null,
			period,
			returnDefinition: usageRecorded
				? `${usage?.intendedUse ?? "unknown"} · ${usage?.historicalAvailability ?? "unknown"}`
				: null,
			feePolicy: report?.feeStatement?.policy ?? null,
		},
	};
}

export type ComparabilityExcluded = {
	readonly runId: string;
	readonly reasons: readonly string[];
};

export type ComparabilityPartition = {
	/** 锚点：首个已发布 report 的 run（按选择顺序）。 */
	readonly anchorRunId: string | null;
	/** 与锚点五轴兼容、并入同一叠加的 run id（含锚点）。 */
	readonly members: readonly string[];
	/** 不并入叠加的 run 及逐轴原因。 */
	readonly excluded: readonly ComparabilityExcluded[];
	/** 成员间双方都未记录的轴：合并成立但未核对，需要披露。 */
	readonly unverifiedAxes: readonly CaliberAxis[];
	/** 逐 run 口径事实（表格展示与导出同源）。 */
	readonly facts: readonly CaliberFacts[];
};

function describeOutcome(outcome: ReportReadOutcome): string | null {
	if (outcome.state === "published") return null;
	if (outcome.state === "unpublished") return "report 未发布，口径无法核对";
	if (outcome.state === "pending") return "report 读取中，口径尚未可知";
	return "report 读取失败，口径无法核对";
}

export function partitionByComparability(
	entries: readonly { readonly run: BacktestRun; readonly reportOutcome: ReportReadOutcome }[],
): ComparabilityPartition {
	const facts = entries.map((entry) => caliberFacts(entry.run, entry.reportOutcome));
	const anchorIndex = entries.findIndex((entry) => entry.reportOutcome.state === "published");
	const members: string[] = [];
	const excluded: ComparabilityExcluded[] = [];
	const unverifiedAxes: CaliberAxis[] = [];

	if (anchorIndex >= 0) {
		const anchor = facts[anchorIndex]!;
		members.push(anchor.runId);
		for (const fact of facts.slice(0, anchorIndex)) {
			const outcome = entries[facts.indexOf(fact)]?.reportOutcome;
			excluded.push({
				runId: fact.runId,
				reasons: [describeOutcome(outcome ?? { state: "failed" }) ?? "report 未发布，口径无法核对"],
			});
		}
		for (let index = anchorIndex + 1; index < entries.length; index += 1) {
			const fact = facts[index]!;
			const outcomeReason = describeOutcome(entries[index]!.reportOutcome);
			if (outcomeReason !== null) {
				excluded.push({ runId: fact.runId, reasons: [outcomeReason] });
				continue;
			}
			const reasons: string[] = [];
			for (const axis of CALIBER_AXES) {
				const anchorValue = anchor.values[axis];
				const value = fact.values[axis];
				if (anchorValue === value) {
					if (anchorValue === null && !unverifiedAxes.includes(axis)) unverifiedAxes.push(axis);
					continue;
				}
				reasons.push(`${CALIBER_AXIS_LABELS[axis]}不同：${anchorValue ?? "未记录"} ≠ ${value ?? "未记录"}`);
			}
			if (reasons.length > 0) {
				excluded.push({ runId: fact.runId, reasons });
			} else {
				members.push(fact.runId);
			}
		}
	} else {
		for (const fact of facts) {
			const outcomeReason = describeOutcome(
				entries[facts.indexOf(fact)]?.reportOutcome ?? {
					state: "failed",
				},
			);
			excluded.push({ runId: fact.runId, reasons: [outcomeReason ?? "report 未发布，口径无法核对"] });
		}
	}

	return {
		anchorRunId: anchorIndex >= 0 ? entries[anchorIndex]!.run.runId : null,
		members,
		excluded,
		unverifiedAxes,
		facts,
	};
}
