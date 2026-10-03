import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { fetchMarketContext } from "./market-evidence";

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

	it("omits source_snapshot_id params so the server resolves observed snapshots", async () => {
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
						missing_inputs: [],
						publication_cutoff: "2026-08-31T07:30:00Z",
						regime_label: "risk_on",
						regime_score: 0.2,
						source_snapshot_ids: [],
						source_snapshot_set_id: "snapshot-set:sha256:observed",
						status: "ready",
						uncertainties: [],
					},
				});
			}),
		);

		const result = await fetchMarketContext({
			asOf: "2026-08-31T09:00:00Z",
			knowledgeCutoff: "2026-08-31T08:00:00Z",
			publicationCutoff: "2026-08-31T07:30:00Z",
			sourceSnapshotIds: [],
		});

		const params = new URL(requestedUrl).searchParams;
		expect(params.getAll("source_snapshot_id")).toEqual([]);
		expect(result.status).toBe("ready");
	});

	it("still rejects duplicate snapshot identities before network I/O", () => {
		expect(() =>
			fetchMarketContext({
				asOf: "2026-08-31T09:00:00Z",
				knowledgeCutoff: "2026-08-31T08:00:00Z",
				publicationCutoff: "2026-08-31T07:30:00Z",
				sourceSnapshotIds: ["snapshot-stock", "snapshot-stock"],
			}),
		).toThrow("unique exact source snapshot");
	});
});
