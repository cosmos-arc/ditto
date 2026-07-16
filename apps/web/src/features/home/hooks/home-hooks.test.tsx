import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { homeHandlers } from "@/mocks/handlers/home";
import { server } from "@/mocks/server";
import { useDecisionBanner } from "./use-decision-banner";
import { useHomePulse } from "./use-home-pulse";
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
	server.use(...homeHandlers);
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
