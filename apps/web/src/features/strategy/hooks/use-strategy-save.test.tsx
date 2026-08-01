import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockStrategyDetailDto } from "@/mocks/fixtures/strategy-live";
import { server } from "@/mocks/server";
import type { StrategySpec } from "@/types/strategy";
import { useStrategyStudioStore } from "../state/strategy-studio-store";
import { useStrategySave } from "./use-strategy-save";

const SAMPLE_SPEC: StrategySpec = {
	strategyId: "seed_etf_industry_rotation",
	name: "ETF 行业轮动",
	template: "etf_rotation",
	universe: "csi_etf_broad",
	assetClass: "etf",
	benchmark: "000300.SH",
	scorer: { method: "rank_then_combine", params: {} },
	selector: { method: "top_k", params: { k: 5 } },
	execution: { frequency: "M", method: "calendar", defaultOrderType: "market" },
	constraints: [],
	params: {},
	signalExpressions: [],
	signalWeights: [],
	paramConstraints: [],
};

function createWrapper(qc: QueryClient) {
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	useStrategyStudioStore.setState({ workingSpec: SAMPLE_SPEC, savedSpec: SAMPLE_SPEC, selectedNodeKey: null });
});

describe("useStrategySave", () => {
	it("PUTs serialized spec, reloads the returned spec into the store, and invalidates strategy scopes", async () => {
		let idempotencyKey = "";
		server.use(
			http.put("/api/v1/strategies/:id", ({ request }) => {
				idempotencyKey = request.headers.get("Idempotency-Key") ?? "";
				return HttpResponse.json({ data: { ...mockStrategyDetailDto, version: 4 } });
			}),
		);
		const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
		const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

		const { result } = renderHook(() => useStrategySave(), { wrapper: createWrapper(qc) });

		await act(async () => {
			await result.current.mutateAsync({
				strategyId: "seed_etf_industry_rotation",
				version: 3,
				spec: SAMPLE_SPEC,
				name: "ETF 行业轮动",
				tags: ["etf", "rotation"],
				idempotencyKey: "save-command-1",
			});
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));
		expect(useStrategyStudioStore.getState().savedSpec?.strategyId).toBe("seed_etf_industry_rotation");
		expect(idempotencyKey).toBe("save-command-1");
		expect(invalidateSpy).toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: expect.arrayContaining(["strategy", "versions"]) }),
		);
		expect(invalidateSpy).toHaveBeenCalledWith(
			expect.objectContaining({ queryKey: expect.arrayContaining(["strategy", "detail"]) }),
		);
	});
});
