import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { ordersHandlers } from "@/mocks/handlers/orders";

import { OrdersList } from "./orders-list";

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

beforeEach(() => server.use(...ordersHandlers));

describe("OrdersList", () => {
	it("渲染订单列表标题", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findByText("订单台账")).resolves.toBeInTheDocument();
	});

	it("显示订单列表", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findByText("000001.SZ")).resolves.toBeInTheDocument();
		await expect(screen.findByText("600519.SH")).resolves.toBeInTheDocument();
	});

	it("显示订单方向", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findAllByText("BUY")).resolves.toHaveLength(4);
		await expect(screen.findByText("SELL")).resolves.toBeInTheDocument();
	});

	it("显示订单状态", async () => {
		render(<OrdersList />, { wrapper: createWrapper() });
		await expect(screen.findByText("pending")).resolves.toBeInTheDocument();
		await expect(screen.findAllByText("filled")).resolves.toHaveLength(2);
	});
});
