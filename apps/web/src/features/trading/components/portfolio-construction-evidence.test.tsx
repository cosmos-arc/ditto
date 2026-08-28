import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createDailyDecisionV3ViewModel } from "./daily-decision-v3.fixture";
import { PortfolioConstructionEvidence } from "./portfolio-construction-evidence";

describe("PortfolioConstructionEvidence", () => {
	it("renders current/target/delta and the exact solver evidence", () => {
		const { container } = render(<PortfolioConstructionEvidence decision={createDailyDecisionV3ViewModel()} />);

		expect(screen.getByText("clarabel")).toBeInTheDocument();
		expect(screen.getByText("sha256:policy-r4")).toBeInTheDocument();
		expect(screen.getByText("25.00%")).toBeInTheDocument();
		expect(screen.getByText("35.00%")).toBeInTheDocument();
		expect(screen.getByText("+10.00%")).toBeInTheDocument();
		expect(screen.getByText("当前契约仅提供 policy digest")).toBeInTheDocument();
		expect(screen.getByText("总敞口")).toBeInTheDocument();
		expect(screen.getByText("¥750,000.00 · 75.00%")).toBeInTheDocument();
		expect(screen.getByText("现金基线")).toBeInTheDocument();
		expect(screen.getByText("¥250,000.00 · 25.00%")).toBeInTheDocument();
		expect(container.querySelector("[data-slot='portfolio-construction']")).toBeInTheDocument();
	});

	it("keeps solver failure visible and links back to blocking reasons", () => {
		const decision = createDailyDecisionV3ViewModel({
			readiness: { status: "blocked", reportedStatus: "blocked", blockingReasons: ["SOLVER_INFEASIBLE"] },
			portfolioConstruction: {
				status: "failed",
				solver: "clarabel",
				solverVersion: "0.10",
				mode: "risk_budget",
				solverStatus: "infeasible",
				durationMs: 8,
				policyDigest: "sha256:policy-r4",
				failureCode: "SOLVER_INFEASIBLE",
			},
		});
		render(<PortfolioConstructionEvidence decision={decision} />);

		expect(screen.getAllByText("SOLVER_INFEASIBLE").length).toBeGreaterThan(0);
		expect(screen.getByRole("link", { name: "查看阻塞原因" })).toHaveAttribute(
			"href",
			"/trading?strategy_id=strategy-r4&account_id=paper-r4&trade_date=2026-08-19",
		);
	});
});
