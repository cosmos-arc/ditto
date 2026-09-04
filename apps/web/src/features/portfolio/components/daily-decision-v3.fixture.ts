import type { DailyDecisionV3ViewModel } from "../types/daily-decision-v3";

export function createDailyDecisionV3ViewModel(
	overrides: Partial<DailyDecisionV3ViewModel> = {},
): DailyDecisionV3ViewModel {
	const base: DailyDecisionV3ViewModel = {
		identity: {
			strategyId: "strategy-r4",
			strategyVersion: "7",
			signalDate: "2026-08-18",
			tradeDate: "2026-08-19",
			accountId: "paper-r4",
			sleeveId: "sleeve-r4",
		},
		readiness: { status: "ready", reportedStatus: "ready", blockingReasons: [] },
		data: { freshness: "ready", qualityState: "passed", snapshotIds: { bars: "snapshot-bars-r4" } },
		account: {
			asOf: "2026-08-18T07:00:00Z",
			baselineId: "baseline-r4",
			cashAvailable: 250_000,
			totalValue: 1_000_000,
			exposure: 750_000,
			positions: [],
		},
		actions: [
			{
				intentId: "intent-r4",
				instrumentId: 510300,
				direction: "buy",
				currentWeight: 0.25,
				targetWeight: 0.35,
				deltaWeight: 0.1,
				suggestedQuantity: 1000,
				filledQuantity: 0,
				remainingQuantity: 1000,
				sizingReadiness: "ready",
				executionStatus: "pending",
				riskFlags: [],
			},
		],
		portfolioConstruction: {
			status: "completed",
			solver: "clarabel",
			solverVersion: "0.10",
			mode: "risk_budget",
			solverStatus: "optimal",
			durationMs: 18.5,
			policyDigest: "sha256:policy-r4",
			failureCode: null,
		},
		tailRisk: {
			historicalEs99: 0.041,
			historicalVar99: 0.031,
			parametricVar99: 0.029,
			monteCarloVar99: 0.033,
			monteCarloSeed: 42,
		},
		factorRisk: {
			availability: "available",
			totalRisk: 0.12,
			marginalContributions: { market: 0.08, size: 0.04 },
			percentageContributions: { market: 0.67, size: 0.33 },
			eulerResidual: 0.0001,
		},
		stressTests: {
			catalogVersion: "stress-v3",
			losses: { liquidity_crunch: 0.08, rate_shock: 0.03 },
			unavailableScenarios: [],
		},
		reconciliation: { status: "matched", differences: [], alertIdempotencyKey: null },
		provenance: {
			decisionTime: "2026-08-18T07:00:00Z",
			knowledgeCutoff: "2026-08-18T06:55:00Z",
			publicationCutoff: "2026-08-18T06:50:00Z",
			sourceSnapshotIds: ["snapshot-bars-r4"],
			generatedAt: "2026-08-18T07:01:00Z",
			complete: true,
		},
		completeness: { status: "complete", issues: [] },
	};

	return { ...base, ...overrides };
}
