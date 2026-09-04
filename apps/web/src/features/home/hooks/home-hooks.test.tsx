import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { homeHandlers } from "@/mocks/handlers/home";
import { portfolioHandlers } from "@/mocks/handlers/portfolio";
import { server } from "@/mocks/server";
import { useDecisionBanner } from "./use-decision-banner";
import { useHomePulse } from "./use-home-pulse";
import { useMarketPulseMetrics } from "./use-market-pulse-metrics";
import { usePendingActions } from "./use-pending-actions";
import { useRecentSignals } from "./use-recent-signals";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper(queryClient?: QueryClient) {
	const client = queryClient ?? createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => {
	server.use(...homeHandlers, ...portfolioHandlers);
});

describe("useHomePulse", () => {
	it("返回 Home 脉动数据", async () => {
		const { result } = renderHook(() => useHomePulse(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.session).toBe("continuous");
		expect(result.current.data?.pendingActions).toBe(2);
	});
});

describe("useDecisionBanner", () => {
	it("返回决策横幅数据", async () => {
		const { result } = renderHook(() => useDecisionBanner(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.marketRegime).toBe("mixed");
		expect(result.current.data?.totalEquity).toBe(25432180);
		expect(result.current.data?.suggestion.length).toBeGreaterThan(0);
	});
});

describe("usePendingActions", () => {
	it("返回待处理事项列表", async () => {
		const { result } = renderHook(() => usePendingActions(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.actions).toHaveLength(5);
		expect(result.current.data?.actions[0]?.priority).toBe("critical");
	});
});

describe("useRecentSignals", () => {
	it("返回近期信号列表（空）", async () => {
		const { result } = renderHook(() => useRecentSignals(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.signals).toHaveLength(0);
	});
});

describe("Home live projection hooks", () => {
	it("shares Daily Decision V3 while sourcing the market brief from exact MarketContext evidence", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const wrapper = createWrapper();
		const decision = renderHook(() => useDecisionBanner(), { wrapper });
		const pulse = renderHook(() => useHomePulse(), { wrapper });
		const market = renderHook(() => useMarketPulseMetrics(), { wrapper });

		await waitFor(() => expect(decision.result.current.isSuccess).toBe(true));
		await waitFor(() => expect(pulse.result.current.isSuccess).toBe(true));
		await waitFor(() => expect(market.result.current.isSuccess).toBe(true));

		expect(decision.result.current.data).toMatchObject({ dailyPnl: 197, ivix: null, northboundFlow: null });
		expect(pulse.result.current.data).toMatchObject({ pendingActions: 1, runningJobs: null });
		expect(market.result.current.data).toMatchObject({
			brief: {
				status: "ready",
				statusLabel: "可用",
				regimeLabel: "风险偏好",
				evidenceRefs: ["dataset://stock_daily/breadth@2026-08-31", "dataset://macro_indicators/surprise@2026-08-31"],
			},
			metrics: [
				{ label: "市场环境", value: "风险偏好", change: "可用 · 得分 +0.28" },
				{ label: "市场宽度", value: "42.0%", change: "上行" },
				{ label: "全球市场 1日", value: "-0.60%", change: "下行" },
				{ label: "宏观意外", value: "+0.31", change: "上行" },
			],
		});
	});
});
