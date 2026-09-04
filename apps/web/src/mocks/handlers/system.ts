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

	http.get("/api/v1/ingestion/catalog/remediation/backlog", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const tradeDate = query.getAll("trade_dates")[0] ?? "2026-08-30";
		const datasetIds = query.getAll("dataset_ids");
		const items = datasetIds.map((datasetId, index) => ({
			dataset_id: datasetId,
			item_id: `${index === 0 ? "source-health" : "promotion"}:${datasetId}:${tradeDate}`,
			namespace: "market",
			reasons: [index === 0 ? "PRIMARY_SOURCE_STALE" : "CERTIFICATION_EVIDENCE_MISSING"],
			severity: index === 0 ? "high" : "medium",
			source: index === 0 ? "source_health" : "promotion_readiness",
			suggested_actions: [index === 0 ? "review_fallback_source" : "review_promotion_evidence"],
			trade_date: tradeDate,
		}));
		return HttpResponse.json({
			data: {
				available_sources: ["tushare", "wind"],
				dataset_ids: datasetIds,
				generated_at: "2026-08-30T07:05:00Z",
				items,
				severity_counts: [
					{ severity: "high", count: Math.min(1, items.length) },
					{ severity: "medium", count: Math.max(0, items.length - 1) },
				],
				total_items: items.length,
				trade_dates: [tradeDate],
			},
		});
	}),

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
				revoked_promotion_count: 0,
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

	http.get("/api/v1/ingestion/catalog/source-fallback/summary", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const tradeDate = query.getAll("trade_dates")[0] ?? "2026-08-30";
		const datasetIds = query.getAll("dataset_ids");
		const previews = datasetIds.map((datasetId, index) => ({
			approval_required: index === 0,
			dataset_id: datasetId,
			default_source: "tushare",
			execution_allowed: true,
			fallback_sources: ["wind"],
			namespace: "market",
			policy_status: index === 0 ? "review_required" : "not_required",
			reason_codes: index === 0 ? ["PRIMARY_SOURCE_STALE"] : [],
			recommended_actions: index === 0 ? ["review_fallback_source"] : [],
			recommended_source: index === 0 ? "wind" : "tushare",
			selected_freshness_status: "fresh",
			selected_source: index === 0 ? "wind" : "tushare",
			source_selection_status: "ready",
			trade_date: tradeDate,
		}));
		return HttpResponse.json({
			data: {
				approval_required_count: 1,
				available_sources: ["tushare", "wind"],
				dataset_ids: datasetIds,
				execution_allowed_count: 2,
				policy_status_counts: [
					{ status: "review_required", count: 1 },
					{ status: "not_required", count: 1 },
				],
				previews,
				total_previews: previews.length,
				trade_dates: [tradeDate],
			},
		});
	}),

	http.get("/api/v1/ingestion/catalog/promotion/readiness", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const datasetIds = query.getAll("dataset_ids");
		const datasets = datasetIds.map((datasetId, index) => ({
			active_maturity_promotion: index === 0,
			current_maturity: index === 0 ? "certified" : "validated",
			dataset_id: datasetId,
			missing_criteria: index === 0 ? [] : ["certification_evidence"],
			promotion_status: index === 0 ? "ready" : "blocked",
		}));
		return HttpResponse.json({
			data: {
				active_promotion_count: Math.min(1, datasets.length),
				dataset_count: datasets.length,
				datasets,
				promotable_count: Math.min(1, datasets.length),
				status_counts: [
					{ status: "ready", count: 1 },
					{ status: "blocked", count: 1 },
				],
			},
		});
	}),
];
