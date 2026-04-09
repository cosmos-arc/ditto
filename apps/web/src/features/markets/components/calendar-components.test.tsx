import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { marketsHandlers } from "@/mocks/handlers/markets";

import { MarketCalendarList } from "./market-calendar-list";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...marketsHandlers));

describe("MarketCalendarList", () => {
	it("渲染日历标题", async () => {
		render(<MarketCalendarList />, { wrapper: createWrapper() });

		await expect(screen.findByText("市场日历")).resolves.toBeInTheDocument();
	});

	it("显示日历事件", async () => {
		render(<MarketCalendarList />, { wrapper: createWrapper() });

		const elements = await screen.findAllByText(/CPI 同比/);
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});
});
