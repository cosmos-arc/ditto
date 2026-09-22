import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest } from "@/test/request";
import { fetchPaperAccountHistory, type PaperHistoryQueryIdentity } from "../paper-accounts";

const identity: PaperHistoryQueryIdentity = {
	session_id: "paper-session-1",
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
		result_id: "paper-history:sha256:result-1",
		account_id: "paper-main",
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
				total_value: "109.00",
				cash: "-1.00",
				external_flow: "0",
				period_return: "0.09",
				cumulative_return: "0.09",
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
				end_value: "109.00",
				linked_return: "0.09",
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

describe("paper history API", () => {
	it("sends the session-bound replay identity and parses the series", async () => {
		const fetchMock = stubFetch(historyPayload());
		vi.stubGlobal("fetch", fetchMock);

		const history = await fetchPaperAccountHistory("paper-main", identity);

		const request = capturedRequest(fetchMock.mock.calls);
		const url = new URL(request.url);
		expect(url.pathname).toBe("/api/v1/paper/accounts/paper-main/history");
		expect(url.searchParams.get("session_id")).toBe("paper-session-1");
		expect(url.searchParams.get("ledger_event_count")).toBe("3");
		expect(url.searchParams.get("ledger_hash")).toBe("account-ledger:sha256:abc");
		expect(url.searchParams.getAll("source_snapshot_ids")).toEqual(["snapshot:stock_daily:1"]);
		expect(request.method).toBe("GET");

		expect(history.result_id).toBe("paper-history:sha256:result-1");
		expect(history.points[1]?.total_value).toBe("109.00");
		expect(history.segments[0]?.linked_return).toBe("0.09");
	});

	it.each([
		["end_date", "2026-03-09"],
		["account_id", "paper-other"],
	] as const)("rejects identity drift in %s", async (key, value) => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ [key]: value })));
		await expect(fetchPaperAccountHistory("paper-main", identity)).rejects.toThrow();
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
		await expect(fetchPaperAccountHistory("paper-main", identity)).rejects.toThrow();
	});

	it("rejects a manual-series payload delivered through the paper transport", async () => {
		vi.stubGlobal("fetch", stubFetch(historyPayload({ result_id: "manual-history:sha256:result-1" })));
		await expect(fetchPaperAccountHistory("paper-main", identity)).rejects.toThrow(/paper-history:sha256:/);
	});

	it("fails closed on a malformed payload", async () => {
		vi.stubGlobal("fetch", stubFetch({ segments: "not-a-list" }));
		await expect(fetchPaperAccountHistory("paper-main", identity)).rejects.toThrow();
	});
});
