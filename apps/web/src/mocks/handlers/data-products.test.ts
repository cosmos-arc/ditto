import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { dataProductsHandlers } from "./data-products";

const AUTHORITY_HASH = "a".repeat(64);

beforeEach(() => {
	server.use(...dataProductsHandlers);
});

describe("dataProductsHandlers", () => {
	it("supports the complete governed mutation lifecycle in the browser fixture", async () => {
		const requested = await fetch("/api/v1/ingestion/catalog/remediation/approvals", {
			body: JSON.stringify({
				action: "repair_catalog_freshness",
				intent_type: "write",
				item_id: "source_health:calendar:2026-08-30",
				method: "POST",
				path: "/v1/ingestion/calendar/2026-08-30",
				request_payload: { dataset_id: "calendar", trade_date: "2026-08-30" },
				requested_by: "operator",
			}),
			headers: { "content-type": "application/json" },
			method: "POST",
		});
		expect(requested.status).toBe(200);

		const approvals = await fetch("/api/v1/ingestion/catalog/remediation/approvals").then((response) =>
			response.json(),
		);
		expect(approvals.data).toHaveLength(1);

		const decided = await fetch("/api/v1/ingestion/catalog/remediation/approvals/approval-mock-001/decision", {
			body: JSON.stringify({ authority_hash: AUTHORITY_HASH, decided_by: "operator", decision: "approved" }),
			headers: { "content-type": "application/json" },
			method: "POST",
		}).then((response) => response.json());
		expect(decided.data.status).toBe("approved");

		const executed = await fetch("/api/v1/ingestion/catalog/remediation/approvals/approval-mock-001/execute", {
			body: JSON.stringify({ authority_hash: AUTHORITY_HASH, executed_by: "operator" }),
			headers: { "content-type": "application/json" },
			method: "POST",
		}).then((response) => response.json());
		expect(executed.data.approval.status).toBe("completed");
		expect(executed.data.execution.status).toBe("success");

		const drafted = await fetch("/api/v1/ingestion/catalog/source-fallback/policies", {
			body: JSON.stringify({
				approval_required: true,
				created_by: "operator",
				dataset_id: "calendar",
				default_source: "tushare",
				execution_allowed: true,
				fallback_sources: ["local_tdx"],
				namespace: "market",
				reason_codes: ["PRIMARY_SOURCE_STALE"],
				recommended_actions: ["review_fallback_source"],
				recommended_source: "local_tdx",
				selected_source: "local_tdx",
				source_selection_blockers: [],
				source_selection_status: "ready",
				trade_date: "2026-08-30",
				unsupported_sources: [],
			}),
			headers: { "content-type": "application/json" },
			method: "POST",
		}).then((response) => response.json());
		expect(drafted.data.status).toBe("draft");

		const approvedFallback = await fetch(
			`/api/v1/ingestion/catalog/source-fallback/policies/${drafted.data.policy_id}/approval`,
			{
				body: JSON.stringify({ actor: "operator", authority_hash: AUTHORITY_HASH }),
				headers: { "content-type": "application/json" },
				method: "POST",
			},
		).then((response) => response.json());
		expect(approvedFallback.data.status).toBe("approved");

		const revoked = await fetch("/api/v1/ingestion/catalog/promotion/revoke", {
			body: JSON.stringify({
				dataset_id: "calendar",
				revocation_reason: "failed_revalidation",
				revoked_by: "operator",
			}),
			headers: { "content-type": "application/json" },
			method: "POST",
		}).then((response) => response.json());
		expect(revoked.data.dataset_maturity_after).toBe("experimental");
	});
});
