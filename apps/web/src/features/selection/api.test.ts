import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import {
	type CreateSelectionRunBody,
	compareSelectionRuns,
	createSelectionRun,
	getIndustryRotation,
	getSelectionRun,
	listSelectionRuns,
} from "./api";

const runBody: CreateSelectionRunBody = {
	as_of: "2026-08-31T07:00:00Z",
	industries: [],
	instruments: [],
	knowledge_cutoff: "2026-08-31T07:00:00Z",
	market_context_feature_set_id: null,
	membership_version: "sw-l1:2026-08-31",
	publication_cutoff: "2026-08-31T07:00:00Z",
	rotation_algorithm_version: "industry-rotation-v1",
	rotation_missing_inputs: ["industry_inputs"],
	rotation_source_snapshot_ids: ["market-a"],
	seed: 17,
	selection_source_snapshot_ids: ["market-a"],
	selection_spec: {
		asset_kind: "stock",
		excluded_limit_states: ["limit_up", "limit_down"],
		factor_weights: [{ name: "momentum", weight: 1 }],
		min_average_turnover: 20_000_000,
		min_listing_days: 120,
		spec_id: "stock-core",
		spec_version: "1",
		top_k: 10,
	},
	universe_snapshot_id: "universe:sha256:abc",
};

describe("selection API", () => {
	it("uses exact run, snapshot, compare, and create paths", async () => {
		const requests: string[] = [];
		server.use(
			http.get("/api/v1/selections/runs", ({ request }) => {
				requests.push(request.url);
				return HttpResponse.json({ data: [] });
			}),
			http.get("/api/v1/selections/runs/:runId", ({ request, params }) => {
				requests.push(request.url);
				return HttpResponse.json({ data: { run_id: params["runId"] } });
			}),
			http.get("/api/v1/selections/industry-rotations/:snapshotId", ({ request, params }) => {
				requests.push(request.url);
				return HttpResponse.json({ data: { snapshot_id: params["snapshotId"] } });
			}),
			http.get("/api/v1/selections/runs/:before/compare/:after", ({ request, params }) => {
				requests.push(request.url);
				return HttpResponse.json({
					data: { after_run_id: params["after"], before_run_id: params["before"] },
				});
			}),
			http.post("/api/v1/selections/runs", async ({ request }) => {
				requests.push(request.url);
				expect(await request.json()).toEqual(runBody);
				return HttpResponse.json({ data: { selection_run: { run_id: "run-new" } } }, { status: 201 });
			}),
		);

		await listSelectionRuns("stock core", 12);
		await getSelectionRun("run/one");
		await getIndustryRotation("rotation/one");
		await compareSelectionRuns("run/before", "run/after");
		await createSelectionRun(runBody);

		expect(requests.map((value) => new URL(value).pathname)).toEqual([
			"/api/v1/selections/runs",
			"/api/v1/selections/runs/run%2Fone",
			"/api/v1/selections/industry-rotations/rotation%2Fone",
			"/api/v1/selections/runs/run%2Fbefore/compare/run%2Fafter",
			"/api/v1/selections/runs",
		]);
		expect(new URL(requests[0] ?? "").searchParams.get("spec_id")).toBe("stock core");
	});

	it("fails closed before compare when exact run identities are not distinct", () => {
		expect(() => compareSelectionRuns("same", "same")).toThrow("distinct exact run IDs");
	});
});
