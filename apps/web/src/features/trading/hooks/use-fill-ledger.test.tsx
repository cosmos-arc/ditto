import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { tradingKeys } from "../api/query-keys";
import { useFillLedger } from "./use-fill-ledger";

afterEach(() => {
	window.history.replaceState({}, "", "/trading");
});

describe("useFillLedger execution scope", () => {
	it("uses the URL strategy for both the request and query cache key", async () => {
		window.history.replaceState({}, "", "/trading/orders?strategy_id=strategy-r1");
		let requestedStrategy: string | null = null;
		server.use(
			http.get("/api/v1/trade/fills", ({ request }) => {
				requestedStrategy = new URL(request.url).searchParams.get("strategy_id");
				return HttpResponse.json({
					data: [],
					pagination: { total: 0, limit: 0, offset: 0, has_more: false },
				});
			}),
		);
		const queryClient = new QueryClient({
			defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
		});
		function Wrapper({ children }: { readonly children: ReactNode }) {
			return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
		}

		const { result } = renderHook(() => useFillLedger(), { wrapper: Wrapper });

		await waitFor(() => expect(result.current.isSuccess).toBe(true));
		expect(requestedStrategy).toBe("strategy-r1");
		expect(queryClient.getQueryState(tradingKeys.fills("strategy-r1"))).toBeDefined();
	});
});
