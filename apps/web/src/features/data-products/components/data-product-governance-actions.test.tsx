import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import type {
	FallbackPolicyView,
	FallbackPreviewView,
	PromotionReadinessView,
	RemediationApprovalView,
	RemediationItemDetailView,
} from "../types/operations";
import { DataProductGovernanceActions } from "./data-product-governance-actions";

const AUTHORITY_HASH = "a".repeat(64);
const ACTION_PAYLOAD = { dataset_id: "stock_daily", trade_date: "2026-08-18", force: true };

function createWrapper(): ({ children }: { readonly children: ReactNode }) => ReactNode {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return function Wrapper({ children }: { readonly children: ReactNode }): ReactNode {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

function approval(overrides: Partial<RemediationApprovalView> = {}): RemediationApprovalView {
	return {
		action: "repair_catalog_freshness",
		approvalId: "approval-001",
		authorityHash: AUTHORITY_HASH,
		expiresAt: "2099-08-18T09:00:00Z",
		intentType: "write",
		itemId: "source_health:stock_daily:2026-08-18",
		method: "POST",
		path: "/api/v1/ingestion/stock_daily/2026-08-18",
		requestPayload: ACTION_PAYLOAD,
		requestedAt: "2026-08-18T08:00:00Z",
		requestedBy: "operator",
		status: "requested",
		...overrides,
	};
}

function fallbackPreview(): FallbackPreviewView {
	return {
		approvalRequired: true,
		blockers: [],
		datasetId: "stock_daily",
		defaultSource: "wind",
		executionAllowed: true,
		fallbackSources: ["tushare"],
		namespace: "market",
		policyStatus: "review_required",
		reasonCodes: ["PRIMARY_SOURCE_STALE"],
		recommendedActions: ["review_source_failover"],
		recommendedSource: "tushare",
		selectedSource: "tushare",
		sourceSelectionStatus: "ready",
		tradeDate: "2026-08-18",
	};
}

function fallbackPolicy(overrides: Partial<FallbackPolicyView> = {}): FallbackPolicyView {
	return {
		approvalRequired: true,
		authorityHash: AUTHORITY_HASH,
		authorityPayload: {
			action: "approval",
			dataset_id: "stock_daily",
			selected_source: "tushare",
			trade_date: "2026-08-18",
		},
		createdAt: "2026-08-18T08:00:00Z",
		createdBy: "operator",
		datasetId: "stock_daily",
		defaultSource: "wind",
		executionAllowed: true,
		namespace: "market",
		policyId: "fallback-001",
		reasonCodes: ["PRIMARY_SOURCE_STALE"],
		recommendedSource: "tushare",
		selectedSource: "tushare",
		status: "draft",
		tradeDate: "2026-08-18",
		...overrides,
	};
}

function remediationDetail(): RemediationItemDetailView {
	return {
		approvalIntents: [
			{
				action: "repair_catalog_freshness",
				intentType: "write",
				method: "POST",
				notes: null,
				path: "/api/v1/ingestion/stock_daily/2026-08-18",
				requestTemplate: ACTION_PAYLOAD,
				requiredOperatorInputs: [],
			},
		],
		evidenceRequirements: [],
		generatedAt: "2026-08-18T08:00:00Z",
		item: {
			datasetId: "stock_daily",
			fallbackSources: ["tushare"],
			itemId: "source_health:stock_daily:2026-08-18",
			namespace: "market",
			reasons: ["PRIMARY_SOURCE_STALE"],
			severity: "high",
			source: "source_health",
			suggestedActions: ["repair_catalog_freshness"],
			tradeDate: "2026-08-18",
		},
		summary: "Primary source is stale.",
	};
}

const NO_PROMOTION: PromotionReadinessView = {
	active: false,
	currentMaturity: "experimental",
	datasetId: "stock_daily",
	missingCriteria: [],
	rejectedCriteria: [],
	satisfiedCriteria: [],
	status: "blocked",
};

function renderActions({
	approvals = [],
	fallbackPolicies = [],
	promotion = NO_PROMOTION,
	remediation = remediationDetail(),
}: {
	readonly approvals?: readonly RemediationApprovalView[];
	readonly fallbackPolicies?: readonly FallbackPolicyView[];
	readonly promotion?: PromotionReadinessView;
	readonly remediation?: RemediationItemDetailView | undefined;
} = {}) {
	return render(
		<DataProductGovernanceActions
			approvals={approvals}
			datasetId="stock_daily"
			fallbackPolicies={fallbackPolicies}
			fallbackPreview={fallbackPreview()}
			promotion={promotion}
			remediationDetail={remediation}
			tradeDate="2026-08-18"
		/>,
		{ wrapper: createWrapper() },
	);
}

describe("DataProductGovernanceActions", () => {
	it("fails closed when the exact remediation authority has expired", async () => {
		const user = userEvent.setup();
		renderActions({ approvals: [approval({ expiresAt: "2000-01-01T00:00:00Z" })] });

		await user.click(screen.getByRole("button", { name: "检查 remediation approval" }));

		expect(screen.getByText(AUTHORITY_HASH)).toBeInTheDocument();
		expect(screen.getByRole("alert")).toHaveTextContent("approval expired");
		expect(screen.getByRole("button", { name: "拒绝" })).toBeDisabled();
		expect(screen.getByRole("button", { name: "批准精确动作" })).toBeDisabled();
	});

	it("submits the same remediation hash that the operator confirmed", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/remediation/approvals/:approvalId/decision", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: { ...rawApproval("approved") } });
			}),
		);
		renderActions({ approvals: [approval()] });

		await user.click(screen.getByRole("button", { name: "检查 remediation approval" }));
		await user.type(screen.getByLabelText("治理确认短语"), `remediation:approve:${AUTHORITY_HASH}`);
		await user.click(screen.getByRole("button", { name: "批准精确动作" }));

		expect(await screen.findByRole("status")).toHaveTextContent("approval approved");
		expect(requestBody).toEqual({ authority_hash: AUTHORITY_HASH, decided_by: "operator", decision: "approved" });
	});

	it("binds fallback approval to the server authority payload and hash", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/source-fallback/policies/:policyId/approval", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: rawFallbackPolicy("approved", "activation") });
			}),
		);
		renderActions({ fallbackPolicies: [fallbackPolicy()] });

		await user.click(screen.getByRole("button", { name: "检查 fallback approval" }));
		expect(screen.getByText("Exact fallback authority payload")).toBeInTheDocument();
		await user.type(screen.getByLabelText("治理确认短语"), `fallback:approval:${AUTHORITY_HASH}`);
		await user.click(screen.getByRole("button", { name: "确认 fallback approval" }));

		expect(await screen.findByRole("status")).toHaveTextContent("fallback approved");
		expect(requestBody).toEqual({ actor: "operator", authority_hash: AUTHORITY_HASH });
	});

	it("requires a typed second confirmation for promotion revoke", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/promotion/revoke", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: { dataset_id: "stock_daily", promotion_status: "blocked" } });
			}),
		);
		renderActions({ promotion: { ...NO_PROMOTION, active: true, status: "ready" } });

		await user.click(screen.getByRole("button", { name: "撤销晋级" }));
		const confirm = screen.getByRole("button", { name: "确认撤销晋级" });
		expect(confirm).toBeDisabled();
		await user.type(screen.getByLabelText("治理确认短语"), "promotion:revoke:stock_daily:2026-08-18:confirm");
		expect(confirm).toBeEnabled();
		await user.click(confirm);

		expect(await screen.findByRole("status")).toHaveTextContent("promotion revoked");
		expect(requestBody).toEqual({
			dataset_id: "stock_daily",
			revocation_reason: "failed_revalidation",
			revoked_by: "operator",
		});
	});

	it("requests approval without executing the remediation intent", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/remediation/approvals", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: rawApproval("requested") });
			}),
		);
		renderActions();

		await user.click(screen.getByRole("button", { name: "预览 remediation request" }));
		expect(screen.getByText("Exact request payload")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "请求审批" })).toBeDisabled();
		await user.type(screen.getByLabelText("治理确认短语"), "remediation:request:source_health:stock_daily:2026-08-18");
		await user.click(screen.getByRole("button", { name: "请求审批" }));

		expect(await screen.findByRole("status")).toHaveTextContent("approval requested · approval-001");
		expect(requestBody).toEqual({
			action: "repair_catalog_freshness",
			intent_type: "write",
			item_id: "source_health:stock_daily:2026-08-18",
			method: "POST",
			path: "/api/v1/ingestion/stock_daily/2026-08-18",
			request_payload: ACTION_PAYLOAD,
			requested_by: "operator",
		});
	});

	it("allows rejecting an exact valid approval without an execution confirmation phrase", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/remediation/approvals/:approvalId/decision", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: rawApproval("rejected") });
			}),
		);
		renderActions({ approvals: [approval()] });

		await user.click(screen.getByRole("button", { name: "检查 remediation approval" }));
		await user.click(screen.getByRole("button", { name: "拒绝" }));

		expect(await screen.findByRole("status")).toHaveTextContent("approval rejected");
		expect(requestBody).toEqual({
			authority_hash: AUTHORITY_HASH,
			decided_by: "operator",
			decision: "rejected",
		});
	});

	it("executes only the approved authority hash", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/remediation/approvals/:approvalId/execute", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({
					data: {
						approval: rawApproval("completed"),
						execution: { status: "success" },
					},
				});
			}),
		);
		renderActions({ approvals: [approval({ status: "approved" })] });

		await user.click(screen.getByRole("button", { name: "检查 remediation approval" }));
		await user.type(screen.getByLabelText("治理确认短语"), `remediation:execute:${AUTHORITY_HASH}`);
		await user.click(screen.getByRole("button", { name: "执行已批准动作" }));

		expect(await screen.findByRole("status")).toHaveTextContent("remediation success");
		expect(requestBody).toEqual({ authority_hash: AUTHORITY_HASH, executed_by: "operator" });
	});

	it("drafts the exact fallback preview selected by the operator", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/source-fallback/policies", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: { policy_id: "fallback-created" } });
			}),
		);
		renderActions();

		await user.click(screen.getByRole("button", { name: "预览 fallback draft" }));
		expect(screen.getByText("wind")).toBeInTheDocument();
		expect(screen.getByText("tushare")).toBeInTheDocument();
		await user.type(screen.getByLabelText("治理确认短语"), "fallback:draft:stock_daily:2026-08-18:tushare");
		await user.click(screen.getByRole("button", { name: "创建 fallback draft" }));

		expect(await screen.findByRole("status")).toHaveTextContent("fallback draft · fallback-created");
		expect(requestBody).toMatchObject({
			created_by: "operator",
			dataset_id: "stock_daily",
			default_source: "wind",
			selected_source: "tushare",
			trade_date: "2026-08-18",
		});
	});

	it.each([
		{ action: "activation", status: "approved", result: "active" },
		{ action: "retirement", status: "active", result: "retired" },
	] as const)("binds fallback $action to the current policy authority", async ({ action, status, result }) => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post(`/api/v1/ingestion/catalog/source-fallback/policies/:policyId/${action}`, async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: { status: result } });
			}),
		);
		renderActions({
			fallbackPolicies: [
				fallbackPolicy({
					authorityPayload: { action, dataset_id: "stock_daily" },
					status,
				}),
			],
		});

		await user.click(screen.getByRole("button", { name: `检查 fallback ${action}` }));
		await user.type(screen.getByLabelText("治理确认短语"), `fallback:${action}:${AUTHORITY_HASH}`);
		await user.click(screen.getByRole("button", { name: `确认 fallback ${action}` }));

		expect(await screen.findByRole("status")).toHaveTextContent(`fallback ${result}`);
		expect(requestBody).toEqual({ actor: "operator", authority_hash: AUTHORITY_HASH });
	});

	it("surfaces a mutation failure and preserves the operator's governed context", async () => {
		const user = userEvent.setup();
		server.use(
			http.post("/api/v1/ingestion/catalog/remediation/approvals", () =>
				HttpResponse.json({ detail: "authority service unavailable" }, { status: 503 }),
			),
		);
		renderActions();

		await user.click(screen.getByRole("button", { name: "预览 remediation request" }));
		await user.type(screen.getByLabelText("治理确认短语"), "remediation:request:source_health:stock_daily:2026-08-18");
		await user.click(screen.getByRole("button", { name: "请求审批" }));

		await waitFor(() => {
			expect(screen.getByRole("alert")).toHaveTextContent("authority service unavailable");
		});
		expect(screen.getByText("Exact request payload")).toBeInTheDocument();
	});

	it("uses the selected promotion revocation reason", async () => {
		const user = userEvent.setup();
		let requestBody: unknown;
		server.use(
			http.post("/api/v1/ingestion/catalog/promotion/revoke", async ({ request }) => {
				requestBody = await request.json();
				return HttpResponse.json({ data: { dataset_id: "stock_daily" } });
			}),
		);
		renderActions({ promotion: { ...NO_PROMOTION, active: true, currentMaturity: null, status: "ready" } });

		await user.click(screen.getByRole("button", { name: "撤销晋级" }));
		expect(screen.getByText("unknown")).toBeInTheDocument();
		await user.selectOptions(screen.getByLabelText("撤销原因"), "evidence_invalidated");
		await user.type(screen.getByLabelText("治理确认短语"), "promotion:revoke:stock_daily:2026-08-18:confirm");
		await user.click(screen.getByRole("button", { name: "确认撤销晋级" }));

		await waitFor(() => {
			expect(requestBody).toMatchObject({ revocation_reason: "evidence_invalidated" });
		});
	});
});

function rawApproval(status: string) {
	return {
		action: "repair_catalog_freshness",
		approval_id: "approval-001",
		authority_hash: AUTHORITY_HASH,
		expires_at: "2099-08-18T09:00:00Z",
		intent_type: "write",
		item_id: "source_health:stock_daily:2026-08-18",
		method: "POST",
		path: "/api/v1/ingestion/stock_daily/2026-08-18",
		request_payload: ACTION_PAYLOAD,
		requested_at: "2026-08-18T08:00:00Z",
		requested_by: "operator",
		status,
	};
}

function rawFallbackPolicy(status: string, action: string) {
	return {
		approval_required: true,
		authority_hash: AUTHORITY_HASH,
		authority_payload: { action, dataset_id: "stock_daily" },
		created_at: "2026-08-18T08:00:00Z",
		created_by: "operator",
		dataset_id: "stock_daily",
		default_source: "wind",
		execution_allowed: true,
		fallback_sources: ["tushare"],
		namespace: "market",
		policy_id: "fallback-001",
		reason_codes: ["PRIMARY_SOURCE_STALE"],
		recommended_actions: [],
		recommended_source: "tushare",
		selected_source: "tushare",
		source_selection_blockers: [],
		source_selection_status: "ready",
		status,
		trade_date: "2026-08-18",
		unsupported_sources: [],
	};
}
