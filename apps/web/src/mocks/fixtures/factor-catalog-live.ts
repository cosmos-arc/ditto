type Preview = {
	readonly rank_ic: number;
	readonly ic_ir: number;
	readonly sharpe: number;
	readonly turnover: number;
	readonly decay: number;
	readonly coverage: number;
	readonly universe: string;
	readonly status: "stable" | "degrading" | "warning";
};

function descriptor(
	...[factorId, lanes, lookback, pitRequirement, preview]: readonly [string, readonly string[], number, string, Preview]
) {
	return {
		factor_id: factorId,
		resolved_payload: {
			lanes,
			lookback: { value: lookback, unit: "trading_days" },
			pit_requirement: pitRequirement,
			diagnostic_preview: preview,
		},
	};
}

export const mockFactorCatalog = [
	descriptor("momentum_1m", ["stock", "etf"], 20, "known_at", {
		rank_ic: 0.018,
		ic_ir: 0.39,
		sharpe: 0.88,
		turnover: 0.34,
		decay: 0.071,
		coverage: 0.96,
		universe: "全 A / ETF",
		status: "degrading",
	}),
	descriptor("momentum_3m", ["stock", "etf"], 60, "known_at", {
		rank_ic: 0.043,
		ic_ir: 0.72,
		sharpe: 1.42,
		turnover: 0.19,
		decay: 0.024,
		coverage: 0.95,
		universe: "全 A / ETF",
		status: "stable",
	}),
	descriptor("reversal_1w", ["stock", "etf"], 5, "known_at", {
		rank_ic: 0.021,
		ic_ir: 0.41,
		sharpe: 0.93,
		turnover: 0.61,
		decay: 0.086,
		coverage: 0.94,
		universe: "全 A / ETF",
		status: "warning",
	}),
	descriptor("volatility_factor", ["stock", "etf"], 20, "known_at", {
		rank_ic: 0.036,
		ic_ir: 0.64,
		sharpe: 1.21,
		turnover: 0.22,
		decay: 0.031,
		coverage: 0.98,
		universe: "全 A / ETF",
		status: "stable",
	}),
	descriptor("vol_ratio", ["stock", "etf"], 60, "known_at", {
		rank_ic: 0.014,
		ic_ir: 0.28,
		sharpe: 0.74,
		turnover: 0.43,
		decay: 0.079,
		coverage: 0.91,
		universe: "全 A / ETF",
		status: "degrading",
	}),
	descriptor("liquidity", ["stock", "etf"], 20, "known_at", {
		rank_ic: 0.028,
		ic_ir: 0.51,
		sharpe: 1.08,
		turnover: 0.25,
		decay: 0.044,
		coverage: 0.99,
		universe: "全 A / ETF",
		status: "stable",
	}),
	descriptor("relative_strength_60d", ["stock", "etf"], 60, "known_at", {
		rank_ic: 0.041,
		ic_ir: 0.68,
		sharpe: 1.34,
		turnover: 0.2,
		decay: 0.027,
		coverage: 0.93,
		universe: "全 A / ETF",
		status: "stable",
	}),
	descriptor("ep_ttm", ["stock"], 1, "announcement_known_at", {
		rank_ic: 0.032,
		ic_ir: 0.57,
		sharpe: 1.16,
		turnover: 0.12,
		decay: 0.018,
		coverage: 0.87,
		universe: "全 A",
		status: "stable",
	}),
	descriptor("bp_ratio", ["stock"], 1, "announcement_known_at", {
		rank_ic: 0.029,
		ic_ir: 0.49,
		sharpe: 1.02,
		turnover: 0.11,
		decay: 0.022,
		coverage: 0.9,
		universe: "全 A",
		status: "stable",
	}),
	descriptor("quality_roe", ["stock"], 1, "announcement_known_at", {
		rank_ic: 0.047,
		ic_ir: 0.81,
		sharpe: 1.58,
		turnover: 0.09,
		decay: 0.016,
		coverage: 0.82,
		universe: "全 A",
		status: "stable",
	}),
	descriptor("revenue_growth", ["stock"], 1, "announcement_known_at", {
		rank_ic: 0.017,
		ic_ir: 0.33,
		sharpe: 0.82,
		turnover: 0.1,
		decay: 0.063,
		coverage: 0.78,
		universe: "全 A",
		status: "degrading",
	}),
	descriptor("log_free_float_cap", ["stock"], 1, "known_at", {
		rank_ic: 0.025,
		ic_ir: 0.46,
		sharpe: 0.97,
		turnover: 0.08,
		decay: 0.029,
		coverage: 1,
		universe: "全 A",
		status: "stable",
	}),
] as const;
