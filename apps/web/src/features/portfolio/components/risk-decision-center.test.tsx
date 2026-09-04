import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createDailyDecisionV3ViewModel } from "./daily-decision-v3.fixture";
import { RiskDecisionCenter } from "./risk-decision-center";

describe("RiskDecisionCenter", () => {
	it("renders ES/VaR, factor contribution, stress, reconciliation, and PIT provenance", () => {
		const { container } = render(<RiskDecisionCenter decision={createDailyDecisionV3ViewModel()} />);

		expect(screen.getByText("Historical ES99")).toBeInTheDocument();
		expect(screen.getByText("Parametric VaR99")).toBeInTheDocument();
		expect(screen.getByText("market")).toBeInTheDocument();
		expect(screen.getByText("总风险")).toBeInTheDocument();
		expect(screen.getByText("12.00%")).toBeInTheDocument();
		expect(screen.getByText("Euler residual")).toBeInTheDocument();
		expect(screen.getByText("0.0100%")).toBeInTheDocument();
		expect(screen.getByText("Monte Carlo seed: 42")).toBeInTheDocument();
		expect(screen.getByText("liquidity_crunch")).toBeInTheDocument();
		expect(screen.getByText("对账一致")).toBeInTheDocument();
		expect(screen.getByText("decision time")).toBeInTheDocument();
		expect(screen.getByText("2026-08-18T07:00:00Z")).toBeInTheDocument();
		expect(screen.getByText("generated at")).toBeInTheDocument();
		expect(screen.getByText("2026-08-18T07:01:00Z")).toBeInTheDocument();
		expect(screen.getByText("source snapshots")).toBeInTheDocument();
		expect(screen.getByText("snapshot-bars-r4")).toBeInTheDocument();
		expect(screen.getByText("2026-08-18T06:50:00Z")).toBeInTheDocument();
		expect(container.querySelector("[data-slot='risk-tail']")).toBeInTheDocument();
		expect(container.querySelector("[data-slot='risk-factor']")).toBeInTheDocument();
		expect(container.querySelector("[data-slot='risk-stress']")).toBeInTheDocument();
	});

	it("fails closed for unavailable factors, missing scenarios, reconciliation mismatch, and missing provenance", () => {
		const decision = createDailyDecisionV3ViewModel({
			factorRisk: {
				availability: "unavailable",
				totalRisk: null,
				marginalContributions: {},
				percentageContributions: {},
				eulerResidual: null,
			},
			stressTests: {
				catalogVersion: "stress-v3",
				losses: {},
				unavailableScenarios: ["liquidity_crunch"],
			},
			reconciliation: {
				status: "mismatch",
				differences: ["position_total"],
				alertIdempotencyKey: "alert-r4",
			},
			provenance: {
				decisionTime: null,
				knowledgeCutoff: null,
				publicationCutoff: null,
				sourceSnapshotIds: [],
				generatedAt: null,
				complete: false,
			},
			completeness: {
				status: "blocked",
				issues: ["PIT_PROVENANCE_INCOMPLETE", "RECONCILIATION_MISMATCH"],
			},
		});
		render(<RiskDecisionCenter decision={decision} />);

		expect(screen.getByText("因子风险不可用")).toBeInTheDocument();
		expect(screen.getByText("场景不可用：liquidity_crunch")).toBeInTheDocument();
		expect(screen.getByText("对账不一致")).toBeInTheDocument();
		expect(screen.getByText("PIT provenance 不完整")).toBeInTheDocument();
		expect(screen.getAllByRole("alert").length).toBeGreaterThanOrEqual(3);
	});
});
