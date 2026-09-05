import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchCurrentMarketContext } from "./market-context";

describe("current MarketContext workflow", () => {
	it("fails closed when either certified A-share core dataset is missing", async () => {
		let contextRequests = 0;
		server.use(
			http.get("/api/v1/data-products", () =>
				HttpResponse.json({
					data: [{ active_certification_report_id: "cert-stock", dataset_id: "stock_daily" }],
				}),
			),
			http.get("/api/v1/market/context", () => {
				contextRequests += 1;
				return HttpResponse.json({ data: {} });
			}),
		);

		await expect(fetchCurrentMarketContext("2026-08-31T09:00:00Z")).rejects.toThrow(
			"certified stock_daily and index_daily",
		);
		expect(contextRequests).toBe(0);
	});

	it("includes certified global index snapshots in current market context", async () => {
		let sourceSnapshotIds: string[] = [];
		server.use(
			http.get("/api/v1/data-products", () =>
				HttpResponse.json({
					data: ["stock_daily", "index_daily", "global_index_daily"].map((datasetId) => ({
						active_certification_report_id: `cert-${datasetId}`,
						dataset_id: datasetId,
					})),
				}),
			),
			http.get("/api/v1/data-products/:datasetId/evidence", ({ params }) =>
				HttpResponse.json({
					data: {
						dataset_id: params["datasetId"],
						snapshot_ids: [`snapshot-${params["datasetId"]}`],
					},
				}),
			),
			http.get("/api/v1/market/context", ({ request }) => {
				sourceSnapshotIds = new URL(request.url).searchParams.getAll("source_snapshot_id");
				return HttpResponse.json({ data: { status: "ready" } });
			}),
		);

		await fetchCurrentMarketContext("2026-08-31T09:00:00Z");

		expect(sourceSnapshotIds).toEqual(["snapshot-stock_daily", "snapshot-index_daily", "snapshot-global_index_daily"]);
	});
});
