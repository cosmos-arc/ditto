import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest, requestPath } from "@/test/request";
import { listETFAllocationVersions } from "../etf-allocations";

const version = (allocationId: string) => ({
	version_id: "version-one",
	allocation_id: allocationId,
	parent_version_id: null,
	asof: "2026-09-01",
	knowledge_cutoff: "2026-09-01T09:00:00Z",
	source_snapshot_id: "snapshot:recorded:etf",
	mode: "equal",
	weights: { "1": "0.80000000" },
	cash_weight: "0.2",
	max_position_weight: "1",
	tracking_exposure: { "000300.SH": "0.80000000" },
	reason: "broad exposure",
	rule_version: "etf-allocation-v1",
	paper_status: "research_only",
	review_status: "research_only",
	created_at: "2026-09-01T09:00:00Z",
});

function fetchMock(body: unknown) {
	return vi.fn<typeof fetch>(
		async () =>
			new Response(JSON.stringify({ data: body }), { status: 200, headers: { "Content-Type": "application/json" } }),
	);
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("listETFAllocationVersions", () => {
	it("returns versions of the requested allocation", async () => {
		const fetch = fetchMock([version("demo")]);
		vi.stubGlobal("fetch", fetch);

		await expect(listETFAllocationVersions("demo")).resolves.toHaveLength(1);
		expect(requestPath(capturedRequest(fetch.mock.calls))).toBe("/api/v1/portfolio/etf-allocations/demo/versions");
	});

	it("rejects a cross-scoped version list instead of trusting it", async () => {
		vi.stubGlobal("fetch", fetchMock([version("other")]));

		await expect(listETFAllocationVersions("demo")).rejects.toThrow("ETF 配置版本响应不属于该配置");
	});
});
