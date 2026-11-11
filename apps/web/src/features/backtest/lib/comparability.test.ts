import { describe, expect, it } from "vitest";
import type { BacktestReport, BacktestRun } from "../types";
import { legacyBacktestUsage } from "../types";
import { caliberFacts, partitionByComparability, type ReportReadOutcome } from "./comparability";

function run(runId: string): BacktestRun {
	return {
		runId,
		strategyId: "seed_etf_industry_rotation",
		strategyVersion: "4",
		mode: "backtest",
		status: "completed",
		startedAt: "2026-08-28T09:00:00Z",
		completedAt: "2026-08-28T09:14:00Z",
		errorMessage: "",
		parentRunId: "",
		benchmarkReturn: null,
		progressPct: 100,
		currentStep: "completed",
		completedDays: 60,
		totalDays: 60,
	};
}

function report(overrides: Partial<BacktestReport> = {}): BacktestReport {
	return {
		runId: "run-x",
		periodStart: "2026-01-05",
		periodEnd: "2026-03-31",
		initialCash: 1_000_000,
		finalNav: 1_120_000,
		dividendStatement: null,
		feeStatement: null,
		rebalanceFreq: "daily",
		usageContext: { ...legacyBacktestUsage },
		strategyPromotion: null,
		pitPolicy: null,
		alphaStats: null,
		tradeStats: null,
		...overrides,
	};
}

const published = (value: BacktestReport): ReportReadOutcome => ({ state: "published", report: value });

describe("caliberFacts", () => {
	it("records five axes when the report carries them", () => {
		const facts = caliberFacts(
			run("run-a"),
			published(
				report({
					usageContext: {
						intendedUse: "limited_historical_research",
						historicalAvailability: "not_certified",
						samplePool: "recorded_input_union",
						inputInstrumentIds: [510500, 510300],
						limitations: [],
					},
					feeStatement: {
						currency: "CNY",
						policy: "研究佣金包含经手费、证管费及券商留存。",
						rulesObservedAt: "2026-01-02",
						sourceRef: "rule-provider",
						finalCash: 1,
						fills: [],
					},
				}),
			),
		);
		expect(facts.values.assetPool).toBe("510300,510500");
		expect(facts.values.currency).toBe("CNY");
		expect(facts.values.period).toBe("2026-01-05 → 2026-03-31");
		expect(facts.values.returnDefinition).toBe("limited_historical_research · not_certified");
		expect(facts.values.feePolicy).toBe("研究佣金包含经手费、证管费及券商留存。");
	});

	it("marks axes unrecorded when the report does not carry them", () => {
		const facts = caliberFacts(run("run-a"), published(report()));
		expect(facts.values.assetPool).toBeNull();
		expect(facts.values.returnDefinition).toBeNull();
		expect(facts.values.feePolicy).toBeNull();
		// 期间是报告必载事实；币种可来自分红账本
		expect(facts.values.period).toBe("2026-01-05 → 2026-03-31");
	});

	it("reads currency from the dividend ledger when no fee bill exists", () => {
		const facts = caliberFacts(
			run("run-a"),
			published(
				report({
					dividendStatement: {
						currency: "CNY",
						policy: "",
						conversions: [],
						events: [],
						entries: [],
						balances: [],
					},
				}),
			),
		);
		expect(facts.values.currency).toBe("CNY");
	});

	it("period stays unrecorded when the report lacks period dates", () => {
		const facts = caliberFacts(run("run-a"), published(report({ periodStart: "", periodEnd: "" })));
		expect(facts.values.period).toBeNull();
	});
});

describe("partitionByComparability", () => {
	it("merges runs whose recorded axes agree and discloses symmetric unrecorded axes", () => {
		const partition = partitionByComparability([
			{ run: run("run-a"), reportOutcome: published(report()) },
			{ run: run("run-b"), reportOutcome: published(report()) },
		]);
		expect(partition.members).toEqual(["run-a", "run-b"]);
		expect(partition.excluded).toEqual([]);
		// 双方都未记录的轴如实披露为未核对，而不是假装可比
		expect(partition.unverifiedAxes).toEqual(["assetPool", "currency", "returnDefinition", "feePolicy"]);
	});

	it("separates a run whose recorded axis differs, naming the axis and both values", () => {
		const partition = partitionByComparability([
			{ run: run("run-a"), reportOutcome: published(report()) },
			{
				run: run("run-b"),
				reportOutcome: published(report({ periodStart: "2025-01-05", periodEnd: "2025-03-31" })),
			},
		]);
		expect(partition.members).toEqual(["run-a"]);
		expect(partition.excluded).toHaveLength(1);
		expect(partition.excluded[0]?.runId).toBe("run-b");
		expect(partition.excluded[0]?.reasons[0]).toContain("时间样本");
		expect(partition.excluded[0]?.reasons[0]).toContain("2026-01-05 → 2026-03-31");
		expect(partition.excluded[0]?.reasons[0]).toContain("2025-01-05 → 2025-03-31");
	});

	it("separates asymmetric knowledge: one run recorded an axis the anchor did not", () => {
		const partition = partitionByComparability([
			{ run: run("run-a"), reportOutcome: published(report()) },
			{
				run: run("run-b"),
				reportOutcome: published(
					report({
						usageContext: {
							intendedUse: "limited_historical_research",
							historicalAvailability: "not_certified",
							samplePool: "recorded_input_union",
							inputInstrumentIds: [510300],
							limitations: [],
						},
					}),
				),
			},
		]);
		expect(partition.members).toEqual(["run-a"]);
		expect(partition.excluded[0]?.reasons.join("\n")).toContain("资产池");
		expect(partition.excluded[0]?.reasons.join("\n")).toContain("未记录");
		expect(partition.excluded[0]?.reasons.join("\n")).toContain("510300");
	});

	it("always excludes runs without a resolved published report", () => {
		const partition = partitionByComparability([
			{ run: run("run-a"), reportOutcome: { state: "unpublished" } },
			{ run: run("run-b"), reportOutcome: { state: "pending" } },
			{ run: run("run-c"), reportOutcome: { state: "failed" } },
		]);
		expect(partition.members).toEqual([]);
		const reasons = partition.excluded.map((item) => item.reasons.join("\n"));
		// 未发布/读取失败 → 无法核对；读取中 → 尚未可知（不下「不可比」结论）
		expect(reasons[0]).toContain("report 未发布，口径无法核对");
		expect(reasons[1]).toContain("report 读取中，口径尚未可知");
		expect(reasons[2]).toContain("report 读取失败，口径无法核对");
	});

	it("anchors on the first published run so an unpublished head cannot block comparable pairs", () => {
		const partition = partitionByComparability([
			{ run: run("run-a"), reportOutcome: { state: "unpublished" } },
			{ run: run("run-b"), reportOutcome: published(report()) },
			{ run: run("run-c"), reportOutcome: published(report()) },
		]);
		expect(partition.members).toEqual(["run-b", "run-c"]);
		expect(partition.anchorRunId).toBe("run-b");
		expect(partition.excluded.map((item) => item.runId)).toEqual(["run-a"]);
	});

	it("reports every differing axis, not just the first", () => {
		const partition = partitionByComparability([
			{ run: run("run-a"), reportOutcome: published(report()) },
			{
				run: run("run-b"),
				reportOutcome: published(
					report({
						periodStart: "2025-01-05",
						periodEnd: "2025-03-31",
						feeStatement: {
							currency: "CNY",
							policy: "另一套费用口径",
							rulesObservedAt: "2025-01-02",
							sourceRef: "rule-provider",
							finalCash: 1,
							fills: [],
						},
					}),
				),
			},
		]);
		expect(partition.excluded[0]?.reasons).toHaveLength(3);
		expect(partition.excluded[0]?.reasons.join("\n")).toContain("时间样本不同");
		// 币种与费用口径同时呈现（一方记录、一方未记录也是不兼容）
		expect(partition.excluded[0]?.reasons.join("\n")).toContain("币种不同");
		expect(partition.excluded[0]?.reasons.join("\n")).toContain("费用口径不同");
	});
});
