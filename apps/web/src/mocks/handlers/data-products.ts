import { HttpResponse, http, type RequestHandler } from "msw";

const DATASET_IDS = [
	"calendar",
	"stock_basic",
	"etf_basic",
	"index_basic",
	"stock_daily",
	"etf_daily",
	"index_daily",
	"global_index_daily",
	"adj_factor",
	"fund_adj",
	"stock_status",
	"index_weight",
	"corporate_actions",
	"balance_sheet",
	"income_statement",
	"cash_flow",
	"dividend",
	"valuation_metrics",
	"macro_indicators",
	"fx_daily",
	"commodity_daily",
] as const;

const MARKET_CONTEXT_DATASETS = new Set([
	"stock_daily",
	"index_daily",
	"global_index_daily",
	"index_weight",
	"macro_indicators",
	"fx_daily",
	"commodity_daily",
]);

const AUTHORITY_HASH = "a".repeat(64);
type MockRecord = Record<string, unknown>;

const remediationApprovals: MockRecord[] = [];
const fallbackPolicies: MockRecord[] = [];

function upsertBy(items: MockRecord[], key: string, value: string, item: MockRecord): void {
	const index = items.findIndex((candidate) => candidate[key] === value);
	if (index === -1) items.push(item);
	else items[index] = item;
}

function productRows() {
	return DATASET_IDS.map((datasetId, index) => ({
		active_certification_report_id:
			index === 0 || MARKET_CONTEXT_DATASETS.has(datasetId) ? `cert-${datasetId}-1` : null,
		certified_target_from: "2015-01-01",
		currency: datasetId === "fx_daily" ? "mixed" : "CNY",
		dataset_id: datasetId,
		frequency: datasetId.includes("daily") ? "daily" : "source_defined",
		maturity: index < 11 ? "initial-focus" : "experimental",
		owner: "data-platform",
		r2_scope: "hard",
		raw_target_from: "2005-01-01",
		schedule: datasetId.includes("daily") ? "trading_days" : "source_defined",
		schema_version: `${datasetId}.v1`,
		timezone: "Asia/Shanghai",
	}));
}

function datasetId(value: string | readonly string[] | undefined): string {
	return typeof value === "string" ? value : "calendar";
}

function tradeDate(request: Request): string {
	const query = new URL(request.url).searchParams;
	return query.get("trade_date") ?? query.getAll("trade_dates")[0] ?? "2026-08-30";
}

export const dataProductsHandlers: RequestHandler[] = [
	http.get("/api/v1/data-products", () => HttpResponse.json({ data: productRows() })),

	http.get("/api/v1/data-products/:datasetId/coverage", ({ params }) =>
		HttpResponse.json({
			data: {
				actual_partitions: 2499,
				certified_from: "2015-01-05",
				complete_from: "2015-01-05",
				dataset_id: datasetId(params["datasetId"]),
				expected_partitions: 2500,
				gaps: ["2026-07-15"],
				profile: "research_daily",
				raw_from: "2005-01-04",
				unapproved_gaps: ["2026-07-15"],
			},
		}),
	),

	http.get("/api/v1/data-products/:datasetId/quality", ({ params }) =>
		HttpResponse.json({
			data: {
				consumer_results: [{ evidence_uri: "evidence://consumer/r1", name: "R1 preflight", passed: true }],
				dataset_id: datasetId(params["datasetId"]),
				dq_results: [
					{ evidence_uri: "evidence://dq/completeness", name: "partition completeness", passed: true },
					{ evidence_uri: "evidence://dq/provider", name: "provider parity: tushare vs local_tdx", passed: false },
				],
				dq_rule_version: "dq-v3",
				freshness_results: [{ evidence_uri: "evidence://freshness/t1", name: "T+1 freshness", passed: true }],
				pit_replay_results: [{ evidence_uri: "evidence://pit/replay", name: "knowledge date replay", passed: true }],
				profile: "research_daily",
				recovery_results: [{ evidence_uri: "evidence://recovery/chunk", name: "chunk restore", passed: true }],
				report_id: "cert-calendar-1",
			},
		}),
	),

	http.get("/api/v1/data-products/:datasetId/runs", ({ params }) =>
		HttpResponse.json({
			data: [
				{
					content_hash: `sha256:${datasetId(params["datasetId"])}`,
					dataset_id: datasetId(params["datasetId"]),
					generated_at: "2026-08-30T07:10:00Z",
					profile: "research_daily",
					report_id: "cert-calendar-1",
					reviewed_at: "2026-08-30T07:15:00Z",
					reviewed_by: "operator",
					revocation_reason: null,
					status: "approved",
				},
			],
		}),
	),

	http.get("/api/v1/data-products/:datasetId/evidence", ({ params }) =>
		HttpResponse.json({
			data: {
				content_hash: `sha256:${datasetId(params["datasetId"])}`,
				dataset_id: datasetId(params["datasetId"]),
				fallback_history: ["tushare -> local_tdx (preview only)"],
				override_history: ["coverage exception rejected"],
				profile: "research_daily",
				report_id: "cert-calendar-1",
				schema_versions: [`${datasetId(params["datasetId"])}:v2`],
				snapshot_ids: [`snapshot-${datasetId(params["datasetId"])}-20260830`],
				source_ids: ["tushare", "local_tdx"],
			},
		}),
	),

	http.get("/api/v1/data-products/:datasetId/license", ({ params }) =>
		HttpResponse.json({
			data: {
				dataset_id: datasetId(params["datasetId"]),
				license_record_ids: ["license-tushare-reviewed-v1"],
				profile: "research_daily",
				report_id: "cert-calendar-1",
			},
		}),
	),

	http.get("/api/v1/ingestion/catalog/remediation/items/:itemId", ({ params, request }) => {
		const itemId = datasetId(params["itemId"]);
		const activeDatasetId = itemId.split(":")[1] ?? "calendar";
		const activeTradeDate = tradeDate(request);
		return HttpResponse.json({
			data: {
				approval_intents: [
					{
						action: "repair_catalog_freshness",
						intent_type: "write",
						method: "POST",
						path: `/api/v1/ingestion/${activeDatasetId}/${activeTradeDate}`,
						request_template: { dataset_id: activeDatasetId, trade_date: activeTradeDate },
						required_operator_inputs: [],
					},
				],
				evidence_requirements: [
					{
						description: "Refresh catalog freshness evidence before execution.",
						requirement_id: "freshness-evidence",
						source: "source_health",
						status: "missing",
					},
				],
				generated_at: "2026-08-30T07:05:00Z",
				item: {
					dataset_id: activeDatasetId,
					item_id: itemId,
					namespace: "market",
					reasons: ["PRIMARY_SOURCE_STALE"],
					severity: "high",
					source: "source_health",
					suggested_actions: ["repair_catalog_freshness"],
					trade_date: activeTradeDate,
				},
				summary: "Primary source freshness evidence requires operator review.",
			},
		});
	}),

	http.get("/api/v1/ingestion/catalog/remediation/approvals", () => HttpResponse.json({ data: remediationApprovals })),

	http.get("/api/v1/ingestion/catalog/source-health", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const activeDatasetId = query.get("dataset_id") ?? "calendar";
		const activeTradeDate = tradeDate(request);
		return HttpResponse.json({
			data: {
				dataset_id: activeDatasetId,
				default_source: "tushare",
				failover_from_default: true,
				fallback_sources: ["local_tdx"],
				namespace: "market",
				selected_freshness_status: "fresh",
				selected_source: "local_tdx",
				selected_source_health: {
					freshness_at: "2026-08-30T07:04:00Z",
					freshness_status: "fresh",
					source: "local_tdx",
					supported: true,
				},
				source_selection_blockers: [],
				source_selection_status: "ready",
				sources: [
					{ freshness_status: "stale", source: "tushare", supported: true },
					{ freshness_at: "2026-08-30T07:04:00Z", freshness_status: "fresh", source: "local_tdx", supported: true },
				],
				trade_date: activeTradeDate,
			},
		});
	}),

	http.get("/api/v1/ingestion/catalog/source-fallback/preview", ({ request }) => {
		const query = new URL(request.url).searchParams;
		const activeDatasetId = query.get("dataset_id") ?? "calendar";
		const activeTradeDate = tradeDate(request);
		return HttpResponse.json({
			data: {
				approval_required: true,
				dataset_id: activeDatasetId,
				default_source: "tushare",
				execution_allowed: true,
				fallback_sources: ["local_tdx"],
				namespace: "market",
				policy_status: "review_required",
				reason_codes: ["PRIMARY_SOURCE_STALE"],
				recommended_actions: ["review_fallback_source"],
				recommended_source: "local_tdx",
				selected_freshness_status: "fresh",
				selected_source: "local_tdx",
				source_selection_blockers: [],
				source_selection_status: "ready",
				trade_date: activeTradeDate,
			},
		});
	}),

	http.get("/api/v1/ingestion/catalog/source-fallback/policies", ({ request }) => {
		const activeDatasetId = new URL(request.url).searchParams.get("dataset_id");
		return HttpResponse.json({
			data: activeDatasetId
				? fallbackPolicies.filter((policy) => policy["dataset_id"] === activeDatasetId)
				: fallbackPolicies,
		});
	}),
	http.get("/api/v1/ingestion/catalog/promotion/history", () => HttpResponse.json({ data: [] })),

	http.post("/api/v1/ingestion/catalog/remediation/approvals", async ({ request }) => {
		const body = (await request.json()) as MockRecord;
		const approval = {
			...body,
			approval_id: "approval-mock-001",
			authority_hash: AUTHORITY_HASH,
			expires_at: "2099-08-30T08:00:00Z",
			requested_at: "2026-08-30T07:20:00Z",
			status: "requested",
		};
		upsertBy(remediationApprovals, "approval_id", "approval-mock-001", approval);
		return HttpResponse.json({
			data: approval,
		});
	}),

	http.post("/api/v1/ingestion/catalog/remediation/approvals/:approvalId/decision", async ({ params, request }) => {
		const approvalId = datasetId(params["approvalId"]);
		const approval = remediationApprovals.find((candidate) => candidate["approval_id"] === approvalId);
		if (!approval) return HttpResponse.json({ detail: "approval not found" }, { status: 404 });
		const body = (await request.json()) as MockRecord;
		if (body["authority_hash"] !== approval["authority_hash"])
			return HttpResponse.json({ detail: "authority hash mismatch" }, { status: 409 });
		const decided = {
			...approval,
			decided_at: "2026-08-30T07:25:00Z",
			decided_by: body["decided_by"],
			decision_notes: body["notes"] ?? null,
			status: body["decision"],
		};
		upsertBy(remediationApprovals, "approval_id", approvalId, decided);
		return HttpResponse.json({ data: decided });
	}),

	http.post("/api/v1/ingestion/catalog/remediation/approvals/:approvalId/execute", async ({ params, request }) => {
		const approvalId = datasetId(params["approvalId"]);
		const approval = remediationApprovals.find((candidate) => candidate["approval_id"] === approvalId);
		if (!approval) return HttpResponse.json({ detail: "approval not found" }, { status: 404 });
		const body = (await request.json()) as MockRecord;
		if (body["authority_hash"] !== approval["authority_hash"])
			return HttpResponse.json({ detail: "authority hash mismatch" }, { status: 409 });
		if (approval["status"] !== "approved")
			return HttpResponse.json({ detail: "approval is not executable" }, { status: 409 });
		const completed = { ...approval, status: "completed" };
		upsertBy(remediationApprovals, "approval_id", approvalId, completed);
		return HttpResponse.json({
			data: {
				approval: completed,
				execution: {
					action: approval["action"],
					approval_id: approvalId,
					executed_at: "2026-08-30T07:30:00Z",
					executed_by: body["executed_by"],
					notes: body["notes"] ?? null,
					result_payload: { fixture: true },
					status: "success",
				},
			},
		});
	}),

	http.post("/api/v1/ingestion/catalog/source-fallback/policies", async ({ request }) => {
		const body = (await request.json()) as MockRecord;
		const policyId = `fallback-${String(body["dataset_id"] ?? "calendar")}`;
		const policy = {
			...body,
			authority_hash: AUTHORITY_HASH,
			authority_payload: {
				action: "approval",
				dataset_id: body["dataset_id"],
				selected_source: body["selected_source"],
				trade_date: body["trade_date"],
			},
			created_at: "2026-08-30T07:20:00Z",
			policy_id: policyId,
			status: "draft",
		};
		upsertBy(fallbackPolicies, "policy_id", policyId, policy);
		return HttpResponse.json({ data: policy });
	}),

	http.post("/api/v1/ingestion/catalog/source-fallback/policies/:policyId/:action", async ({ params, request }) => {
		const policyId = datasetId(params["policyId"]);
		const action = datasetId(params["action"]);
		const policy = fallbackPolicies.find((candidate) => candidate["policy_id"] === policyId);
		if (!policy) return HttpResponse.json({ detail: "fallback policy not found" }, { status: 404 });
		const body = (await request.json()) as MockRecord;
		if (body["authority_hash"] !== policy["authority_hash"])
			return HttpResponse.json({ detail: "authority hash mismatch" }, { status: 409 });
		const status = action === "approval" ? "approved" : action === "activation" ? "active" : "retired";
		const nextAction = action === "approval" ? "activation" : "retirement";
		const transitioned = {
			...policy,
			authority_payload: { ...((policy["authority_payload"] as MockRecord) ?? {}), action: nextAction },
			decided_at: "2026-08-30T07:25:00Z",
			decided_by: body["actor"],
			decision_notes: body["notes"] ?? null,
			status,
		};
		upsertBy(fallbackPolicies, "policy_id", policyId, transitioned);
		return HttpResponse.json({ data: transitioned });
	}),

	http.post("/api/v1/ingestion/catalog/promotion/revoke", async ({ request }) => {
		const body = (await request.json()) as MockRecord;
		return HttpResponse.json({
			data: {
				dataset_id: body["dataset_id"],
				dataset_maturity_after: "experimental",
				dataset_maturity_before: "initial-focus",
				evidence_uri: "ditto://evidence/promotion/mock",
				notes: body["notes"] ?? null,
				revocation_reason: body["revocation_reason"],
				revoked_at: "2026-08-30T07:35:00Z",
				revoked_by: body["revoked_by"],
			},
		});
	}),
];
