import { afterEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/api/generated/schema";
import { capturedRequest, requestJson, requestPath } from "@/test/request";
import {
	fetchPortfolioComparison,
	type PortfolioComparisonIdentity,
	previewPortfolioScenario,
} from "../portfolio-comparison";

type Comparison = components["schemas"]["PortfolioComparisonResponse"];
type Scenario = components["schemas"]["PortfolioScenarioPreviewResponse"];

const identity: PortfolioComparisonIdentity = {
	strategy_id: "strategy-1",
	model_portfolio_id: "model-main",
	paper_account_id: "paper-main",
	manual_account_id: "manual-main",
	paper_session_id: "paper-session-1",
	as_of: "2026-08-31",
	knowledge_cutoff: "2026-08-31T15:00:00+08:00",
	publication_cutoff: "2026-08-31T15:00:00+08:00",
	source_snapshot_ids: ["snapshot:stock", "snapshot:fund"],
	valuation_snapshot_id: "valuation:abc",
};

afterEach(() => {
	vi.unstubAllGlobals();
});

describe("portfolio comparison API", () => {
	it.each([
		["strategy_id", "other", "strategy_id"],
		["as_of", "2026-09-01", "as_of"],
		["source_snapshot_ids", ["snapshot:other", "snapshot:fund"], "source snapshot"],
		["source_snapshot_ids", [], "source snapshot"],
		["valuation_snapshot_id", "valuation:other", "valuation snapshot"],
	] as const)("rejects comparison identity drift in %s", async (key, value, message) => {
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () =>
				Response.json({
					data: {
						strategy_id: identity.strategy_id,
						as_of: identity.as_of,
						source_snapshot_ids: identity.source_snapshot_ids,
						valuation_snapshot_id: identity.valuation_snapshot_id,
						[key]: value,
					},
				}),
			),
		);
		await expect(fetchPortfolioComparison(identity)).rejects.toThrow(message);
	});

	it("accepts reordered source snapshots without an optional valuation constraint", async () => {
		const { valuation_snapshot_id: _valuation, ...unconstrained } = identity;
		const payload = {
			strategy_id: identity.strategy_id,
			as_of: identity.as_of,
			source_snapshot_ids: [...identity.source_snapshot_ids].reverse(),
			valuation_snapshot_id: "valuation:chosen",
		};
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () => Response.json({ data: payload })),
		);
		await expect(fetchPortfolioComparison(unconstrained)).resolves.toEqual(payload);
	});

	it.each([
		["baseline_kind", "model", "baseline"],
		["as_of", "2026-09-01", "as_of"],
		["source_snapshot_ids", ["snapshot:other"], "source snapshot"],
	] as const)("rejects scenario identity drift in %s", async (key, value, message) => {
		const payload = {
			baseline_kind: key === "baseline_kind" ? value : "paper",
			proposed_weights: {},
			applied_constraints: [],
			risk: {
				before: { cash_weight: 0.1, gross_exposure: 0.9, industry_exposure: {}, stressed_return: -0.04 },
				after: { cash_weight: 0.15, gross_exposure: 0.85, industry_exposure: {}, stressed_return: -0.03 },
				as_of: identity.as_of,
				source_snapshot_ids: identity.source_snapshot_ids,
				valuation_snapshot_id: identity.valuation_snapshot_id,
				constraint_findings: [],
				turnover: 0.05,
				...(key === "baseline_kind" ? {} : { [key]: value }),
			},
		};
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () => Response.json({ data: payload })),
		);
		await expect(
			previewPortfolioScenario({
				...identity,
				baseline_kind: "paper",
				excluded_instrument_ids: [],
				max_position_weight: "0.30",
				cash_reserve_weight: "0.10",
				market_shock: -0.05,
			}),
		).rejects.toThrow(message);
	});

	it("sends every exact identity field and repeats source snapshot query parameters", async () => {
		const payload = {
			strategy_id: identity.strategy_id,
			as_of: identity.as_of,
			source_snapshot_ids: identity.source_snapshot_ids,
			valuation_snapshot_id: identity.valuation_snapshot_id,
		} as Comparison;
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(JSON.stringify({ data: payload }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchPortfolioComparison(identity)).resolves.toEqual(payload);

		const request = capturedRequest(fetchMock.mock.calls);
		const requestUrl = new URL(request.url);
		expect(requestUrl.pathname).toBe("/api/v1/portfolio/comparison");
		expect(requestUrl.searchParams.get("model_portfolio_id")).toBe("model-main");
		expect(requestUrl.searchParams.get("paper_session_id")).toBe("paper-session-1");
		expect(requestUrl.searchParams.getAll("source_snapshot_ids")).toEqual(["snapshot:stock", "snapshot:fund"]);
		expect(request.method).toBe("GET");
	});

	it("fails closed before rendering when the response identity drifts", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							strategy_id: identity.strategy_id,
							as_of: "2026-09-01",
							source_snapshot_ids: identity.source_snapshot_ids,
							valuation_snapshot_id: identity.valuation_snapshot_id,
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchPortfolioComparison(identity)).rejects.toThrow("comparison as_of mismatch");
	});

	it("posts a preview-only scenario body without an apply target or write identifier", async () => {
		const payload = {
			baseline_kind: "paper",
			proposed_weights: {},
			applied_constraints: [],
			risk: {
				before: { cash_weight: 0.1, gross_exposure: 0.9, industry_exposure: {}, stressed_return: -0.04 },
				after: { cash_weight: 0.15, gross_exposure: 0.85, industry_exposure: {}, stressed_return: -0.03 },
				as_of: identity.as_of,
				constraint_findings: [],
				source_snapshot_ids: identity.source_snapshot_ids,
				turnover: 0.05,
				valuation_snapshot_id: "valuation:abc",
			},
		} as Scenario;
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(JSON.stringify({ data: payload }), {
					status: 200,
					headers: { "Content-Type": "application/json" },
				}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(
			previewPortfolioScenario({
				...identity,
				baseline_kind: "paper",
				excluded_instrument_ids: [600519],
				max_position_weight: "0.35",
				cash_reserve_weight: "0.10",
				market_shock: -0.08,
				industry_shocks: { consumer: -0.12 },
			}),
		).resolves.toEqual(payload);

		const request = capturedRequest(fetchMock.mock.calls);
		expect(requestPath(request)).toBe("/api/v1/portfolio/scenario-previews");
		expect(request.method).toBe("POST");
		const body = (await requestJson(request)) as Record<string, unknown>;
		expect(body).toMatchObject({
			baseline_kind: "paper",
			excluded_instrument_ids: [600519],
			max_position_weight: "0.35",
			cash_reserve_weight: "0.10",
			market_shock: -0.08,
		});
		expect(body).not.toHaveProperty("apply");
		expect(body).not.toHaveProperty("idempotency_key");
		expect(body).not.toHaveProperty("target_weights");
	});

	it("rejects a scenario result from another valuation snapshot", async () => {
		const fetchMock = vi.fn<typeof fetch>(
			async () =>
				new Response(
					JSON.stringify({
						data: {
							baseline_kind: "model",
							proposed_weights: {},
							applied_constraints: [],
							risk: {
								as_of: identity.as_of,
								valuation_snapshot_id: "valuation:other",
								source_snapshot_ids: identity.source_snapshot_ids,
							},
						},
					}),
					{ status: 200, headers: { "Content-Type": "application/json" } },
				),
		);
		vi.stubGlobal("fetch", fetchMock);

		await expect(
			previewPortfolioScenario({
				...identity,
				baseline_kind: "model",
				excluded_instrument_ids: [],
				max_position_weight: "0.30",
				cash_reserve_weight: "0.10",
				market_shock: -0.05,
			}),
		).rejects.toThrow("scenario valuation snapshot mismatch");
	});
});
