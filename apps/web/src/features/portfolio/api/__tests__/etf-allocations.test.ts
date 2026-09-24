import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest, requestPath } from "@/test/request";
import { executeETFPaper, fetchETFAllocationReview, listETFAllocationVersions } from "../etf-allocations";

const version = (allocationId: string, overrides: Record<string, unknown> = {}) => ({
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
	...overrides,
});

function fetchMock(body: unknown, status = 200) {
	return vi.fn<typeof fetch>(
		async () =>
			new Response(JSON.stringify({ data: body }), { status, headers: { "Content-Type": "application/json" } }),
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

	it("rejects a version that claims Paper authority", async () => {
		vi.stubGlobal(
			"fetch",
			fetchMock([version("demo", { review_status: "review_approved", paper_status: "paper_authorized" })]),
		);

		await expect(listETFAllocationVersions("demo")).rejects.toThrow("ETF 配置版本身份或审查状态无效");
	});
});

describe("fetchETFAllocationReview", () => {
	const query = {
		account_kind: "paper" as const,
		account_id: "paper-a",
		as_of: "2026-09-02",
		knowledge_cutoff: "2026-09-02T09:00:00Z",
		source_snapshot_ids: ["price-1"],
	};
	const response = {
		allocation_id: "demo",
		version_id: "version-one",
		account_kind: "paper",
		account_id: "paper-a",
		as_of: "2026-09-02",
		source_snapshot_ids: ["price-1"],
		valuation_snapshot_id: "valuation-1",
		ledger_hash: "ledger-1",
		target: { valuation_snapshot_id: "valuation-1", cash_weight: "0.2" },
		actual: { valuation_snapshot_id: "valuation-1", cash_weight: "0.1" },
		drift: {
			cash_drift_bps: "-1000",
			items: [{ instrument_id: 1, baseline_weight: "0.8", observed_weight: "0.9", drift_bps: "1000" }],
		},
		actual_exposure: { "000300.SH": "0.9" },
		unknown_exposure_instrument_ids: [2],
	};

	it("maps validated server values into the review view model", async () => {
		vi.stubGlobal("fetch", fetchMock(response));
		await expect(fetchETFAllocationReview("demo", "version-one", query)).resolves.toEqual({
			valuationSnapshotId: "valuation-1",
			ledgerHash: "ledger-1",
			targetCashWeight: "0.2",
			actualCashWeight: "0.1",
			cashDriftBps: "-1000",
			positions: [{ instrumentId: 1, targetWeight: "0.8", actualWeight: "0.9", driftBps: "1000" }],
			actualExposure: { "000300.SH": "0.9" },
			unknownExposureInstrumentIds: [2],
		});
	});

	it.each([
		["allocation_id", "other"],
		["version_id", "other"],
		["account_kind", "manual"],
		["account_id", "other"],
		["as_of", "2026-09-03"],
		["source_snapshot_ids", ["other"]],
		["actual", { valuation_snapshot_id: "other", cash_weight: "0.1" }],
	])("rejects a review with mismatched %s", async (field, value) => {
		vi.stubGlobal("fetch", fetchMock({ ...response, [field]: value }));
		await expect(fetchETFAllocationReview("demo", "version-one", query)).rejects.toThrow("ETF 复盘响应证据身份不匹配");
	});
});

describe("executeETFPaper", () => {
	const body = {
		authorization_id: "authorization",
		account_id: "paper",
		session_id: "session",
		signal_date: "2026-09-01",
		intended_trade_date: "2026-09-02",
		execution_cutoff: "2026-09-02T08:00:00Z",
		reference_snapshot_id: "reference",
		market_snapshot_id: "bar",
	};

	const outcome = (overrides: Record<string, unknown> = {}) => ({
		intent_id: "intent-a",
		instrument_id: 1,
		status: "filled",
		reason: null,
		execution_id: "execution-a",
		ledger_event_id: "event-a",
		...overrides,
	});

	it("maps a filled outcome with its ledger identity", async () => {
		vi.stubGlobal("fetch", fetchMock({ outcomes: [outcome()] }, 201));

		await expect(executeETFPaper("demo", "version-one", "key", body)).resolves.toEqual([
			{
				intentId: "intent-a",
				instrumentId: 1,
				status: "filled",
				reason: null,
				executionId: "execution-a",
				ledgerEventId: "event-a",
			},
		]);
	});

	it("rejects an unknown execution status", async () => {
		vi.stubGlobal("fetch", fetchMock({ outcomes: [outcome({ status: "completed" })] }, 201));

		await expect(executeETFPaper("demo", "version-one", "key", body)).rejects.toThrow(
			"ETF Paper 执行响应缺少意图或状态无效",
		);
	});

	it("rejects a filled outcome without execution or ledger identity", async () => {
		vi.stubGlobal("fetch", fetchMock({ outcomes: [outcome({ execution_id: null, ledger_event_id: null })] }, 201));

		await expect(executeETFPaper("demo", "version-one", "key", body)).rejects.toThrow(
			"ETF Paper 执行状态与执行/账本身份不匹配",
		);
	});

	it("maps a deferred outcome with execution identity only", async () => {
		vi.stubGlobal("fetch", fetchMock({ outcomes: [outcome({ status: "deferred", ledger_event_id: null })] }, 201));

		await expect(executeETFPaper("demo", "version-one", "key", body)).resolves.toMatchObject([
			{ status: "deferred", executionId: "execution-a", ledgerEventId: null },
		]);
	});

	it("rejects a rejected outcome that claims a ledger event", async () => {
		vi.stubGlobal("fetch", fetchMock({ outcomes: [outcome({ status: "rejected" })] }, 201));

		await expect(executeETFPaper("demo", "version-one", "key", body)).rejects.toThrow(
			"ETF Paper 执行状态与执行/账本身份不匹配",
		);
	});

	it("rejects a deferred outcome without an execution identity", async () => {
		vi.stubGlobal(
			"fetch",
			fetchMock({ outcomes: [outcome({ status: "deferred", execution_id: null, ledger_event_id: null })] }, 201),
		);

		await expect(executeETFPaper("demo", "version-one", "key", body)).rejects.toThrow(
			"ETF Paper 执行状态与执行/账本身份不匹配",
		);
	});

	it("rejects a no-rebalance outcome that claims identities", async () => {
		vi.stubGlobal("fetch", fetchMock({ outcomes: [outcome({ status: "no_rebalance" })] }, 201));

		await expect(executeETFPaper("demo", "version-one", "key", body)).rejects.toThrow(
			"ETF Paper 执行状态与执行/账本身份不匹配",
		);
	});
});
