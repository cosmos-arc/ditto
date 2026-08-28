import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchRemediationBacklog, fetchRemediationDetail } from "./operations";

describe("data product operations API adapters", () => {
	it("encodes list query parameters as repeated values instead of JSON", async () => {
		let requestedUrl = "";
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/backlog", ({ request }) => {
				requestedUrl = request.url;
				return HttpResponse.json({
					data: {
						generated_at: "2026-08-18T08:00:00Z",
						dataset_ids: ["stock_daily"],
						trade_dates: ["2026-08-18"],
						available_sources: ["wind", "tushare"],
						total_items: 0,
						severity_counts: [],
						items: [],
					},
				});
			}),
		);

		await fetchRemediationBacklog({
			datasetId: "stock_daily",
			tradeDate: "2026-08-18",
			availableSources: ["wind", "tushare"],
		});

		const params = new URL(requestedUrl).searchParams;
		expect(params.getAll("dataset_ids")).toEqual(["stock_daily"]);
		expect(params.getAll("trade_dates")).toEqual(["2026-08-18"]);
		expect(params.getAll("available_sources")).toEqual(["wind", "tushare"]);
	});

	it("maps remediation detail into an exact intent and evidence view model", async () => {
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/items/:itemId", ({ params }) =>
				HttpResponse.json({
					data: {
						generated_at: "2026-08-18T08:00:00Z",
						item: {
							item_id: params.itemId,
							source: "source_health",
							dataset_id: "stock_daily",
							namespace: "market",
							severity: "high",
							trade_date: "2026-08-18",
							reasons: ["PRIMARY_SOURCE_STALE"],
							suggested_actions: ["repair_catalog_freshness"],
						},
						summary: "Primary source is stale.",
						evidence_requirements: [
							{
								requirement_id: "freshness-evidence",
								source: "source_health",
								status: "missing",
								description: "Refresh source evidence.",
							},
						],
						approval_intents: [
							{
								action: "repair_catalog_freshness",
								intent_type: "write",
								method: "POST",
								path: "/v1/ingestion/stock_daily/2026-08-18",
								request_template: {
									dataset_id: "stock_daily",
									trade_date: "2026-08-18",
									force: true,
								},
								required_operator_inputs: [],
							},
						],
					},
				}),
			),
		);

		const result = await fetchRemediationDetail("source_health:stock_daily:2026-08-18", {
			datasetId: "stock_daily",
			tradeDate: "2026-08-18",
		});

		expect(result.item.itemId).toBe("source_health:stock_daily:2026-08-18");
		expect(result.approvalIntents[0]).toMatchObject({
			action: "repair_catalog_freshness",
			requestTemplate: { dataset_id: "stock_daily", trade_date: "2026-08-18", force: true },
		});
		expect(result.evidenceRequirements[0]?.status).toBe("missing");
	});
});
