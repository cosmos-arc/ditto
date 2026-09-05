import { describe, expect, it } from "vitest";
import { DEFAULT_STRATEGY_ID, tradingKeys } from "./query-keys";

const portfolioIdentity = {
	strategy_id: "strategy-1",
	model_portfolio_id: "model-1",
	paper_account_id: "paper-1",
	manual_account_id: "manual-1",
	paper_session_id: "session-1",
	as_of: "2026-09-04",
	knowledge_cutoff: "2026-09-04T08:00:00Z",
	publication_cutoff: "2026-09-04T07:30:00Z",
	source_snapshot_ids: ["snapshot-z", "snapshot-a"],
} as const;

describe("tradingKeys", () => {
	it("uses explicit fail-closed sentinels when optional trading scope is unresolved", () => {
		expect(tradingKeys.dailyDecision()).toEqual([
			"trading",
			"daily-decision",
			DEFAULT_STRATEGY_ID,
			"latest",
			"account-unselected",
		]);
		expect(tradingKeys.dailyDecisionV3()).toEqual([
			"trading",
			"daily-decision",
			"v3",
			DEFAULT_STRATEGY_ID,
			"latest",
			"account-unselected",
		]);
		expect(tradingKeys.signals()).toEqual(["trading", "signals", DEFAULT_STRATEGY_ID, "latest"]);
		expect(tradingKeys.intents()).toEqual(["trading", "intents", DEFAULT_STRATEGY_ID, "all"]);
		expect(tradingKeys.fills()).toEqual(["trading", "fills", DEFAULT_STRATEGY_ID, "start", "end"]);
		expect(tradingKeys.positions()).toEqual(["trading", "positions", DEFAULT_STRATEGY_ID, "latest"]);
		expect(tradingKeys.pnl()).toEqual(["trading", "pnl", DEFAULT_STRATEGY_ID, "latest"]);
		expect(tradingKeys.deviation()).toEqual(["trading", "deviation", DEFAULT_STRATEGY_ID, "latest"]);
	});

	it("keeps every caller-provided scope dimension in the cache identity", () => {
		expect(tradingKeys.dailyDecision("strategy-2", "2026-09-03", "account-2")).toEqual([
			"trading",
			"daily-decision",
			"strategy-2",
			"2026-09-03",
			"account-2",
		]);
		expect(tradingKeys.dailyDecisionV3("strategy-2", "2026-09-03", "account-2")).toEqual([
			"trading",
			"daily-decision",
			"v3",
			"strategy-2",
			"2026-09-03",
			"account-2",
		]);
		expect(tradingKeys.signals("strategy-2", "2026-09-03")).toEqual(["trading", "signals", "strategy-2", "2026-09-03"]);
		expect(tradingKeys.intents("strategy-2", "pending")).toEqual(["trading", "intents", "strategy-2", "pending"]);
		expect(tradingKeys.fills("strategy-2", "2026-09-01", "2026-09-03")).toEqual([
			"trading",
			"fills",
			"strategy-2",
			"2026-09-01",
			"2026-09-03",
		]);
		expect(tradingKeys.positions("strategy-2", "2026-09-03")).toEqual([
			"trading",
			"positions",
			"strategy-2",
			"2026-09-03",
		]);
		expect(tradingKeys.pnl("strategy-2", "2026-09-03")).toEqual(["trading", "pnl", "strategy-2", "2026-09-03"]);
		expect(tradingKeys.deviation("strategy-2", "2026-09-03")).toEqual([
			"trading",
			"deviation",
			"strategy-2",
			"2026-09-03",
		]);
	});

	it("canonicalizes snapshot order and distinguishes unresolved valuation evidence", () => {
		expect(tradingKeys.portfolioComparison(portfolioIdentity)).toEqual([
			"trading",
			"portfolio-comparison",
			"strategy-1",
			"model-1",
			"paper-1",
			"manual-1",
			"session-1",
			"2026-09-04",
			"2026-09-04T08:00:00Z",
			"2026-09-04T07:30:00Z",
			"snapshot-a|snapshot-z",
			"valuation-unresolved",
		]);
		expect(tradingKeys.portfolioComparison({ ...portfolioIdentity, valuation_snapshot_id: "valuation-42" })).toEqual([
			"trading",
			"portfolio-comparison",
			"strategy-1",
			"model-1",
			"paper-1",
			"manual-1",
			"session-1",
			"2026-09-04",
			"2026-09-04T08:00:00Z",
			"2026-09-04T07:30:00Z",
			"snapshot-a|snapshot-z",
			"valuation-42",
		]);
	});
});
