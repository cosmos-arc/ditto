import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchSystemRemediation } from "./system-overview";

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
});
