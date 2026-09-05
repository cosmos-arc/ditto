import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api";
import { server } from "@/mocks/server";
import { strategyKeys } from "../api/query-keys";
import { useStrategyGovernance } from "./use-strategy-governance";

function createWrapper(qc: QueryClient) {
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

describe("useStrategyGovernance", () => {
	it("submitReview sends packet identity plus idempotency key and invalidates exact governed evidence scopes", async () => {
		let body: Record<string, unknown> = {};
		let idempotencyKey = "";
		server.use(
			http.post("/api/v1/strategies/:id/versions/:v/submit-review", async ({ request }) => {
				body = (await request.json()) as Record<string, unknown>;
				idempotencyKey = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({
					data: { strategy_id: "s", version: 1, state: "review", review_outcome: "pending" },
				});
			}),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
		const { result } = renderHook(() => useStrategyGovernance("seed_etf_industry_rotation"), {
			wrapper: createWrapper(qc),
		});

		await act(async () => {
			await result.current.submitReview.mutateAsync({
				version: 1,
				actor: "analyst",
				reason: "提交审查",
				bundleHash: "b".repeat(64),
				experimentId: "exp-1",
			});
		});

		await waitFor(() => expect(result.current.submitReview.isSuccess).toBe(true));
		expect(body).toEqual({ actor: "analyst", reason: "提交审查", bundle_hash: "b".repeat(64) });
		expect(idempotencyKey).toBeTruthy();
		expect(invalidateSpy).toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: strategyKeys.versions("seed_etf_industry_rotation") }),
		);
		expect(invalidateSpy).toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: strategyKeys.active("seed_etf_industry_rotation") }),
		);
		expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["research", "reviews", "list"] });
		expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["research", "reviews", "packet", "exp-1"] });
		expect(invalidateSpy).toHaveBeenCalledWith({
			queryKey: ["research", "experiments", "exp-1", "candidate-evidence"],
		});
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
					experimentId: "exp-3",
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

	it("does not recover the active pointer for a non-conflict transport failure", async () => {
		server.use(
			http.post("/api/v1/strategies/:id/versions/:v/reactivate", () =>
				HttpResponse.json({ detail: "temporarily unavailable", error_code: "UPSTREAM_UNAVAILABLE" }, { status: 503 }),
			),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
		const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
		const refetchSpy = vi.spyOn(qc, "refetchQueries");
		const { result } = renderHook(() => useStrategyGovernance("s"), { wrapper: createWrapper(qc) });

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
		expect(invalidateSpy).not.toHaveBeenCalled();
		expect(refetchSpy).not.toHaveBeenCalled();
	});

	it("keeps approve and publish as separate evidence-bound commands", async () => {
		const calls: Array<{ path: string; body: Record<string, unknown>; key: string }> = [];
		server.use(
			http.post(/\/api\/v1\/strategies\/s\/versions\/2\/(approve|publish)/, async ({ request }) => {
				calls.push({
					path: new URL(request.url).pathname,
					body: (await request.json()) as Record<string, unknown>,
					key: request.headers.get("Idempotency-Key") ?? "",
				});
				return HttpResponse.json({
					data: {
						strategy_id: "s",
						version: 2,
						state: "approved",
						review_outcome: "approved",
						active_version: 2,
						pointer_revision: 3,
					},
				});
			}),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const { result } = renderHook(() => useStrategyGovernance("s"), { wrapper: createWrapper(qc) });

		await act(async () => {
			await result.current.approve.mutateAsync({
				version: 2,
				actor: "reviewer",
				reason: "approve evidence",
				experimentId: "exp-2",
			});
			await result.current.publish.mutateAsync({
				version: 2,
				bundleHash: "c".repeat(64),
				actor: "publisher",
				reason: "promote approved version",
				experimentId: "exp-2",
			});
		});

		expect(calls).toHaveLength(2);
		expect(calls[0]).toMatchObject({
			path: "/api/v1/strategies/s/versions/2/approve",
			body: { actor: "reviewer", reason: "approve evidence" },
		});
		expect(calls[1]).toMatchObject({
			path: "/api/v1/strategies/s/versions/2/publish",
			body: { actor: "publisher", reason: "promote approved version", bundle_hash: "c".repeat(64) },
		});
		expect(calls.every((call) => call.key.length > 0)).toBe(true);
		expect(calls[0]?.key).not.toBe(calls[1]?.key);
	});

	it("invalidates strategy and review scopes without inventing experiment evidence when identity is absent", async () => {
		server.use(
			http.post("/api/v1/strategies/:id/versions/:v/reject", () =>
				HttpResponse.json({ data: { strategy_id: "s", version: 2, state: "draft", review_outcome: "rejected" } }),
			),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
		const { result } = renderHook(() => useStrategyGovernance("s"), { wrapper: createWrapper(qc) });

		await act(async () => {
			await result.current.reject.mutateAsync({ version: 2, actor: "reviewer", reason: "insufficient evidence" });
		});

		expect(invalidateSpy).toHaveBeenCalledTimes(4);
		expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["research", "reviews", "list"] });
		expect(invalidateSpy).not.toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: expect.arrayContaining(["experiments"]) }),
		);
	});

	it("still creates a bounded idempotency identity when randomUUID is unavailable", async () => {
		let key = "";
		server.use(
			http.post("/api/v1/strategies/:id/versions/:v/deprecate", ({ request }) => {
				key = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({
					data: { strategy_id: "s", version: 2, state: "deprecated", review_outcome: "approved" },
				});
			}),
		);
		vi.stubGlobal("crypto", {});
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const { result } = renderHook(() => useStrategyGovernance("s"), { wrapper: createWrapper(qc) });

		await act(async () => {
			await result.current.deprecate.mutateAsync({ version: 2, actor: "operator", reason: "superseded" });
		});

		expect(key).toMatch(/^strategy-governance-\d+-[a-z0-9]+$/u);
		vi.unstubAllGlobals();
	});
});
