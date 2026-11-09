import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export async function createBacktestRun(input: {
	readonly strategyId: string;
	readonly strategyVersion: number;
	readonly idempotencyKey: string;
	readonly startDate: string;
	readonly endDate: string;
	readonly initialCash: number;
	readonly allowExperimental: boolean;
	readonly historicalReconstruction?: boolean;
}) {
	const result = await apiClient.post("/api/v1/backtests/runs", {
		params: { header: { "Idempotency-Key": input.idempotencyKey } },
		body: {
			strategy_version: input.strategyVersion,
			strategy_id: input.strategyId,
			start_date: input.startDate,
			end_date: input.endDate,
			initial_cash: input.initialCash,
			allow_experimental_data: input.allowExperimental,
			historical_reconstruction: input.historicalReconstruction ?? false,
		},
	});
	if (
		!result ||
		typeof result.run_id !== "string" ||
		!/^[A-Za-z0-9._:-]+$/u.test(result.run_id) ||
		result.strategy_id !== input.strategyId ||
		!["pending", "running", "completed", "failed", "cancelled"].includes(result.status)
	) {
		throw new Error("回测提交响应无效；请重试以核对同一次提交。");
	}
	return { runId: result.run_id, status: result.status };
}

import type {
	BacktestAuditRecord,
	BacktestBenchmark,
	BacktestNavPoint,
	BacktestReport,
	BacktestRequest,
	BacktestRun,
	BacktestTradeRecord,
} from "../types";
import { legacyBacktestUsage } from "../types";

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
	const bill = dto.fee_statement;
	if (
		bill != null &&
		(bill.currency !== "CNY" ||
			!Array.isArray(bill.fills) ||
			(bill.final_cash !== null && !Number.isFinite(bill.final_cash)) ||
			bill.fills.some(
				(fill) =>
					!fill ||
					!Number.isSafeInteger(fill.instrument_id) ||
					fill.instrument_id <= 0 ||
					fill.schedule?.instrument_id !== fill.instrument_id ||
					!["buy", "sell"].includes(fill.direction) ||
					!Number.isSafeInteger(fill.quantity) ||
					fill.quantity <= 0 ||
					fill.price <= 0 ||
					![
						fill.price,
						fill.commission,
						fill.stamp_duty,
						fill.transfer_fee,
						fill.total_fee,
						fill.schedule.commission_rate,
						fill.schedule.min_commission,
						fill.schedule.stamp_duty_rate,
						fill.schedule.transfer_fee_rate,
						fill.schedule.transfer_fee_per_share,
					].every((value) => Number.isFinite(value) && value >= 0),
			))
	) {
		throw new Error("费用账单响应无效；币种、成交方向、证券身份或金额不一致，请重新读取报告。");
	}
	return {
		runId: dto.run_id,
		periodStart: dto.period?.["start"] ?? "",
		periodEnd: dto.period?.["end"] ?? "",
		initialCash: dto.initial_cash,
		finalNav: dto.final_nav,
		feeStatement: dto.fee_statement
			? {
					currency: dto.fee_statement.currency,
					policy: dto.fee_statement.policy,
					rulesObservedAt: dto.fee_statement.rules_observed_at,
					sourceRef: dto.fee_statement.source_ref,
					finalCash: dto.fee_statement.final_cash,
					fills: dto.fee_statement.fills.map((fill) => ({
						fillId: fill.fill_id,
						orderId: fill.order_id,
						instrumentId: fill.instrument_id,
						symbol: fill.symbol,
						tradeDate: fill.trade_date,
						direction: fill.direction,
						quantity: fill.quantity,
						price: fill.price,
						commission: fill.commission,
						stampDuty: fill.stamp_duty,
						transferFee: fill.transfer_fee,
						totalFee: fill.total_fee,
						schedule: {
							instrumentId: fill.schedule.instrument_id,
							asOfDate: fill.schedule.as_of_date,
							commissionRate: fill.schedule.commission_rate,
							minCommission: fill.schedule.min_commission,
							stampDutyRate: fill.schedule.stamp_duty_rate,
							transferFeeRate: fill.schedule.transfer_fee_rate,
							transferFeePerShare: fill.schedule.transfer_fee_per_share,
						},
					})),
				}
			: null,
		rebalanceFreq: dto.rebalance_freq,
		usageContext: dto.usage_context
			? {
					intendedUse: dto.usage_context.intended_use,
					historicalAvailability: dto.usage_context.historical_availability,
					samplePool: dto.usage_context.sample_pool,
					inputInstrumentIds: dto.usage_context.input_instrument_ids ?? [],
					limitations: dto.usage_context.limitations ?? legacyBacktestUsage.limitations,
				}
			: legacyBacktestUsage,
		strategyPromotion: dto.strategy_promotion ?? null,
		pitPolicy: dto.pit_policy ?? null,
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
					profitFactor: trades.profit_factor ?? null,
					avgWin: trades.avg_win,
					avgLoss: trades.avg_loss,
					avgWinLossRatio: trades.avg_win_loss_ratio ?? null,
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

export async function fetchBacktestRequest(runId: string): Promise<BacktestRequest> {
	const dto = await apiClient.get("/api/v1/backtests/runs/{run_id}/request", {
		params: { path: { run_id: runId } },
	});
	if (
		!dto ||
		dto.run_id !== runId ||
		!["historical_reconstruction", "limited_historical_research", "strict_snapshot_replay", "unclassified"].includes(
			dto.purpose,
		) ||
		!["pending", "ready", "blocked", "unrecorded"].includes(dto.input_status)
	) {
		throw new Error("请求来源响应无效；请重试读取本次运行。");
	}
	const participation = dto.participation ?? [];
	if (
		!Array.isArray(participation) ||
		participation.some(
			(row) =>
				!row ||
				!Number.isSafeInteger(row.instrument_id) ||
				row.instrument_id <= 0 ||
				typeof row.symbol !== "string" ||
				!row.symbol ||
				typeof row.trade_date !== "string" ||
				!/^\d{4}-\d{2}-\d{2}$/u.test(row.trade_date) ||
				![
					"eligible",
					"outside_universe",
					"not_listed",
					"delisted",
					"warmup",
					"listing_rule_unavailable",
					"suspended",
					"zero_volume",
				].includes(row.status) ||
				!Number.isSafeInteger(row.warmup_available) ||
				row.warmup_available < 0 ||
				!Number.isSafeInteger(row.warmup_required) ||
				row.warmup_required < 0 ||
				(row.evaluated !== undefined && typeof row.evaluated !== "boolean") ||
				(row.execution_rule != null && typeof row.execution_rule !== "string"),
		) ||
		new Set(participation.map((row) => `${row.trade_date}:${row.instrument_id}`)).size !== participation.length
	) {
		throw new Error("逐日参与记录无效；请重试读取本次运行。");
	}
	return {
		runId: dto.run_id,
		purpose: dto.purpose,
		startDate: dto.start_date ?? null,
		endDate: dto.end_date ?? null,
		initialCash: dto.initial_cash ?? null,
		universe: dto.universe,
		inputStatus: dto.input_status,
		frozenAt: dto.frozen_at,
		reason: dto.reason,
		members: dto.members ?? [],
		limitations: dto.limitations ?? [],
		participation: participation.map((row) => ({
			instrumentId: row.instrument_id,
			symbol: row.symbol,
			tradeDate: row.trade_date,
			status: row.status,
			warmupAvailable: row.warmup_available,
			warmupRequired: row.warmup_required,
			evaluated: row.evaluated ?? false,
			executionRule: row.execution_rule ?? null,
		})),
		sources: (dto.sources ?? []).map((source) => ({
			dataset: source.dataset,
			source: source.source,
			snapshotId: source.snapshot_id,
			checksum: source.checksum,
			startDate: source.request_start,
			endDate: source.request_end,
			receivedAt: source.received_at,
			observedAt: source.observed_at,
			rows: source.rows,
			verified: source.verified,
		})),
	};
}

export async function retryBacktestRun(input: { readonly runId: string; readonly idempotencyKey: string }) {
	const dto = await apiClient.post("/api/v1/backtests/runs/{run_id}/retry", {
		params: { path: { run_id: input.runId }, header: { "Idempotency-Key": input.idempotencyKey } },
	});
	if (
		!dto ||
		typeof dto.run_id !== "string" ||
		!/^[A-Za-z0-9._:-]+$/u.test(dto.run_id) ||
		dto.parent_run_id !== input.runId ||
		!["pending", "running", "completed", "failed", "cancelled"].includes(dto.status)
	) {
		throw new Error("恢复响应无效；请重试核对同一次恢复。");
	}
	return { runId: dto.run_id };
}
