import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { dataProductOperationsKeys } from "../api/operations";
import { useRequestRemediationApproval } from "./use-data-product-operations";

function wrapper(queryClient: QueryClient) {
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("data product operation mutations", () => {
	it("invalidates only the remediation approval projection after a request", async () => {
		server.use(
			http.post("/api/v1/ingestion/catalog/remediation/approvals", () =>
				HttpResponse.json({
					data: {
						action: "repair_catalog_freshness",
						approval_id: "approval-001",
						authority_hash: "a".repeat(64),
						expires_at: "2099-08-18T09:00:00Z",
						intent_type: "write",
						item_id: "source_health:stock_daily:2026-08-18",
						method: "POST",
						path: "/v1/ingestion/stock_daily/2026-08-18",
						request_payload: { dataset_id: "stock_daily", trade_date: "2026-08-18" },
						requested_at: "2026-08-18T08:00:00Z",
						requested_by: "operator",
						status: "requested",
					},
				}),
			),
		);
		const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
		const approvalsKey = dataProductOperationsKeys.approvals("stock_daily");
		const unrelatedKey = dataProductOperationsKeys.sourceHealth("stock_daily", "2026-08-18");
		queryClient.setQueryData(approvalsKey, []);
		queryClient.setQueryData(unrelatedKey, { status: "ready" });
		const { result } = renderHook(() => useRequestRemediationApproval("stock_daily"), {
			wrapper: wrapper(queryClient),
		});

		await act(async () => {
			await result.current.mutateAsync({
				action: "repair_catalog_freshness",
				intentType: "write",
				itemId: "source_health:stock_daily:2026-08-18",
				method: "POST",
				path: "/v1/ingestion/stock_daily/2026-08-18",
				requestPayload: { dataset_id: "stock_daily", trade_date: "2026-08-18" },
				requestedBy: "operator",
			});
		});

		expect(queryClient.getQueryState(approvalsKey)?.isInvalidated).toBe(true);
		expect(queryClient.getQueryState(unrelatedKey)?.isInvalidated).toBe(false);
	});
});
