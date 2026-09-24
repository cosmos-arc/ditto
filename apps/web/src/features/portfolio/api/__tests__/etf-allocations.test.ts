import { afterEach, describe, expect, it, vi } from "vitest";
import { capturedRequest, requestPath } from "@/test/request";
import { executeETFPaper, listETFAllocationVersions } from "../etf-allocations";

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
