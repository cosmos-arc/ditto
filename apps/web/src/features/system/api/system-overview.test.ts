import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { capturedRequest, requestPath } from "@/test/request";
import {
	fetchSystemCatalogAssets,
	fetchSystemFallback,
	fetchSystemPromotion,
	fetchSystemRemediation,
	fetchSystemSourceHealth,
} from "./system-overview";

afterEach(() => vi.unstubAllGlobals());

describe("system overview API adapter", () => {
	it("serializes dataset and trade-date scope as repeated query values", async () => {
		let requestedUrl = "";
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/backlog", ({ request }) => {
				requestedUrl = request.url;
				return HttpResponse.json({
					data: {
						available_sources: [],
						dataset_ids: ["etf_daily", "stock_daily"],
						generated_at: "2026-08-30T07:05:00Z",
						items: [],
						severity_counts: [],
						total_items: 0,
						trade_dates: ["2026-08-30"],
					},
				});
			}),
		);

		await fetchSystemRemediation({ datasetIds: ["etf_daily", "stock_daily"], tradeDate: "2026-08-30" });

		const query = new URL(requestedUrl).searchParams;
		expect(query.getAll("dataset_ids")).toEqual(["etf_daily", "stock_daily"]);
		expect(query.getAll("trade_dates")).toEqual(["2026-08-30"]);
	});

	it("maps missing optional catalog evidence to explicit unavailable values", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const path = requestPath(capturedRequest([[input, init]])).split("?")[0];
			switch (path) {
				case "/api/v1/ingestion/catalog/assets":
					return Response.json({
						data: [
							{
								asset: { dataset_id: "stock_daily", namespace: "market" },
								freshness_at: "2026-08-30T07:05:00Z",
								schema_fingerprint: { schema_hash: "a".repeat(64) },
								source: "tushare",
								storage_uri: "parquet://stock_daily",
							},
						],
					});
				case "/api/v1/ingestion/catalog/remediation/backlog":
					return Response.json({
						data: {
							generated_at: "2026-08-30T07:05:00Z",
							items: [
								{
									dataset_id: "stock_daily",
									item_id: "source-health:stock_daily",
									severity: "high",
									source: "source_health",
								},
							],
							severity_counts: [],
							total_items: 1,
						},
					});
				case "/api/v1/ingestion/catalog/source-health/summary":
					return Response.json({
						data: {
							attention_required: [
								{
									dataset_id: "stock_daily",
									selected_source: "tushare",
									attention_severity: "high",
									source_selection_status: "attention_required",
								},
							],
							failover_count: 1,
							no_fallback_source_count: 0,
							revoked_promotion_count: 0,
							selected_source_counts: [],
							status_counts: [],
							total_reports: 1,
						},
					});
				case "/api/v1/ingestion/catalog/source-fallback/summary":
					return Response.json({
						data: {
							approval_required_count: 1,
							execution_allowed_count: 0,
							previews: [
								{
									dataset_id: "stock_daily",
									default_source: "wind",
									policy_status: "draft",
									selected_source: "tushare",
								},
							],
							policy_status_counts: [],
							total_previews: 1,
						},
					});
				case "/api/v1/ingestion/catalog/promotion/readiness":
					return Response.json({
						data: {
							active_promotion_count: 0,
							dataset_count: 1,
							datasets: [{ active_maturity_promotion: false, dataset_id: "stock_daily", promotion_status: "blocked" }],
							promotable_count: 0,
							status_counts: [],
						},
					});
				default:
					throw new Error(`Unhandled system overview request ${path}`);
			}
		});
		vi.stubGlobal("fetch", fetchMock);
		const scope = { datasetIds: ["stock_daily"], tradeDate: "2026-08-30" } as const;

		await expect(fetchSystemCatalogAssets()).resolves.toMatchObject([{ rowCount: null }]);
		await expect(fetchSystemRemediation(scope)).resolves.toMatchObject({
			items: [{ reasons: [], suggestedActions: [], tradeDate: null }],
		});
		await expect(fetchSystemSourceHealth(scope)).resolves.toMatchObject({ attentionItems: [{ reasons: [] }] });
		await expect(fetchSystemFallback(scope)).resolves.toMatchObject({ previews: [{ recommendedSource: null }] });
		await expect(fetchSystemPromotion(scope)).resolves.toMatchObject({
			datasets: [{ currentMaturity: null, missingCriteria: [] }],
		});
	});
});
