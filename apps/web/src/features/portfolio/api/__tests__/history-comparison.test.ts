import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest } from "@/test/request";
import { fetchHistoryComparison, fetchStrategyOptions, type HistoryComparisonIdentity } from "../portfolio-comparison";

const identity: HistoryComparisonIdentity = {
	strategy_id: "strategy-compare",
	paper_account_id: "paper-1",
	paper_session_id: "paper-session-1",
	manual_account_id: "manual-1",
	start_date: "2026-03-02",
	end_date: "2026-03-04",
	model_initial_capital: 100,
	knowledge_cutoff: "2026-03-04T08:00:00Z",
	publication_cutoff: "2026-03-04T08:00:00Z",
	source_snapshot_ids: ["snapshot:stock_daily:1"],
};

function runPayload() {
	return {
		start_date: "2026-03-02",
		end_date: "2026-03-04",
		point_count: 3,
		points: [
			{
				on_date: "2026-03-02",
				growth: { model: "1", paper: "1", manual: "1" },
				assets: { model: "100.00", paper: "100.00", manual: "100.00" },
			},
			{
				on_date: "2026-03-03",
				growth: { model: "1.1", paper: "1.09", manual: "1.08" },
				assets: { model: "110.00", paper: "109.00", manual: "108.00" },
			},
			{
				on_date: "2026-03-04",
				growth: { model: "1.21", paper: "1.105", manual: "1.168" },
				assets: { model: "121.00", paper: "110.50", manual: "116.80" },
			},
		],
		window_returns: { model: "0.21", paper: "0.105", manual: "0.168" },
	};
}

function legPayload() {
	return [
		{
			kind: "model",
			result_id: "model-history:sha256:leg-1",
			currency: "CNY",
			empty_reason: null,
			point_count: 3,
			valued_point_count: 3,
			gap_count: 0,
			segment_count: 1,
			first_valued_date: "2026-03-02",
			last_valued_date: "2026-03-04",
			ledger_revision: null,
			target_count: 2,
		},
		{
			kind: "paper",
			result_id: "paper-history:sha256:leg-2",
			currency: "CNY",
			empty_reason: null,
			point_count: 3,
			valued_point_count: 3,
			gap_count: 0,
			segment_count: 1,
			first_valued_date: "2026-03-02",
			last_valued_date: "2026-03-04",
			ledger_revision: { event_count: 3, ledger_hash: "account-ledger:sha256:abc" },
			target_count: null,
		},
		{
			kind: "manual",
			result_id: "manual-history:sha256:leg-3",
			currency: "CNY",
			empty_reason: null,
			point_count: 3,
			valued_point_count: 3,
			gap_count: 0,
			segment_count: 1,
			first_valued_date: "2026-03-02",
			last_valued_date: "2026-03-04",
			ledger_revision: { event_count: 2, ledger_hash: "account-ledger:sha256:def" },
			target_count: null,
		},
	];
}

function comparisonPayload(overrides?: Record<string, unknown>) {
	return {
		result_id: "history-comparison:sha256:result-1",
		strategy_id: identity.strategy_id,
		paper_account_id: identity.paper_account_id,
		paper_session_id: identity.paper_session_id,
		manual_account_id: identity.manual_account_id,
		model_initial_capital: "100.00",
		currency: "CNY",
		method: "twr-linked-v1",
		valuation_policy_version: "account-valuation-stale-evidence-v1",
		comparison_policy_version: "common-window-twr-v1",
		status: "comparable",
		empty_reason: null,
		start_date: identity.start_date,
		end_date: identity.end_date,
		knowledge_cutoff: identity.knowledge_cutoff,
		publication_cutoff: identity.publication_cutoff,
		runs: [runPayload()],
		legs: legPayload(),
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

describe("history comparison API", () => {
	it("sends the shared identity and parses runs and legs", async () => {
		const fetchMock = stubFetch(comparisonPayload());
		vi.stubGlobal("fetch", fetchMock);

		const comparison = await fetchHistoryComparison(identity);

		const request = capturedRequest(fetchMock.mock.calls);
		const url = new URL(request.url);
		expect(url.pathname).toBe("/api/v1/portfolio/history-comparison");
		expect(url.searchParams.get("strategy_id")).toBe("strategy-compare");
		expect(url.searchParams.get("paper_account_id")).toBe("paper-1");
		expect(url.searchParams.get("paper_session_id")).toBe("paper-session-1");
		expect(url.searchParams.get("manual_account_id")).toBe("manual-1");
		expect(url.searchParams.get("model_initial_capital")).toBe("100");
		expect(request.method).toBe("GET");

		expect(comparison.result_id).toBe("history-comparison:sha256:result-1");
		expect(comparison.status).toBe("comparable");
		expect(comparison.runs).toHaveLength(1);
		expect(comparison.runs[0]?.points[2]?.growth.model).toBe("1.21");
		expect(comparison.runs[0]?.window_returns.paper).toBe("0.105");
		const paperLeg = comparison.legs.find((leg) => leg.kind === "paper");
		expect(paperLeg?.ledger_revision?.event_count).toBe(3);
		const modelLeg = comparison.legs.find((leg) => leg.kind === "model");
		expect(modelLeg?.target_count).toBe(2);
	});

	it.each([
		["strategy_id", "strategy-other"],
		["paper_account_id", "paper-2"],
		["paper_session_id", "paper-session-2"],
		["manual_account_id", "manual-2"],
		["end_date", "2026-03-09"],
	] as const)("rejects identity drift in %s", async (key, value) => {
		vi.stubGlobal("fetch", stubFetch(comparisonPayload({ [key]: value })));
		await expect(fetchHistoryComparison(identity)).rejects.toThrow();
	});

	it("rejects a capital that differs from the request", async () => {
		vi.stubGlobal("fetch", stubFetch(comparisonPayload({ model_initial_capital: "200.00" })));
		await expect(fetchHistoryComparison(identity)).rejects.toThrow(/model_initial_capital/);
	});

	it("accepts an equivalent capital echo format", async () => {
		vi.stubGlobal("fetch", stubFetch(comparisonPayload({ model_initial_capital: "100" })));
		await expect(fetchHistoryComparison(identity)).resolves.toBeTruthy();
	});

	it("rejects a foreign result identity", async () => {
		vi.stubGlobal("fetch", stubFetch(comparisonPayload({ result_id: "model-history:sha256:x" })));
		await expect(fetchHistoryComparison(identity)).rejects.toThrow(/history-comparison:sha256:/);
	});

	it("parses single-point runs with null window returns", async () => {
		const singleRun = {
			start_date: "2026-03-02",
			end_date: "2026-03-02",
			point_count: 1,
			points: [
				{
					on_date: "2026-03-02",
					growth: { model: "1", paper: "1", manual: "1" },
					assets: { model: "100.00", paper: "100.00", manual: "100.00" },
				},
			],
			window_returns: { model: null, paper: null, manual: null },
		};
		vi.stubGlobal("fetch", stubFetch(comparisonPayload({ status: "single_common_point", runs: [singleRun] })));
		const comparison = await fetchHistoryComparison(identity);
		expect(comparison.status).toBe("single_common_point");
		expect(comparison.runs[0]?.window_returns.model).toBeNull();
		expect(comparison.runs[0]?.points[0]?.assets.manual).toBe("100.00");
	});

	it("parses an explicit incomparable outcome", async () => {
		vi.stubGlobal(
			"fetch",
			stubFetch(comparisonPayload({ status: "incomparable", empty_reason: "no_common_valuation_dates", runs: [] })),
		);
		const comparison = await fetchHistoryComparison(identity);
		expect(comparison.status).toBe("incomparable");
		expect(comparison.empty_reason).toBe("no_common_valuation_dates");
		expect(comparison.runs).toHaveLength(0);
	});

	it("fails closed on a malformed run payload", async () => {
		vi.stubGlobal(
			"fetch",
			stubFetch(comparisonPayload({ runs: [{ start_date: "2026-03-02", points: "not-a-list" }] })),
		);
		await expect(fetchHistoryComparison(identity)).rejects.toThrow();
	});

	it("fails closed when a leg is missing its per-kind growth entry", async () => {
		const brokenRun = runPayload();
		const firstPoint = brokenRun.points[0];
		if (firstPoint) {
			firstPoint.growth = { model: "1", paper: "1" } as typeof firstPoint.growth;
		}
		vi.stubGlobal("fetch", stubFetch(comparisonPayload({ runs: [brokenRun] })));
		await expect(fetchHistoryComparison(identity)).rejects.toThrow(/manual/);
	});
});

describe("strategy options API", () => {
	it("parses the bare strategy array the endpoint really returns", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: [
							{
								strategy_id: "strategy-compare",
								name: "比较策略",
								version: 1,
								status: "active",
								lifecycle_state: "active",
								created_at: "2026-01-01T00:00:00Z",
								tags: [],
							},
						],
						pagination: { total: 1, limit: 100, offset: 0 },
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		const options = await fetchStrategyOptions();

		const request = capturedRequest(fetchMock.mock.calls);
		const url = new URL(request.url);
		expect(url.pathname).toBe("/api/v1/strategies");
		expect(url.searchParams.get("limit")).toBe("100");
		expect(options).toEqual([{ strategy_id: "strategy-compare", name: "比较策略" }]);
	});

	it("fails closed on a malformed strategy entry", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(
				async () =>
					new Response(JSON.stringify({ data: [{ strategy_id: "strategy-compare" }] }), {
						status: 200,
						headers: { "Content-Type": "application/json" },
					}),
			),
		);
		await expect(fetchStrategyOptions()).rejects.toThrow(/name/);
	});
});
