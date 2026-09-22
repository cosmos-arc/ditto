import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest } from "@/test/request";
import { fetchManualAccountHistory, type ManualHistoryQueryIdentity } from "../manual-accounts";

const identity: ManualHistoryQueryIdentity = {
	start_date: "2026-03-02",
	end_date: "2026-03-04",
	knowledge_cutoff: "2026-03-04T08:00:00Z",
	publication_cutoff: "2026-03-04T08:00:00Z",
	source_snapshot_ids: ["snapshot:stock_daily:1"],
	ledger_event_count: 3,
	ledger_hash: "account-ledger:sha256:abc",
};

function historyPayload(overrides?: Record<string, unknown>) {
	return {
		result_id: "manual-history:sha256:result-1",
		account_id: "manual-main",
		currency: "CNY",
		start_date: identity.start_date,
		end_date: identity.end_date,
		knowledge_cutoff: identity.knowledge_cutoff,
		publication_cutoff: identity.publication_cutoff,
		source_snapshot_ids: [...identity.source_snapshot_ids],
		ledger_revision: {
			event_count: identity.ledger_event_count,
			ledger_hash: identity.ledger_hash,
		},
		method: "twr-linked-v1",
		valuation_policy_version: "manual-valuation-stale-evidence-v1",
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
				total_value: null,
				cash: "10.00",
				external_flow: "0",
				period_return: null,
				cumulative_return: null,
				segment_id: null,
				price_time: null,
				stale: false,
				source_snapshot_ids: [],
				quality: [{ code: "price_missing", detail: "600519" }],
			},
			{
				on_date: "2026-03-04",
				valuation_instant: "2026-03-04T23:59:59.999999+08:00",
				total_value: "121.00",
				cash: "0.00",
				external_flow: "100.00",
				period_return: "0.1",
				cumulative_return: "0.1",
				segment_id: 1,
				price_time: "2026-03-04T07:00:00Z",
				stale: true,
				source_snapshot_ids: ["snapshot:stock_daily:1"],
				quality: [{ code: "stale_price", detail: "600519:2026-03-03" }],
			},
		],
		segments: [
			{
				segment_id: 0,
				start_date: "2026-03-02",
				end_date: "2026-03-02",
				start_value: "100.00",
				end_value: "100.00",
				linked_return: null,
				closed_reason: "valuation_gap",
				quality: [{ code: "valuation_gap", detail: "2026-03-04" }],
			},
			{
				segment_id: 1,
				start_date: "2026-03-04",
				end_date: "2026-03-04",
				start_value: "110.00",
				end_value: "121.00",
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

describe("manual history API", () => {
	it("sends the exact replay identity and parses gap and stale rows", async () => {
		const fetchMock = stubFetch(historyPayload());
		vi.stubGlobal("fetch", fetchMock);

		const history = await fetchManualAccountHistory("manual-main", identity);

		const request = capturedRequest(fetchMock.mock.calls);
		const url = new URL(request.url);
		expect(url.pathname).toBe("/api/v1/manual/accounts/manual-main/history");
		expect(url.searchParams.get("start_date")).toBe("2026-03-02");
		expect(url.searchParams.get("end_date")).toBe("2026-03-04");
		expect(url.searchParams.get("ledger_event_count")).toBe("3");
		expect(url.searchParams.get("ledger_hash")).toBe("account-ledger:sha256:abc");
		expect(url.searchParams.getAll("source_snapshot_ids")).toEqual(["snapshot:stock_daily:1"]);
		expect(request.method).toBe("GET");

		expect(history.result_id).toBe("manual-history:sha256:result-1");
		expect(history.points[1]?.total_value).toBeNull();
		expect(history.points[1]?.cash).toBe("10.00");
		expect(history.points[1]?.quality[0]?.code).toBe("price_missing");
		expect(history.points[2]?.stale).toBe(true);
		expect(history.segments[0]?.closed_reason).toBe("valuation_gap");
		expect(history.segments[1]?.linked_return).toBe("0.1");
	});

	it.each([
		["end_date", "2026-03-09"],
		["account_id", "manual-other"],
	] as const)("rejects identity drift in %s", async (key, value) => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ [key]: value })));
		await expect(fetchManualAccountHistory("manual-main", identity)).rejects.toThrow();
	});

	it("rejects a ledger revision that differs from the request", async () => {
		vi.stubGlobal(
			"fetch",
			stubFetch(
				historyPayload({
					ledger_revision: { event_count: 4, ledger_hash: "account-ledger:sha256:other" },
				}),
			),
		);
		await expect(fetchManualAccountHistory("manual-main", identity)).rejects.toThrow();
	});

	it("accepts a backend datetime echo in an equivalent instant format", async () => {
		vi.stubGlobal(
			"fetch",
			stubFetch(
				historyPayload({
					knowledge_cutoff: "2026-03-04T16:00:00.000000Z",
					publication_cutoff: "2026-03-04T16:00:00Z",
				}),
			),
		);
		await expect(
			fetchManualAccountHistory("manual-main", {
				...identity,
				knowledge_cutoff: "2026-03-04T16:00:00Z",
				publication_cutoff: "2026-03-04T16:00:00Z",
			}),
		).resolves.toBeTruthy();
	});

	it("rejects a datetime echo that is a different instant", async () => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ knowledge_cutoff: "2026-03-05T16:00:00Z" })));
		await expect(fetchManualAccountHistory("manual-main", identity)).rejects.toThrow();
	});

	it("fails closed on a malformed payload", async () => {
		vi.stubGlobal("fetch", stubFetch({ points: "not-a-list" }));
		await expect(fetchManualAccountHistory("manual-main", identity)).rejects.toThrow();
	});
});
