import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import {
	type AssembleSelectionRunBody,
	compareSelectionRuns,
	createSelectionRun,
	getIndustryRotation,
	getSelectionRun,
	listSelectionRuns,
	listUniverseOptions,
} from "./api";

const policyBody: AssembleSelectionRunBody = {
	as_of: "2026-08-31T07:00:00Z",
	asset_kind: "stock",
	excluded_limit_states: ["limit_up", "limit_down"],
	factor_weights: [{ name: "momentum_1m", weight: 1 }],
	lookback_days: 400,
	min_average_turnover: 20_000_000,
	min_listing_days: 120,
	seed: 17,
	spec_id: "stock-core",
	spec_version: "1",
	top_k: 10,
	universe_id: "a-share-custom-202609",
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
				expect(await request.json()).toEqual(policyBody);
				return HttpResponse.json({ data: { selection_run: { run_id: "run-new" } } }, { status: 201 });
			}),
		);

		await listSelectionRuns("stock core", 12);
		await getSelectionRun("run/one");
		await getIndustryRotation("rotation/one");
		await compareSelectionRuns("run/before", "run/after");
		await createSelectionRun(policyBody);

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

describe("listUniverseOptions pagination", () => {
	it("keeps fetching pages until a short page arrives", async () => {
		const requested: string[] = [];
		const fullPage = Array.from({ length: 100 }, (_, i) => ({
			universe_id: `u-${i}`,
			name: `U${i}`,
			universe_type: "custom",
		}));
		server.use(
			http.get("/api/v1/universes", ({ request }) => {
				requested.push(request.url);
				const offset = Number(new URL(request.url).searchParams.get("offset") ?? "0");
				return HttpResponse.json({ data: offset === 0 ? fullPage : fullPage.slice(0, 3) });
			}),
		);

		const options = await listUniverseOptions();
		expect(options).toHaveLength(103);
		expect(requested).toHaveLength(2);
		expect(new URL(requested[0]!).searchParams.get("offset")).toBe("0");
		expect(new URL(requested[1]!).searchParams.get("offset")).toBe("100");
	});
});
