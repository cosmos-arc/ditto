export type DailyDecisionReadiness = "ready" | "review" | "blocked";

export type DailyDecisionV3ViewModel = {
	readonly identity: {
		readonly strategyId: string;
		readonly strategyVersion: string | null;
		readonly signalDate: string | null;
		readonly tradeDate: string | null;
		readonly accountId: string | null;
		readonly sleeveId: string | null;
	};
	readonly readiness: {
		readonly status: DailyDecisionReadiness;
		readonly reportedStatus: DailyDecisionReadiness;
		readonly blockingReasons: readonly string[];
	};
	readonly data: {
		readonly freshness: string | null;
		readonly qualityState: string | null;
		readonly snapshotIds: Readonly<Record<string, string>>;
	};
	readonly account: {
		readonly asOf: string | null;
		readonly baselineId: string | null;
		readonly cashAvailable: number | null;
		readonly totalValue: number | null;
		readonly exposure: number | null;
		readonly positions: readonly {
			readonly instrumentId: number;
			readonly quantity: number;
			readonly availableQuantity: number | null;
			readonly marketValue: number | null;
		}[];
	};
	readonly actions: readonly {
		readonly intentId: string;
		readonly instrumentId: number;
		readonly direction: string | null;
		readonly currentWeight: number | null;
		readonly targetWeight: number;
		readonly deltaWeight: number | null;
		readonly suggestedQuantity: number | null;
		readonly filledQuantity: number | null;
		readonly remainingQuantity: number | null;
		readonly sizingReadiness: string | null;
		readonly executionStatus: string | null;
		readonly riskFlags: readonly string[];
	}[];
	readonly portfolioConstruction: {
		readonly status: string;
		readonly solver: string | null;
		readonly solverVersion: string | null;
		readonly mode: string | null;
		readonly solverStatus: string | null;
		readonly durationMs: number | null;
		readonly policyDigest: string | null;
		readonly failureCode: string | null;
	};
	readonly tailRisk: {
		readonly historicalEs99: number | null;
		readonly historicalVar99: number | null;
		readonly parametricVar99: number | null;
		readonly monteCarloVar99: number | null;
		readonly monteCarloSeed: number | null;
	};
	readonly factorRisk: {
		readonly availability: "available" | "partial" | "unavailable";
		readonly totalRisk: number | null;
		readonly marginalContributions: Readonly<Record<string, number>>;
		readonly percentageContributions: Readonly<Record<string, number>>;
		readonly eulerResidual: number | null;
	};
	readonly stressTests: {
		readonly catalogVersion: string;
		readonly losses: Readonly<Record<string, number>>;
		readonly unavailableScenarios: readonly string[];
	};
	readonly reconciliation: {
		readonly status: string;
		readonly differences: readonly string[];
		readonly alertIdempotencyKey: string | null;
	};
	readonly provenance: {
		readonly decisionTime: string | null;
		readonly knowledgeCutoff: string | null;
		readonly publicationCutoff: string | null;
		readonly sourceSnapshotIds: readonly string[];
		readonly generatedAt: string | null;
		readonly complete: boolean;
	};
	readonly completeness: {
		readonly status: "complete" | "partial" | "blocked";
		readonly issues: readonly string[];
	};
};
