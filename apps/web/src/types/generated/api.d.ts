/**
 * Generated baseline for Ditto trade API.
 *
 * Source: ditto `/openapi.json` when the backend is running.
 * Refresh with: bun run gen:api
 */

export interface paths {
	"/api/v1/trade/daily-decision": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					trade_date?: string | null;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_DailyDecisionReportResponse_"];
					};
				};
			};
		};
	};
	"/api/v1/trade/intents": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					signal_date?: string | null;
					status?: string | null;
					limit?: number;
					offset?: number;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_list_TradeIntentResponse__"];
					};
				};
			};
		};
	};
	"/api/v1/trade/fills": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					start_date?: string | null;
					end_date?: string | null;
					limit?: number;
					offset?: number;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_list_FillResponse__"];
					};
				};
			};
		};
		post: {
			requestBody: {
				content: {
					"application/json": components["schemas"]["RecordFillRequest"];
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_FillResponse_"];
					};
				};
			};
		};
	};
	"/api/v1/trade/positions": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					snapshot_date?: string | null;
					limit?: number;
					offset?: number;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_list_PositionSnapshotResponse__"];
					};
				};
			};
		};
	};
	"/api/v1/trade/pnl": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					snapshot_date: string;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_PnlSummaryResponse_"];
					};
				};
			};
		};
	};
	"/api/v1/trade/signals/latest": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					limit?: number;
					offset?: number;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_list_TradeIntentResponse__"];
					};
				};
			};
		};
	};
	"/api/v1/trade/signals/{signal_date}/intents": {
		get: {
			parameters: {
				path: {
					signal_date: string;
				};
				query: {
					strategy_id: string;
					limit?: number;
					offset?: number;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_list_TradeIntentResponse__"];
					};
				};
			};
		};
	};
	"/api/v1/trade/deviation": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					signal_date: string;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_DeviationResponse_"];
					};
				};
			};
		};
	};
	"/api/v1/trade/comparison": {
		get: {
			parameters: {
				query: {
					strategy_id: string;
					run_id: string;
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_ComparisonMetricsResponse_"];
					};
				};
			};
		};
	};
	"/api/v1/trade/intents/{intent_id}/status": {
		put: {
			parameters: {
				path: {
					intent_id: string;
				};
			};
			requestBody: {
				content: {
					"application/json": components["schemas"]["UpdateIntentStatusRequest"];
				};
			};
			responses: {
				200: {
					content: {
						"application/json": components["schemas"]["APIResponse_boolean_"];
					};
				};
			};
		};
	};
}

export interface components {
	schemas: {
		APIResponse_DailyDecisionReportResponse_: ApiResponse<components["schemas"]["DailyDecisionReportResponse"]>;
		APIResponse_list_TradeIntentResponse__: ApiResponse<components["schemas"]["TradeIntentResponse"][]>;
		APIResponse_list_FillResponse__: ApiResponse<components["schemas"]["FillResponse"][]>;
		APIResponse_list_PositionSnapshotResponse__: ApiResponse<components["schemas"]["PositionSnapshotResponse"][]>;
		APIResponse_PnlSummaryResponse_: ApiResponse<components["schemas"]["PnlSummaryResponse"]>;
		APIResponse_DeviationResponse_: ApiResponse<components["schemas"]["DeviationResponse"]>;
		APIResponse_ComparisonMetricsResponse_: ApiResponse<components["schemas"]["ComparisonMetricsResponse"]>;
		APIResponse_FillResponse_: ApiResponse<components["schemas"]["FillResponse"]>;
		APIResponse_boolean_: ApiResponse<boolean>;
		PaginationResponse: {
			total: number;
			limit: number;
			offset: number;
			has_more: boolean;
		};
		TradeIntentResponse: {
			intent_id: string;
			strategy_id: string;
			signal_date: string;
			instrument_id: number;
			direction: string;
			target_weight: number;
			current_weight: number;
			delta_weight: number;
			quantity?: number | null;
			status: string;
		};
		FillResponse: {
			fill_id: string;
			intent_id: string;
			strategy_id: string;
			trade_date: string;
			instrument_id: number;
			direction: string;
			quantity: number;
			fill_price: number;
			fee: number;
			slippage: number;
			notes: string;
			settlement_date: string;
		};
		PositionSnapshotResponse: {
			snapshot_id: string;
			strategy_id: string;
			snapshot_date: string;
			instrument_id: number;
			quantity: number;
			available_quantity: number;
			average_cost: number;
			market_value: number;
			unrealized_pnl: number;
			realized_pnl: number;
			total_fees: number;
		};
		PnlSummaryResponse: {
			total_realized_pnl: number;
			total_unrealized_pnl: number;
			total_fees: number;
			net_pnl: number;
		};
		ComparisonMetricsResponse: {
			backtest_return: number;
			actual_return?: number | null;
			return_diff?: number | null;
			return_diff_bps?: number | null;
			backtest_sharpe: number;
			actual_sharpe: number;
			backtest_total_cost: number;
			actual_total_cost: number;
			cost_drag_bps: number;
			nav_correlation: number;
			max_nav_diff_bps: number;
			avg_daily_tracking_error_bps: number;
		};
		SignalDeviationItem: {
			instrument_id: number;
			signal_action: string;
			signal_weight: number;
			actual_weight?: number | null;
			deviation_bps?: number | null;
			fill_status: string;
		};
		DeviationResponse: {
			strategy_id: string;
			signal_date: string;
			total_signals: number;
			filled: number;
			unfilled: number;
			items: components["schemas"]["SignalDeviationItem"][];
		};
		DailyDecisionReadinessResponse: {
			status: "ready" | "blocked" | "review";
			reasons: string[];
		};
		DailyDecisionReportResponse: {
			strategy_id: string;
			trade_date?: string | null;
			readiness: components["schemas"]["DailyDecisionReadinessResponse"];
			signal_intents: components["schemas"]["TradeIntentResponse"][];
			positions: components["schemas"]["PositionSnapshotResponse"][];
			deviation?: components["schemas"]["DeviationResponse"] | null;
			pnl?: components["schemas"]["PnlSummaryResponse"] | null;
		};
		RecordFillRequest: {
			fill_id: string;
			intent_id: string;
			strategy_id: string;
			trade_date: string;
			instrument_id: number;
			direction: "buy" | "sell";
			quantity: number;
			fill_price: number;
			fee?: number;
			slippage?: number;
			notes?: string;
		};
		UpdateIntentStatusRequest: {
			status: "pending" | "filled" | "partially_filled" | "cancelled" | "expired";
		};
		ErrorResponse: {
			status_code: number;
			error: string;
			detail?: string | null;
			error_code?: string | null;
			request_id?: string | null;
			timestamp?: number | null;
		};
	};
}

export type ApiResponse<T> = {
	data: T;
	pagination?: components["schemas"]["PaginationResponse"] | null;
};
