import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { capturedRequest, requestPath } from "@/test/request";
import { fetchSystemCatalogAssets, fetchSystemSourceHealth } from "./system-overview";

afterEach(() => vi.unstubAllGlobals());

describe("system overview API adapter", () => {
	it("serializes dataset and trade-date scope as repeated query values", async () => {
		let requestedUrl = "";
		server.use(
			http.get("/api/v1/ingestion/catalog/source-health/summary", ({ request }) => {
				requestedUrl = request.url;
				return HttpResponse.json({
					data: {
						attention_required: [],
						dataset_ids: ["etf_daily", "stock_daily"],
						failover_count: 0,
						no_fallback_source_count: 0,
						selected_source_counts: [],
						status_counts: [],
						total_reports: 0,
						trade_dates: ["2026-08-30"],
					},
				});
			}),
		);

		await fetchSystemSourceHealth({ datasetIds: ["etf_daily", "stock_daily"], tradeDate: "2026-08-30" });

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
							selected_source_counts: [],
							status_counts: [],
							total_reports: 1,
						},
					});
				default:
					throw new Error(`Unhandled system overview request ${path}`);
			}
		});
		vi.stubGlobal("fetch", fetchMock);
		const scope = { datasetIds: ["stock_daily"], tradeDate: "2026-08-30" } as const;

		await expect(fetchSystemCatalogAssets()).resolves.toMatchObject([{ rowCount: null }]);
		await expect(fetchSystemSourceHealth(scope)).resolves.toMatchObject({ attentionItems: [{ reasons: [] }] });
	});
});
