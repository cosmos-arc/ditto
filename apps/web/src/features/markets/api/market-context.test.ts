import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchCurrentMarketContext, fetchMarketContext } from "./market-evidence";

describe("market context API", () => {
	it("encodes exact snapshot identities as repeated query parameters", async () => {
		let requestedUrl = "";
		server.use(
			http.get("/api/v1/market/context", ({ request }) => {
				requestedUrl = request.url;
				return HttpResponse.json({
					data: {
						as_of: "2026-08-31T09:00:00Z",
						data_conflicts: [],
						drivers: [],
						evidence_refs: [],
						feature_set_id: "market-regime:sha256:abc",
						feature_version: "market-regime.v1",
						impacts: [],
						knowledge_cutoff: "2026-08-31T08:00:00Z",
						metrics: [],
						missing_inputs: ["benchmark_return_20d"],
						publication_cutoff: "2026-08-31T07:30:00Z",
						regime_label: null,
						regime_score: null,
						source_snapshot_ids: ["snapshot-stock", "snapshot-macro"],
						source_snapshot_set_id: "snapshot-set:sha256:test",
						status: "blocked",
						uncertainties: ["market_context_source_unavailable"],
					},
				});
			}),
		);

		const result = await fetchMarketContext({
			asOf: "2026-08-31T09:00:00Z",
			knowledgeCutoff: "2026-08-31T08:00:00Z",
			publicationCutoff: "2026-08-31T07:30:00Z",
			sourceSnapshotIds: ["snapshot-stock", "snapshot-macro"],
		});

		const params = new URL(requestedUrl).searchParams;
		expect(params.getAll("source_snapshot_id")).toEqual(["snapshot-stock", "snapshot-macro"]);
		expect(params.get("as_of")).toBe("2026-08-31T09:00:00Z");
		expect(result.status).toBe("blocked");
	});

	it("rejects ambiguous empty snapshot requests before network I/O", () => {
		expect(() =>
			fetchMarketContext({
				asOf: "2026-08-31T09:00:00Z",
				knowledgeCutoff: "2026-08-31T08:00:00Z",
				publicationCutoff: "2026-08-31T07:30:00Z",
				sourceSnapshotIds: [],
			}),
		).toThrow("exact source snapshot");
	});

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
						dataset_id: params.datasetId,
						snapshot_ids: [`snapshot-${params.datasetId}`],
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
