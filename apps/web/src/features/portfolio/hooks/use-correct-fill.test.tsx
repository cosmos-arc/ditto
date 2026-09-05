import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { tradingKeys } from "../api/query-keys";
import { useCorrectFill } from "./use-correct-fill";

function createWrapper(queryClient: QueryClient) {
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("useCorrectFill", () => {
	it("invalidates every dependent trading truth after an append-only correction", async () => {
		server.use(
			http.post("/api/v1/manual/fills/:fillId/void", async ({ params, request }) => {
				const payload = await request.json();
				return HttpResponse.json({
					data: {
						...(payload as Record<string, unknown>),
						fill_id: params["fillId"],
						adjustment_type: "void",
						replacement_fill_id: null,
						created_at: "2026-07-16T10:00:00+08:00",
					},
				});
			}),
		);
		const queryClient = new QueryClient({
			defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
		});
		const invalidateQueries = vi.spyOn(queryClient, "invalidateQueries");
		const { result } = renderHook(() => useCorrectFill(), { wrapper: createWrapper(queryClient) });

		await act(async () => {
			await result.current.mutateAsync({
				kind: "void",
				fillId: "fill-001",
				payload: { adjustment_id: "adjustment-void-001", reason: "重复录入" },
			});
		});

		expect(invalidateQueries.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(
			["daily-decision", "positions", "deviation", "pnl", "fills"].map((scope) => [...tradingKeys.all, scope]),
		);
	});
});
