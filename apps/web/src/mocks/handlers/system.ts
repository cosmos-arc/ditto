import { HttpResponse, http, type RequestHandler } from "msw";

export const systemHandlers: RequestHandler[] = [
	http.get("/api/v1/status", () =>
		HttpResponse.json({
			environment: "mock-local",
			features: { backtest: true, data_collection: true, data_validation: true, trading: true },
			observability: { level: "INFO", structured: true },
			status: "running",
			version: "0.1.0-mock",
		}),
	),
	http.get("/api/v1/ingestion/catalog/assets", () =>
		HttpResponse.json({
			data: [
				{
					asset: { dataset_id: "stock_daily", namespace: "market", partition_keys: ["trade_date"] },
					freshness_at: "2026-08-30T07:01:00Z",
					schema_fingerprint: { schema_hash: "sha256:stock-daily-v4", row_count: 5_280_000 },
					source: "tushare",
					storage_uri: "catalog://market/stock_daily",
				},
				{
					asset: { dataset_id: "etf_daily", namespace: "market", partition_keys: ["trade_date"] },
					freshness_at: "2026-08-30T07:04:00Z",
					schema_fingerprint: { schema_hash: "sha256:etf-daily-v3", row_count: 286_400 },
					source: "wind",
					storage_uri: "catalog://market/etf_daily",
				},
			],
		}),
	),

	http.get("/api/v1/ingestion/status", () =>
		HttpResponse.json({
			data: {
				datasets: [
					{
						catalog_freshness_at: "2026-10-01T08:00:00Z",
						catalog_freshness_status: "fresh",
						dataset: "calendar",
						dataset_maturity: "initial-focus",
						latest_date: "2026-09-30",
						latest_status: "success",
						record_count: 2499,
					},
					{
						catalog_freshness_at: "2026-10-01T07:55:00Z",
						catalog_freshness_status: "fresh",
						dataset: "stock_daily",
						dataset_maturity: "initial-focus",
						latest_date: "2026-09-30",
						latest_status: "success",
						record_count: 5_280_000,
					},
					{
						catalog_freshness_at: null,
						catalog_freshness_status: "missing",
						dataset: "index_daily",
						dataset_maturity: "initial-focus",
						latest_date: "2026-09-29",
						latest_status: "failed",
						record_count: 0,
					},
				],
				maturity_summary: [],
			},
		}),
	),

	http.get("/api/v1/ingestion/catalog/source-health/summary", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const tradeDate = query.getAll("trade_dates")[0] ?? "2026-08-30";
		const datasetIds = query.getAll("dataset_ids");
		const attentionDatasetId = datasetIds[0] ?? "stock_daily";
		return HttpResponse.json({
			data: {
				attention_reason_counts: [{ reason: "PRIMARY_SOURCE_STALE", count: 1 }],
				attention_required: [
					{
						attention_reasons: ["PRIMARY_SOURCE_STALE"],
						attention_severity: "warning",
						dataset_id: attentionDatasetId,
						default_source: "tushare",
						failover_from_default: true,
						fallback_sources: ["wind"],
						selected_freshness_status: "fresh",
						selected_source: "wind",
						selected_source_health: {
							freshness_at: "2026-08-30T07:03:00Z",
							freshness_status: "fresh",
							source: "wind",
							supported: true,
						},
						source_selection_blockers: [],
						source_selection_status: "ready",
						trade_date: tradeDate,
					},
				],
				available_sources: ["tushare", "wind"],
				dataset_ids: datasetIds,
				failover_count: 1,
				no_fallback_source_count: 0,
				reports: [],
				selected_source_counts: [{ source: "wind", count: 1 }],
				status_counts: [
					{ status: "fresh", count: 1 },
					{ status: "stale", count: 1 },
				],
				total_reports: datasetIds.length,
				trade_dates: [tradeDate],
			},
		});
	}),
];
