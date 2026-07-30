import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api-client";
import { server } from "@/mocks/server";
import { strategyKeys } from "../api/query-keys";
import { useStrategyGovernance } from "./use-strategy-governance";

function createWrapper(qc: QueryClient) {
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

describe("useStrategyGovernance", () => {
	it("submitReview POSTs the decision and invalidates versions + active scopes", async () => {
		server.use(
			http.post("/api/v1/strategies/:id/versions/:v/submit-review", () =>
				HttpResponse.json({
					data: { strategy_id: "s", version: 1, state: "review", review_outcome: "pending" },
				}),
			),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
		const { result } = renderHook(() => useStrategyGovernance("seed_etf_industry_rotation"), {
			wrapper: createWrapper(qc),
		});

		await act(async () => {
			await result.current.submitReview.mutateAsync({ version: 1, actor: "analyst", reason: "提交审查" });
		});

		await waitFor(() => expect(result.current.submitReview.isSuccess).toBe(true));
		expect(invalidateSpy).toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: expect.arrayContaining(["strategy", "versions"]) }),
		);
		expect(invalidateSpy).toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: expect.arrayContaining(["strategy", "active"]) }),
		);
	});

	it("invalidates and refetches only the active pointer after a typed HTTP 409", async () => {
		server.use(
			http.post("/api/v1/strategies/:id/versions/:v/reactivate", () =>
				HttpResponse.json(
					{ detail: "active pointer changed", error_code: "POINTER_REVISION_CONFLICT" },
					{ status: 409 },
				),
			),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
		const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
		const refetchSpy = vi.spyOn(qc, "refetchQueries");
		const { result } = renderHook(() => useStrategyGovernance("s"), {
			wrapper: createWrapper(qc),
		});

		await act(async () => {
			await result.current.reactivate
				.mutateAsync({
					version: 3,
					actor: "analyst",
					reason: "切回",
					confirmation: "strategy:reactivate:s@3:pointer-revision:2:confirm",
					impactSummary: "恢复稳定策略",
					expectedPointerRevision: 2,
				})
				.catch(() => undefined);
		});

		await waitFor(() => expect(result.current.reactivate.error).toBeInstanceOf(ApiError));
		expect(invalidateSpy).toHaveBeenCalledWith({
			queryKey: strategyKeys.active("s"),
			refetchType: "none",
		});
		expect(refetchSpy).toHaveBeenCalledWith({ queryKey: strategyKeys.active("s") });
		expect(invalidateSpy).toHaveBeenCalledTimes(1);
		expect(refetchSpy).toHaveBeenCalledTimes(1);
	});
});
