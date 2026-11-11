import { describe, expect, it } from "vitest";
import type { CaliberFacts, ComparabilityPartition } from "./comparability";
import { toComparisonCsv } from "./comparison-csv";
import type { MultiRunMetricsRow } from "./multi-run-mapping";

const rows: MultiRunMetricsRow[] = [
	{
		runId: "run-a",
		strategyId: "seed_etf_industry_rotation",
		period: "2026-01-05 → 2026-03-31",
		initialCash: "1,000,000",
		finalNav: "1,120,000",
		annualizedReturn: "18.20%",
		maxDrawdown: "-12.50%",
		sharpe: "1.47",
		reportPublished: true,
	},
	{
		runId: "run-b",
		strategyId: "seed_etf_industry_rotation",
		period: "—",
		initialCash: "—",
		finalNav: "—",
		annualizedReturn: "未发布",
		maxDrawdown: "—",
		sharpe: "—",
		reportPublished: false,
	},
];

const facts: CaliberFacts[] = [
	{
		runId: "run-a",
		values: {
			assetPool: "510300",
			currency: "CNY",
			period: "2026-01-05 → 2026-03-31",
			returnDefinition: "limited_historical_research · not_certified",
			feePolicy: "研究佣金包含经手费、证管费及券商留存。",
		},
	},
	{
		runId: "run-b",
		values: {
			assetPool: null,
			currency: null,
			period: "2026-01-05 → 2026-03-31",
			returnDefinition: null,
			feePolicy: null,
		},
	},
];

const partition: ComparabilityPartition = {
	anchorRunId: "run-a",
	members: ["run-a"],
	excluded: [{ runId: "run-b", reasons: ["资产池不同：510300 ≠ 未记录"] }],
	unverifiedAxes: [],
	facts,
};

describe("toComparisonCsv", () => {
	it("exports metric cells exactly as displayed plus caliber axes and conclusion", () => {
		const csv = toComparisonCsv(rows, partition);
		const lines = csv.split("\n");
		expect(lines[0]).toBe("# comparison=run-a,run-b");
		expect(lines[1]).toBe("# caliber=资产池/币种/时间样本/收益定义/费用；同记录同值才并入同一叠加");
		expect(lines[2]).toBe("# unverified_axes=无");
		expect(lines[3]).toBe(
			"run_id,strategy_id,period,initial_cash,final_nav,annualized_return,max_drawdown,sharpe,report_published,asset_pool,currency,time_sample,return_definition,fee_policy,comparison_conclusion",
		);
		// 表格展示串原样导出（含千分位逗号的单元格按 RFC 4180 加引号）
		expect(lines[4]).toBe(
			'run-a,seed_etf_industry_rotation,2026-01-05 → 2026-03-31,"1,000,000","1,120,000",18.20%,-12.50%,1.47,true,510300,CNY,2026-01-05 → 2026-03-31,limited_historical_research · not_certified,研究佣金包含经手费、证管费及券商留存。,并入叠加',
		);
		expect(lines[5]).toContain("run-b,seed_etf_industry_rotation,—,—,—,未发布,—,—,false");
		expect(lines[5]).toContain("未并入叠加：资产池不同：510300 ≠ 未记录");
		// 未记录轴在导出中如实标注
		expect(lines[5]).toContain("未记录,未记录,2026-01-05 → 2026-03-31,未记录,未记录");
	});

	it("discloses symmetric unrecorded axes in the identity header", () => {
		const csv = toComparisonCsv(rows, {
			...partition,
			members: ["run-a", "run-b"],
			excluded: [],
			unverifiedAxes: ["assetPool", "feePolicy"],
		});
		expect(csv).toContain("# unverified_axes=资产池、费用口径（成员双方均未记录，未核对）");
	});
});
