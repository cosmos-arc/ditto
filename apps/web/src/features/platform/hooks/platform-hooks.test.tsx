import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { platformHandlers } from "@/mocks/handlers/platform";
import { server } from "@/mocks/server";
import { usePlatformAlerts } from "./use-alerts";
import { usePipelines } from "./use-pipelines";
import { usePlatformHealth } from "./use-platform-health";
import { useProviders } from "./use-providers";

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
	server.use(...platformHandlers);
});

describe("usePlatformHealth", () => {
	it("返回平台健康数据", async () => {
		const { result } = renderHook(() => usePlatformHealth(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.freshness).toBe(98.5);
		expect(result.current.data?.completeness).toBe(99.2);
		expect(result.current.data?.accuracy).toBe(97.8);
	});
});

describe("useProviders", () => {
	it("返回数据提供者列表", async () => {
		const { result } = renderHook(() => useProviders(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.providers).toHaveLength(3);
		expect(result.current.data?.providers[0]?.name).toBe("tushare");
	});
});

describe("usePipelines", () => {
	it("返回管道列表", async () => {
		const { result } = renderHook(() => usePipelines(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.items).toHaveLength(3);
		expect(result.current.data?.total).toBe(3);
	});
});

describe("usePlatformAlerts", () => {
	it("返回告警列表", async () => {
		const { result } = renderHook(() => usePlatformAlerts(), {
			wrapper: createWrapper(),
		});

		await waitFor(() => expect(result.current.isSuccess).toBe(true));

		expect(result.current.data).toBeDefined();
		expect(result.current.data?.items.length).toBeGreaterThan(0);
	});
});
