export type FactorStatus = "stable" | "optimal" | "decay" | "failed";

export interface Factor {
	readonly name: string;
	readonly category: string;
	readonly ic: number;
	readonly ir: number;
	readonly decay: number;
	readonly status: FactorStatus;
}

export interface BacktestRun {
	readonly id: string;
	readonly strategy: string;
	readonly time: string;
	readonly sharpe: number;
	readonly maxDrawdown: number;
	readonly dimmed?: boolean;
}

export interface Experiment {
	readonly name: string;
	readonly progress: number;
}
