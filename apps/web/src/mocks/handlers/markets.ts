import { HttpResponse, http, type RequestHandler } from "msw";

export const marketsHandlers: RequestHandler[] = [
	http.get("/api/v1/market/context", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const asOf = query.get("as_of") ?? "2026-08-31T09:00:00Z";
		return HttpResponse.json({
			data: {
				as_of: asOf,
				data_conflicts: [],
				drivers: [
					{ category: "a_share", contribution: 0.18, direction: "supportive", name: "breadth" },
					{ category: "risk", contribution: -0.08, direction: "pressuring", name: "volatility" },
				],
				evidence_refs: ["dataset://stock_daily/breadth@2026-08-31", "dataset://macro_indicators/surprise@2026-08-31"],
				feature_set_id: "market-regime:sha256:mock-context",
				feature_version: "market-regime.v1",
				impacts: [
					{ direction: "supportive", rationale_driver: "breadth", target: "cyclical", target_domain: "industry" },
					{ direction: "pressuring", rationale_driver: "volatility", target: "drawdown_guard", target_domain: "risk" },
				],
				knowledge_cutoff: asOf,
				metrics: [
					{
						category: "a_share",
						evidence_ref: "dataset://stock_daily/breadth@2026-08-31",
						freshness: "fresh",
						name: "advance_decline_breadth",
						trend: "rising",
						unit: "ratio",
						value: 0.42,
					},
					{
						category: "global",
						evidence_ref: "dataset://index_daily/global@2026-08-31",
						freshness: "fresh",
						name: "global_return_1d",
						trend: "falling",
						unit: "ratio",
						value: -0.006,
					},
					{
						category: "macro",
						evidence_ref: "dataset://macro_indicators/surprise@2026-08-31",
						freshness: "fresh",
						name: "macro_surprise_score",
						trend: "rising",
						unit: "score",
						value: 0.31,
					},
				],
				missing_inputs: [],
				publication_cutoff: asOf,
				regime_label: "risk_on",
				regime_score: 0.28,
				source_snapshot_ids: query.getAll("source_snapshot_id"),
				source_snapshot_set_id: "snapshot-set:sha256:mock-context",
				status: "ready",
				uncertainties: [],
			},
		});
	}),
];
