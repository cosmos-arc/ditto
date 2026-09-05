import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { systemHandlers } from "@/mocks/handlers/system";
import { server } from "@/mocks/server";
import { useSystemOverview } from "./use-system-overview";
import { useSystemSettings } from "./use-system-settings";

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...systemHandlers);
});

describe("useSystemOverview", () => {
	it("loads catalog identity before the exact-date governance projections", async () => {
		const { result } = renderHook(() => useSystemOverview("2026-08-30"), { wrapper: createWrapper() });

		await waitFor(() => expect(result.current.promotion.isSuccess).toBe(true));

		expect(result.current.datasetIds).toEqual(["etf_daily", "stock_daily"]);
		expect(result.current.remediation.data?.totalItems).toBe(2);
		expect(result.current.sourceHealth.data?.failoverCount).toBe(1);
		expect(result.current.fallback.data?.approvalRequiredCount).toBe(1);
		expect(result.current.promotion.data?.promotableCount).toBe(1);
	});
});

describe("useSystemSettings", () => {
	it("loads the three public read-only capability projections independently", async () => {
		const { result } = renderHook(() => useSystemSettings(), { wrapper: createWrapper() });

		await waitFor(() => expect(result.current.runtime.isSuccess).toBe(true));
		await waitFor(() => expect(result.current.assets.isSuccess).toBe(true));
		await waitFor(() => expect(result.current.agent.isSuccess).toBe(true));

		expect(result.current.runtime.data).toMatchObject({ environment: "mock-local", status: "running" });
		expect(result.current.assets.data).toHaveLength(2);
		expect(result.current.agent.data).toMatchObject({ provider: "fixture-provider", runtimeState: "available" });
	});
});
