import { render, screen } from "@testing-library/react";
import { describe, it } from "vitest";
import { ResearchPage } from "../components/research-page";
import { StatusBadge, getIcColor, getFactorStatusColor } from "../components/status-badge";
import { FactorHealthTable } from "../components/factor-health-table";
import { QuickActionGrid } from "../components/quick-action-grid";
import { BacktestList } from "../components/backtest-list";
import { ActiveExperiments } from "../components/active-experiments";
import type { FactorStatus } from "../types";

// ─── StatusBadge ────────────────────────────────────────────────

describe("StatusBadge", () => {
	it("renders the label text", () => {
		render(<StatusBadge status="stable" label="STABLE" />);
		expect(screen.getByText("STABLE")).toBeInTheDocument();
	});

	it("applies green token for stable status", () => {
		render(<StatusBadge status="stable" label="STABLE" />);
		const badge = screen.getByText("STABLE");
		expect(badge.className).toContain("text-green-500");
		expect(badge.className).toContain("bg-green-500/10");
		expect(badge.className).toContain("border-green-500/20");
	});

	it("applies green token for optimal status", () => {
		render(<StatusBadge status="optimal" label="OPTIMAL" />);
		const badge = screen.getByText("OPTIMAL");
		expect(badge.className).toContain("text-green-500");
	});

	it("applies amber token for decay status", () => {
		render(<StatusBadge status="decay" label="DECAY" />);
		const badge = screen.getByText("DECAY");
		expect(badge.className).toContain("text-amber-500");
		expect(badge.className).toContain("bg-amber-500/10");
		expect(badge.className).toContain("border-amber-500/20");
	});

	it("applies red token for failed status", () => {
		render(<StatusBadge status="failed" label="FAILED" />);
		const badge = screen.getByText("FAILED");
		expect(badge.className).toContain("text-red-500");
		expect(badge.className).toContain("bg-red-500/10");
		expect(badge.className).toContain("border-red-500/20");
	});
});

// ─── Helper functions ──────────────────────────────────────────

describe("getFactorStatusColor", () => {
	it("returns green for stable", () => {
		expect(getFactorStatusColor("stable")).toBe("text-green-500");
	});

	it("returns green for optimal", () => {
		expect(getFactorStatusColor("optimal")).toBe("text-green-500");
	});

	it("returns amber for decay", () => {
		expect(getFactorStatusColor("decay")).toBe("text-amber-500");
	});

	it("returns red for failed", () => {
		expect(getFactorStatusColor("failed")).toBe("text-red-500");
	});
});

describe("getIcColor", () => {
	it("returns green for IC > 0.02", () => {
		expect(getIcColor(0.042)).toBe("text-green-500");
	});

	it("returns amber for 0 < IC ≤ 0.02", () => {
		expect(getIcColor(0.012)).toBe("text-amber-500");
	});

	it("returns red for IC ≤ 0", () => {
		expect(getIcColor(-0.004)).toBe("text-red-500");
	});
});

// ─── FactorHealthTable ─────────────────────────────────────────

describe("FactorHealthTable", () => {
	it("renders table header", () => {
		render(<FactorHealthTable />);
		expect(screen.getByText("因子健康监控")).toBeInTheDocument();
	});

	it("renders all factor names", () => {
		render(<FactorHealthTable />);
		expect(screen.getByText("Alpha_EMA_Cross_V1")).toBeInTheDocument();
		expect(screen.getByText("Vol_Dispersion_30m")).toBeInTheDocument();
		expect(screen.getByText("NLP_Sentiment_Lag3")).toBeInTheDocument();
		expect(screen.getByText("Orderbook_Imbalance_1s")).toBeInTheDocument();
		expect(screen.getByText("Whale_Flow_Index")).toBeInTheDocument();
		expect(screen.getByText("Mean_Rev_Bollinger_4h")).toBeInTheDocument();
	});

	it("renders status summary counts", () => {
		render(<FactorHealthTable />);
		expect(screen.getByText("24 Optimal")).toBeInTheDocument();
		expect(screen.getByText("3 Decaying")).toBeInTheDocument();
		expect(screen.getByText("1 Failed")).toBeInTheDocument();
	});

	it("renders table column headers", () => {
		render(<FactorHealthTable />);
		expect(screen.getByText("Factor Name")).toBeInTheDocument();
		expect(screen.getByText("Category")).toBeInTheDocument();
		expect(screen.getByText("IC (Mean)")).toBeInTheDocument();
		expect(screen.getByText("IR")).toBeInTheDocument();
		expect(screen.getByText("Decay (T+1)")).toBeInTheDocument();
		expect(screen.getByText("Status")).toBeInTheDocument();
	});

	it("renders footer with expand link", () => {
		render(<FactorHealthTable />);
		expect(screen.getByText("Showing 6 of 28 factors active in research")).toBeInTheDocument();
		expect(screen.getByText("Expand Monitor")).toBeInTheDocument();
	});

	it("renders status badges for each factor", () => {
		render(<FactorHealthTable />);
		expect(screen.getAllByText("STABLE")).toHaveLength(3);
		expect(screen.getByText("OPTIMAL")).toBeInTheDocument();
		expect(screen.getByText("DECAY")).toBeInTheDocument();
		expect(screen.getByText("FAILED")).toBeInTheDocument();
	});
});

// ─── QuickActionGrid ───────────────────────────────────────────

describe("QuickActionGrid", () => {
	it("renders all action cards", () => {
		render(<QuickActionGrid />);
		expect(screen.getByText("New Backtest")).toBeInTheDocument();
		expect(screen.getByText("Factor Analysis")).toBeInTheDocument();
		expect(screen.getByText("Strategy Config")).toBeInTheDocument();
	});

	it("renders action descriptions", () => {
		render(<QuickActionGrid />);
		expect(screen.getByText("Launch multi-threaded simulation")).toBeInTheDocument();
		expect(screen.getByText("IC Decay & Collinearity checks")).toBeInTheDocument();
		expect(screen.getByText("Manage weights and risk limits")).toBeInTheDocument();
	});

	it("action cards are interactive buttons", () => {
		render(<QuickActionGrid />);
		const buttons = screen.getAllByRole("button");
		expect(buttons).toHaveLength(3);
	});
});

// ─── BacktestList ───────────────────────────────────────────────

describe("BacktestList", () => {
	it("renders section header", () => {
		render(<BacktestList />);
		expect(screen.getByText("Recent Backtests")).toBeInTheDocument();
	});

	it("renders all backtest run IDs", () => {
		render(<BacktestList />);
		expect(screen.getByText("#RUN-0942")).toBeInTheDocument();
		expect(screen.getByText("#RUN-0938")).toBeInTheDocument();
		expect(screen.getByText("#RUN-0912")).toBeInTheDocument();
	});

	it("renders strategy names", () => {
		render(<BacktestList />);
		expect(screen.getByText("Momentum_Arbitrage_v4.2")).toBeInTheDocument();
		expect(screen.getByText("Mean_Rev_Scalper_Test")).toBeInTheDocument();
		expect(screen.getByText("X-Modal_Sentiment_HFT")).toBeInTheDocument();
	});

	it("renders metric labels", () => {
		render(<BacktestList />);
		// MetricTile renders "Sharpe" and "Max DD" for each run (3 runs × 2 = 6)
		const sharpeLabels = screen.getAllByText("Sharpe");
		const maxDdLabels = screen.getAllByText("Max DD");
		expect(sharpeLabels).toHaveLength(3);
		expect(maxDdLabels).toHaveLength(3);
	});

	it("renders view all link", () => {
		render(<BacktestList />);
		expect(screen.getByText("View All Runs")).toBeInTheDocument();
	});
});

// ─── ActiveExperiments ─────────────────────────────────────────

describe("ActiveExperiments", () => {
	it("renders section header", () => {
		render(<ActiveExperiments />);
		expect(screen.getByText("Active Experiments")).toBeInTheDocument();
	});

	it("renders active count badge", () => {
		render(<ActiveExperiments />);
		expect(screen.getByText("3 ACTIVE")).toBeInTheDocument();
	});

	it("renders experiment names", () => {
		render(<ActiveExperiments />);
		expect(screen.getByText("GPU-Worker_Alpha_Search")).toBeInTheDocument();
		expect(screen.getByText("Monte_Carlo_Stress_Test")).toBeInTheDocument();
	});

	it("renders progress percentages", () => {
		render(<ActiveExperiments />);
		expect(screen.getByText("82%")).toBeInTheDocument();
		expect(screen.getByText("45%")).toBeInTheDocument();
	});
});

// ─── ResearchPage (composition) ────────────────────────────────

describe("ResearchPage", () => {
	it("renders filter bar with category pills", () => {
		render(<ResearchPage />);
		expect(screen.getByText("All Factors")).toBeInTheDocument();
		expect(screen.getByText("Factor Categories:")).toBeInTheDocument();
		// Categories from filter bar
		expect(screen.getAllByText("Momentum").length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText("Mean Reversion")).toBeInTheDocument();
		expect(screen.getAllByText("Sentiment").length).toBeGreaterThanOrEqual(1);
		expect(screen.getByText("Volume Profile")).toBeInTheDocument();
	});

	it("renders filter bar action buttons", () => {
		render(<ResearchPage />);
		expect(screen.getByText("Filter")).toBeInTheDocument();
		expect(screen.getByText("New Factor")).toBeInTheDocument();
	});

	it("renders all major sections", () => {
		render(<ResearchPage />);
		expect(screen.getByText("因子健康监控")).toBeInTheDocument();
		expect(screen.getByText("New Backtest")).toBeInTheDocument();
		expect(screen.getByText("Recent Backtests")).toBeInTheDocument();
		expect(screen.getByText("Active Experiments")).toBeInTheDocument();
	});
});
