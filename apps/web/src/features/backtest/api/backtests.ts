import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";
import type {
	BacktestAuditRecord,
	BacktestBenchmark,
	BacktestNavPoint,
	BacktestReport,
	BacktestRun,
	BacktestTradeRecord,
} from "../types";

export type RunResponse = components["schemas"]["RunResponse"];
export type BacktestReportResponse = components["schemas"]["BacktestReportResponse"];
export type NavPointResponse = components["schemas"]["NavPointResponse"];
export type BenchmarkNavResponse = components["schemas"]["BenchmarkNavResponse"];
export type TradeResponse = components["schemas"]["TradeResponse"];
export type AuditRecordResponse = components["schemas"]["AuditRecordResponse"];

export function mapBacktestRun(dto: RunResponse): BacktestRun {
	return {
		runId: dto.run_id,
		strategyId: dto.strategy_id,
		strategyVersion: dto.strategy_version,
		mode: dto.mode,
		status: dto.status,
		startedAt: dto.started_at,
		completedAt: dto.completed_at,
		errorMessage: dto.error_message,
		parentRunId: dto.parent_run_id,
		benchmarkReturn: dto.benchmark_return ?? null,
		progressPct: dto.progress_pct,
		currentStep: dto.current_step,
		completedDays: dto.completed_days,
		totalDays: dto.total_days,
	};
}

export async function fetchBacktestRuns(): Promise<BacktestRun[]> {
	const rows = await apiClient.get("/api/v1/backtests/runs");
	return rows.map(mapBacktestRun);
}

export async function fetchBacktestRun(runId: string): Promise<BacktestRun> {
	const dto = await apiClient.get("/api/v1/backtests/runs/{run_id}", {
		params: { path: { run_id: runId } },
	});
	return mapBacktestRun(dto);
}

export function mapBacktestReport(dto: BacktestReportResponse): BacktestReport {
	const alpha = dto.alpha_stats;
	const trades = dto.aggregated_trade_stats;
	return {
		runId: dto.run_id,
		periodStart: dto.period?.["start"] ?? "",
		periodEnd: dto.period?.["end"] ?? "",
		initialCash: dto.initial_cash,
		finalNav: dto.final_nav,
		rebalanceFreq: dto.rebalance_freq,
		alphaStats: alpha
			? {
					annualizedReturn: alpha.annualized_return,
					annualizedVolatility: alpha.annualized_volatility,
					sharpeRatio: alpha.sharpe_ratio,
					sortinoRatio: alpha.sortino_ratio,
					maxDrawdown: alpha.max_drawdown,
					maxDrawdownDurationDays: alpha.max_drawdown_duration_days,
					calmarRatio: alpha.calmar_ratio,
					informationRatio: alpha.information_ratio ?? null,
					trackingError: alpha.tracking_error ?? null,
					beta: alpha.beta ?? null,
					alphaAnnualized: alpha.alpha_annualized ?? null,
					totalTurnover: alpha.total_turnover,
					avgTurnoverPerRebalance: alpha.avg_turnover_per_rebalance,
					totalFees: alpha.total_fees,
					netReturnAfterCost: alpha.net_return_after_cost,
					costDrag: alpha.cost_drag,
				}
			: null,
		tradeStats: trades
			? {
					totalTrades: trades.total_trades,
					longTrades: trades.long_trades,
					shortTrades: trades.short_trades,
					winTrades: trades.win_trades,
					lossTrades: trades.loss_trades,
					winRate: trades.win_rate,
					profitFactor: trades.profit_factor,
					avgWin: trades.avg_win,
					avgLoss: trades.avg_loss,
					avgWinLossRatio: trades.avg_win_loss_ratio,
					maxConsecutiveWins: trades.max_consecutive_wins,
					maxConsecutiveLosses: trades.max_consecutive_losses,
					avgHoldingDays: trades.avg_holding_days,
					medianHoldingDays: trades.median_holding_days,
					bestTrade: trades.best_trade,
					worstTrade: trades.worst_trade,
					avgTradeReturnPct: trades.avg_trade_return_pct,
				}
			: null,
	};
}

export async function fetchBacktestReport(runId: string): Promise<BacktestReport> {
	const dto = await apiClient.get("/api/v1/backtests/runs/{run_id}/report", {
		params: { path: { run_id: runId } },
	});
	return mapBacktestReport(dto);
}

export async function fetchBacktestNav(runId: string): Promise<BacktestNavPoint[]> {
	const rows = await apiClient.get("/api/v1/backtests/runs/{run_id}/nav", {
		params: { path: { run_id: runId } },
	});
	return rows.map((row) => ({ tradeDate: row.trade_date, nav: row.nav }));
}

export async function fetchBacktestBenchmark(runId: string): Promise<BacktestBenchmark> {
	const dto = await apiClient.get("/api/v1/backtests/runs/{run_id}/benchmark", {
		params: { path: { run_id: runId } },
	});
	return {
		runId: dto.run_id,
		dates: dto.dates ?? [],
		navs: dto.navs ?? [],
		benchmarkReturn: dto.benchmark_return ?? null,
	};
}

export async function fetchBacktestTrades(runId: string): Promise<BacktestTradeRecord[]> {
	const rows = await apiClient.get("/api/v1/backtests/runs/{run_id}/trades", {
		params: { path: { run_id: runId } },
	});
	return rows.map((row) => ({
		tradeDate: row.trade_date,
		instrumentId: row.instrument_id,
		direction: row.direction,
		entryDate: row.entry_date,
		exitDate: row.exit_date,
		entryPrice: row.entry_price,
		exitPrice: row.exit_price,
		quantity: row.quantity,
		pnl: row.pnl,
	}));
}

export async function fetchBacktestAudit(runId: string): Promise<BacktestAuditRecord[]> {
	const rows = await apiClient.get("/api/v1/backtests/runs/{run_id}/audit", {
		params: { path: { run_id: runId } },
	});
	return rows.map((row) => ({
		id: row.id,
		runId: row.run_id,
		tradeDate: row.trade_date,
		recordType: row.record_type,
		instrumentId: row.instrument_id ?? null,
		payload: row.payload ?? {},
		createdAt: row.created_at,
	}));
}
