import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { capturedRequest, requestJson, requestPath } from "@/test/request";
import {
	decideRemediationApproval,
	draftFallbackPolicy,
	executeRemediationApproval,
	fetchFallbackPolicies,
	fetchFallbackPreview,
	fetchFallbackSummary,
	fetchPromotionHistory,
	fetchPromotionReadiness,
	fetchRemediationApprovals,
	fetchRemediationBacklog,
	fetchRemediationDetail,
	fetchSourceHealth,
	fetchSourceHealthSummary,
	requestRemediationApproval,
	revokePromotion,
	transitionFallbackPolicy,
} from "./operations";

afterEach(() => vi.unstubAllGlobals());

describe("data product operations API adapters", () => {
	it("encodes list query parameters as repeated values instead of JSON", async () => {
		let requestedUrl = "";
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/backlog", ({ request }) => {
				requestedUrl = request.url;
				return HttpResponse.json({
					data: {
						generated_at: "2026-08-18T08:00:00Z",
						dataset_ids: ["stock_daily"],
						trade_dates: ["2026-08-18"],
						available_sources: ["wind", "tushare"],
						total_items: 0,
						severity_counts: [],
						items: [],
					},
				});
			}),
		);

		await fetchRemediationBacklog({
			datasetId: "stock_daily",
			tradeDate: "2026-08-18",
			availableSources: ["wind", "tushare"],
		});

		const params = new URL(requestedUrl).searchParams;
		expect(params.getAll("dataset_ids")).toEqual(["stock_daily"]);
		expect(params.getAll("trade_dates")).toEqual(["2026-08-18"]);
		expect(params.getAll("available_sources")).toEqual(["wind", "tushare"]);
	});

	it("maps remediation detail into an exact intent and evidence view model", async () => {
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/items/:itemId", ({ params }) =>
				HttpResponse.json({
					data: {
						generated_at: "2026-08-18T08:00:00Z",
						item: {
							item_id: params["itemId"],
							source: "source_health",
							dataset_id: "stock_daily",
							namespace: "market",
							severity: "high",
							trade_date: "2026-08-18",
							reasons: ["PRIMARY_SOURCE_STALE"],
							suggested_actions: ["repair_catalog_freshness"],
						},
						summary: "Primary source is stale.",
						evidence_requirements: [
							{
								requirement_id: "freshness-evidence",
								source: "source_health",
								status: "missing",
								description: "Refresh source evidence.",
							},
						],
						approval_intents: [
							{
								action: "repair_catalog_freshness",
								intent_type: "write",
								method: "POST",
								path: "/api/v1/ingestion/stock_daily/2026-08-18",
								request_template: {
									dataset_id: "stock_daily",
									trade_date: "2026-08-18",
									force: true,
								},
								required_operator_inputs: [],
							},
						],
					},
				}),
			),
		);

		const result = await fetchRemediationDetail("source_health:stock_daily:2026-08-18", {
			datasetId: "stock_daily",
			tradeDate: "2026-08-18",
		});

		expect(result.item.itemId).toBe("source_health:stock_daily:2026-08-18");
		expect(result.approvalIntents[0]).toMatchObject({
			action: "repair_catalog_freshness",
			requestTemplate: { dataset_id: "stock_daily", trade_date: "2026-08-18", force: true },
		});
		expect(result.evidenceRequirements[0]?.status).toBe("missing");
	});

	it("fails closed when optional remediation, source, fallback, and promotion evidence is absent", async () => {
		let readinessCalls = 0;
		const remediationItem = {
			dataset_id: "stock_daily",
			item_id: "source_health:stock_daily:2026-08-18",
			namespace: "market",
			severity: "high",
			source: "source_health",
		};
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const path = requestPath(capturedRequest([[input, init]])).split("?")[0];
			switch (path) {
				case "/api/v1/ingestion/catalog/remediation/backlog":
					return Response.json({
						data: { generated_at: "2026-08-18T08:00:00Z", total_items: 1, items: [remediationItem] },
					});
				case "/api/v1/ingestion/catalog/remediation/items/source_health%3Astock_daily%3A2026-08-18":
					return Response.json({
						data: {
							generated_at: "2026-08-18T08:00:00Z",
							item: remediationItem,
							summary: "Evidence has not been published.",
						},
					});
				case "/api/v1/ingestion/catalog/source-health":
					return Response.json({
						data: {
							dataset_id: "stock_daily",
							default_source: "wind",
							selected_freshness_status: "stale",
							selected_source: "tushare",
							source_selection_status: "attention_required",
							sources: [{ freshness_status: "unknown", source: "tushare", supported: true }],
							trade_date: "2026-08-18",
						},
					});
				case "/api/v1/ingestion/catalog/source-health/summary":
					return Response.json({
						data: {
							attention_required: [],
							failover_count: 1,
							no_fallback_source_count: 0,
							revoked_promotion_count: 0,
							total_reports: 1,
						},
					});
				case "/api/v1/ingestion/catalog/source-fallback/preview":
					return Response.json({
						data: {
							approval_required: true,
							dataset_id: "stock_daily",
							default_source: "wind",
							execution_allowed: false,
							namespace: "market",
							policy_status: "draft",
							selected_source: "tushare",
							source_selection_status: "attention_required",
							trade_date: "2026-08-18",
						},
					});
				case "/api/v1/ingestion/catalog/source-fallback/policies":
					return Response.json({
						data: [
							{
								approval_required: true,
								authority_hash: "a".repeat(64),
								authority_payload: {},
								created_at: "2026-08-18T08:00:00Z",
								created_by: "operator",
								dataset_id: "stock_daily",
								default_source: "wind",
								execution_allowed: false,
								namespace: "market",
								policy_id: "policy-1",
								selected_source: "tushare",
								status: "draft",
								trade_date: "2026-08-18",
							},
						],
					});
				case "/api/v1/ingestion/catalog/source-fallback/summary":
					return Response.json({
						data: {
							approval_required_count: 1,
							execution_allowed_count: 0,
							policy_status_counts: [{ count: 1, status: "draft" }],
							total_previews: 1,
						},
					});
				case "/api/v1/ingestion/catalog/promotion/readiness":
					readinessCalls += 1;
					return Response.json({
						data: {
							datasets:
								readinessCalls === 1
									? []
									: [
											{
												active_maturity_promotion: false,
												dataset_id: "stock_daily",
												promotion_status: "blocked",
											},
										],
						},
					});
				case "/api/v1/ingestion/catalog/promotion/history":
					return Response.json({
						data: [
							{
								action: "revoke",
								actor: "operator",
								next_maturity: "beta",
								previous_maturity: "production",
							},
						],
					});
				case "/api/v1/ingestion/catalog/remediation/approvals":
					return Response.json({
						data: [
							{
								action: "repair",
								approval_id: "approval-1",
								authority_hash: "b".repeat(64),
								expires_at: "2026-08-19T08:00:00Z",
								intent_type: "write",
								item_id: "source_health:stock_daily:2026-08-18",
								requested_at: "2026-08-18T08:00:00Z",
								requested_by: "operator",
								status: "pending",
							},
						],
					});
				default:
					throw new Error(`Unhandled test request: ${path}`);
			}
		});
		vi.stubGlobal("fetch", fetchMock);

		const scope = { datasetId: "stock_daily", tradeDate: "2026-08-18" } as const;
		await expect(fetchRemediationBacklog(scope)).resolves.toMatchObject({
			items: [{ fallbackSources: [], reasons: [], suggestedActions: [], tradeDate: null }],
		});
		await expect(fetchRemediationDetail(remediationItem.item_id, scope)).resolves.toMatchObject({
			approvalIntents: [],
			evidenceRequirements: [],
		});
		await expect(fetchSourceHealth(scope)).resolves.toMatchObject({
			blockers: [],
			failoverFromDefault: true,
			fallbackSources: [],
			sources: [{ freshnessAt: null }],
		});
		await expect(fetchSourceHealth({ ...scope, availableSources: ["tushare"] })).resolves.toMatchObject({
			selectedSource: "tushare",
		});
		await expect(fetchSourceHealthSummary(scope)).resolves.toMatchObject({ attentionReasons: [] });
		await expect(fetchFallbackPreview(scope)).resolves.toMatchObject({
			blockers: [],
			fallbackSources: [],
			reasonCodes: [],
			recommendedActions: [],
			recommendedSource: null,
		});
		await expect(fetchFallbackPolicies(scope.datasetId)).resolves.toMatchObject([
			{ reasonCodes: [], recommendedSource: null },
		]);
		await expect(fetchFallbackSummary(scope)).resolves.toMatchObject({ recommendedActions: [] });
		await expect(fetchPromotionReadiness(scope)).resolves.toBeNull();
		await expect(fetchPromotionReadiness(scope)).resolves.toMatchObject({
			currentMaturity: null,
			missingCriteria: [],
			rejectedCriteria: [],
			satisfiedCriteria: [],
		});
		await expect(fetchPromotionHistory(scope.datasetId)).resolves.toMatchObject([
			{ actionAt: null, evidenceUri: null, notes: null, revocationReason: null },
		]);
		await expect(fetchRemediationApprovals(scope.datasetId)).resolves.toMatchObject([
			{ method: null, path: null, requestPayload: {} },
		]);
	});

	it("preserves explicit operator evidence across every remediation and fallback lifecycle command", async () => {
		const requests: Request[] = [];
		const approval = {
			action: "repair_catalog_freshness",
			approval_id: "approval-1",
			authority_hash: "a".repeat(64),
			expires_at: "2026-08-19T08:00:00Z",
			intent_type: "write",
			item_id: "source_health:stock_daily:2026-08-18",
			method: "POST",
			path: "/api/v1/ingestion/stock_daily/2026-08-18",
			request_payload: { force: true },
			requested_at: "2026-08-18T08:00:00Z",
			requested_by: "operator",
			status: "pending",
		};
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const request = capturedRequest([[input, init]]);
			requests.push(request);
			const path = requestPath(request).split("?")[0] ?? "";
			if (path.endsWith("/execute")) return Response.json({ data: { approval_id: "approval-1", status: "executed" } });
			if (path.includes("source-fallback/policies")) return Response.json({ data: { policy_id: "policy-1" } });
			if (path.endsWith("/promotion/revoke")) return Response.json({ data: { dataset_id: "stock_daily" } });
			return Response.json({ data: approval });
		});
		vi.stubGlobal("fetch", fetchMock);

		await requestRemediationApproval({
			action: "repair_catalog_freshness",
			intentType: "write",
			itemId: approval.item_id,
			method: "POST",
			notes: "operator reviewed source evidence",
			path: approval.path,
			requestPayload: { force: true },
			requestedBy: "operator",
		});
		await decideRemediationApproval({
			approvalId: "approval-1",
			authorityHash: approval.authority_hash,
			decidedBy: "reviewer",
			decision: "approved",
			notes: "evidence accepted",
		});
		await executeRemediationApproval({
			approvalId: "approval-1",
			authorityHash: approval.authority_hash,
			executedBy: "operator",
			notes: "execute exact authority",
		});
		await draftFallbackPolicy(
			{
				approvalRequired: true,
				blockers: ["PRIMARY_STALE"],
				datasetId: "stock_daily",
				defaultSource: "wind",
				executionAllowed: false,
				fallbackSources: ["tushare"],
				namespace: "market",
				policyStatus: "draft",
				reasonCodes: ["PRIMARY_STALE"],
				recommendedActions: ["switch_source"],
				recommendedSource: "tushare",
				selectedSource: "tushare",
				sourceSelectionStatus: "attention_required",
				tradeDate: "2026-08-18",
			},
			"operator",
		);
		for (const action of ["approval", "activation", "retirement"] as const) {
			await transitionFallbackPolicy({
				action,
				actor: "operator",
				authorityHash: approval.authority_hash,
				datasetId: "stock_daily",
				notes: `${action} evidence`,
				policyId: "policy-1",
			});
		}
		await revokePromotion({
			datasetId: "stock_daily",
			notes: "freshness regression",
			reason: "policy_regression",
			revokedBy: "operator",
		});

		expect(requests.map((request) => requestPath(request).split("?")[0])).toEqual([
			"/api/v1/ingestion/catalog/remediation/approvals",
			"/api/v1/ingestion/catalog/remediation/approvals/approval-1/decision",
			"/api/v1/ingestion/catalog/remediation/approvals/approval-1/execute",
			"/api/v1/ingestion/catalog/source-fallback/policies",
			"/api/v1/ingestion/catalog/source-fallback/policies/policy-1/approval",
			"/api/v1/ingestion/catalog/source-fallback/policies/policy-1/activation",
			"/api/v1/ingestion/catalog/source-fallback/policies/policy-1/retirement",
			"/api/v1/ingestion/catalog/promotion/revoke",
		]);
		await expect(requestJson(requests[0] as Request)).resolves.toMatchObject({
			method: "POST",
			notes: "operator reviewed source evidence",
			path: approval.path,
			request_payload: { force: true },
		});
		await expect(requestJson(requests[4] as Request)).resolves.toMatchObject({ notes: "approval evidence" });
	});
});
