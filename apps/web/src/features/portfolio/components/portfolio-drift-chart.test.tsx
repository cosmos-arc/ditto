import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PortfolioComparison } from "../api/portfolio-comparison";
import { driftRows, driftScaleBucket, formatDriftBps, isDriftEmpty, maxAbsDriftBps } from "../lib/drift-chart-mapping";
import { PortfolioDriftChart } from "./portfolio-drift-chart";

/** 最小可用 comparison：三组合两两漂移面（标的 600519/510300 + 现金）。 */
function comparisonFixture(overrides: Partial<PortfolioComparison["model_vs_paper"]> = {}): PortfolioComparison {
	const surface = (
		kind: "model_vs_paper" | "model_vs_manual" | "paper_vs_manual",
		drifts: [string, string],
		cash: string,
		total: string,
	) => ({
		comparison_kind: kind,
		baseline_portfolio_id: "model-main",
		observed_portfolio_id: "paper-main",
		total_abs_drift_bps: total,
		cash_drift_bps: cash,
		items: [
			{
				instrument_id: 600519,
				baseline_weight: "0.50",
				observed_weight: "0.40",
				drift_weight: "-0.10",
				drift_bps: drifts[0],
			},
			{
				instrument_id: 510300,
				baseline_weight: "0.30",
				observed_weight: "0.35",
				drift_weight: "0.05",
				drift_bps: drifts[1],
			},
		],
		attribution: {
			unfilled_bps: "0",
			slippage_amount: "0",
			fee_amount: "0",
			risk_blocked_bps: "0",
			user_choice_bps: "0",
		},
		...overrides,
	});
	return {
		strategy_id: "strategy-1",
		as_of: "2026-08-31",
		valuation_snapshot_id: "valuation:abc",
		source_snapshot_ids: ["snapshot:stock"],
		model: {} as PortfolioComparison["model"],
		paper: {} as PortfolioComparison["paper"],
		manual: {} as PortfolioComparison["manual"],
		model_vs_paper: surface("model_vs_paper", ["-1000", "500"], "200", "1700"),
		model_vs_manual: surface("model_vs_manual", ["-2000", "800"], "400", "3200"),
		paper_vs_manual: surface("paper_vs_manual", ["-500", "250"], "100", "850"),
	};
}

describe("drift-chart-mapping", () => {
	it("builds the instrument union plus a cash row with per-pair drifts", () => {
		const rows = driftRows(comparisonFixture());
		expect(rows.map((row) => row.label)).toEqual(["#510300", "#600519", "现金"]);
		expect(rows[1]?.driftBps.model_vs_paper).toBe(-1000);
		expect(rows[2]?.driftBps.model_vs_manual).toBe(400);
	});

	it("scales against the max visible |bps| and detects the no-drift surface", () => {
		const rows = driftRows(comparisonFixture());
		expect(maxAbsDriftBps(rows, ["model_vs_paper"])).toBe(1000);
		expect(maxAbsDriftBps(rows, ["model_vs_manual", "paper_vs_manual"])).toBe(2000);
		const calm = comparisonFixture();
		for (const pair of ["model_vs_paper", "model_vs_manual", "paper_vs_manual"] as const) {
			calm[pair] = { ...calm[pair], items: [], cash_drift_bps: "0" };
		}
		expect(isDriftEmpty(calm)).toBe(true);
	});

	it("formats signed bps with tabular minus", () => {
		expect(formatDriftBps(-1000)).toBe("−1000.0 bps");
		expect(formatDriftBps(250)).toBe("+250.0 bps");
	});

	it("buckets bar widths into discrete scale steps", () => {
		expect(driftScaleBucket(undefined, 1000)).toBe(0);
		// 零漂移不画条：不得借最小非零档虚示超配
		expect(driftScaleBucket(0, 1000)).toBe(0);
		expect(driftScaleBucket(100, 0)).toBe(0);
		expect(driftScaleBucket(10, 1000)).toBe(1);
		expect(driftScaleBucket(600, 1000)).toBe(5);
		expect(driftScaleBucket(1000, 1000)).toBe(8);
		expect(driftScaleBucket(5000, 1000)).toBe(8);
	});
});

describe("PortfolioDriftChart", () => {
	it("renders the drift matrix with as_of visibility and pair totals", () => {
		render(<PortfolioDriftChart comparison={comparisonFixture()} />);
		const chart = screen.getByTestId("portfolio-drift-chart");
		expect(chart).toBeInTheDocument();
		// PIT 语义在图上可见（AC：as_of 一致性可见）
		expect(screen.getByTestId("drift-as-of")).toHaveTextContent("AS OF 2026-08-31 · 同快照对比");
		expect(chart).toHaveTextContent("valuation:abc");
		// 列头三组两两对比 + 总漂移
		expect(within(chart).getByText(/Σ \+1700\.0 bps/)).toBeInTheDocument();
		// 行：标的并集 + 现金
		expect(screen.getByTestId("drift-cell-instrument-600519-model_vs_paper")).toHaveTextContent("−1000.0 bps");
		expect(screen.getByTestId("drift-cell-cash-model_vs_manual")).toHaveTextContent("+400.0 bps");
	});

	it("toggles a pair column off via the legend-style column header", () => {
		render(<PortfolioDriftChart comparison={comparisonFixture()} />);
		const pairToggle = screen.getByRole("button", { name: /MODEL → PAPER/ });
		expect(pairToggle).toHaveAttribute("aria-pressed", "true");
		fireEvent.click(pairToggle);
		expect(pairToggle).toHaveAttribute("aria-pressed", "false");
		const cell = screen.getByTestId("drift-cell-instrument-600519-model_vs_paper");
		expect(cell).toHaveTextContent("");
		// 其余列不受影响
		expect(screen.getByTestId("drift-cell-instrument-600519-model_vs_manual")).toHaveTextContent("−2000.0 bps");
	});

	it("allows hiding every column and shows an explicit all-hidden state", () => {
		render(<PortfolioDriftChart comparison={comparisonFixture()} />);
		// 三列全部可隐（不做静默拒绝），矩阵进入显式空态
		for (const label of [/MODEL → PAPER/, /MODEL → MANUAL/, /PAPER → MANUAL/]) {
			const column = screen.getByRole("button", { name: label });
			fireEvent.click(column);
			expect(column).toHaveAttribute("aria-pressed", "false");
		}
		expect(screen.getByText("全部对比列已隐藏——点击任一列头恢复")).toBeInTheDocument();
		// 列头仍在，可恢复
		fireEvent.click(screen.getByRole("button", { name: /MODEL → MANUAL/ }));
		expect(screen.queryByText("全部对比列已隐藏——点击任一列头恢复")).not.toBeInTheDocument();
		expect(screen.getByTestId("drift-cell-instrument-600519-model_vs_manual")).toHaveTextContent("−2000.0 bps");
	});

	it("keeps the structured empty state when all drift surfaces are empty", () => {
		const calm = comparisonFixture();
		for (const pair of ["model_vs_paper", "model_vs_manual", "paper_vs_manual"] as const) {
			calm[pair] = { ...calm[pair], items: [], cash_drift_bps: "0" };
		}
		render(<PortfolioDriftChart comparison={calm} />);
		const chart = screen.getByTestId("portfolio-drift-chart");
		expect(chart).toHaveAttribute("data-state", "drift-empty");
		expect(chart).toHaveTextContent("无权重漂移数据");
	});
});
