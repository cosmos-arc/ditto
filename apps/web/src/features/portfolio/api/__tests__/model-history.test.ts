import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest } from "@/test/request";
import { fetchModelHistory, type ModelHistoryIdentity } from "../portfolio-comparison";

const identity: ModelHistoryIdentity = {
	strategy_id: "strategy-model",
	start_date: "2026-03-02",
	end_date: "2026-03-04",
	initial_capital: "100",
	knowledge_cutoff: "2026-03-04T08:00:00Z",
	publication_cutoff: "2026-03-04T08:00:00Z",
};

function historyPayload(overrides?: Record<string, unknown>) {
	return {
		result_id: "model-history:sha256:result-1",
		strategy_id: "strategy-model",
		currency: "CNY",
		start_date: identity.start_date,
		end_date: identity.end_date,
		initial_capital: "100.00",
		knowledge_cutoff: identity.knowledge_cutoff,
		publication_cutoff: identity.publication_cutoff,
		targets: [
			{
				signal_date: "2026-03-02",
				artifact_id: "signal-package-a",
				checksum: "sha256:aaa",
			},
			{
				signal_date: "2026-03-03",
				artifact_id: "signal-package-b",
				checksum: "sha256:bbb",
			},
		],
		method: "twr-linked-v1",
		valuation_policy_version: "account-valuation-stale-evidence-v1",
		points: [
			{
				on_date: "2026-03-02",
				valuation_instant: "2026-03-02T23:59:59.999999+08:00",
				total_value: "100.00",
				cash: "0.00",
				external_flow: "0",
				period_return: null,
				cumulative_return: "0",
				segment_id: 0,
				price_time: "2026-03-02T07:00:00Z",
				stale: false,
				source_snapshot_ids: ["snapshot:stock_daily:1"],
				quality: [],
			},
			{
				on_date: "2026-03-03",
				valuation_instant: "2026-03-03T23:59:59.999999+08:00",
				total_value: "110.00",
				cash: "0.00",
				external_flow: "0",
				period_return: "0.1",
				cumulative_return: "0.1",
				segment_id: 0,
				price_time: "2026-03-03T07:00:00Z",
				stale: false,
				source_snapshot_ids: ["snapshot:stock_daily:1"],
				quality: [],
			},
		],
		segments: [
			{
				segment_id: 0,
				start_date: "2026-03-02",
				end_date: "2026-03-03",
				start_value: "100.00",
				end_value: "110.00",
				linked_return: "0.1",
				closed_reason: "range_end",
				quality: [],
			},
		],
		...overrides,
	};
}

function stubFetch(payload: unknown) {
	return vi.fn<typeof fetch>(
		async () =>
			new Response(JSON.stringify({ data: payload }), {
				status: 200,
				headers: { "Content-Type": "application/json" },
			}),
	);
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("model history API", () => {
	it("sends the replay identity and parses targets and points", async () => {
		const fetchMock = stubFetch(historyPayload());
		vi.stubGlobal("fetch", fetchMock);

		const history = await fetchModelHistory(identity);

		const request = capturedRequest(fetchMock.mock.calls);
		const url = new URL(request.url);
		expect(url.pathname).toBe("/api/v1/portfolio/model-history");
		expect(url.searchParams.get("strategy_id")).toBe("strategy-model");
		expect(url.searchParams.get("initial_capital")).toBe("100");
		expect(url.searchParams.has("artifact_ids")).toBe(false);
		expect(request.method).toBe("GET");

		expect(history.result_id).toBe("model-history:sha256:result-1");
		expect(history.targets).toHaveLength(2);
		expect(history.targets[1]?.artifact_id).toBe("signal-package-b");
		expect(history.points[1]?.total_value).toBe("110.00");
		expect(history.segments[0]?.linked_return).toBe("0.1");
	});

	it("sends pinned artifact ids when provided", async () => {
		const fetchMock = stubFetch(historyPayload());
		vi.stubGlobal("fetch", fetchMock);
		await fetchModelHistory({ ...identity, artifact_ids: ["signal-package-a"] });
		const request = capturedRequest(fetchMock.mock.calls);
		const url = new URL(request.url);
		expect(url.searchParams.getAll("artifact_ids")).toEqual(["signal-package-a"]);
	});

	it.each([
		["end_date", "2026-03-09"],
		["strategy_id", "strategy-other"],
	] as const)("rejects identity drift in %s", async (key, value) => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ [key]: value })));
		await expect(fetchModelHistory(identity)).rejects.toThrow();
	});

	it("rejects an initial capital that differs from the request", async () => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ initial_capital: "200.00" })));
		await expect(fetchModelHistory(identity)).rejects.toThrow();
	});

	it("accepts an equivalent capital echo format", async () => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ initial_capital: "100" })));
		await expect(fetchModelHistory(identity)).resolves.toBeTruthy();
	});

	it("rejects an account-series payload delivered through the model transport", async () => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ result_id: "paper-history:sha256:result-1" })));
		await expect(fetchModelHistory(identity)).rejects.toThrow(/model-history:sha256:/);
	});

	it("fails closed on a malformed payload", async () => {
		vi.stubGlobal("fetch", stubFetch({ targets: "not-a-list" }));
		await expect(fetchModelHistory(identity)).rejects.toThrow();
	});
});
