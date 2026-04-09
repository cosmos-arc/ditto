import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { tradingHandlers } from "@/mocks/handlers/trading";

import { SignalsList } from "./signals-list";

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

beforeEach(() => server.use(...tradingHandlers));

describe("SignalsList", () => {
	it("渲染信号标题", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("信号队列")).resolves.toBeInTheDocument();
	});

	it("显示信号列表", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量突破")).resolves.toBeInTheDocument();
		await expect(screen.findByText("获利了结")).resolves.toBeInTheDocument();
		await expect(screen.findByText("均值回归")).resolves.toBeInTheDocument();
	});

	it("显示信号方向", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findAllByText("BUY")).resolves.toHaveLength(2);
		await expect(screen.getByText("SELL")).toBeInTheDocument();
	});

	it("显示置信度", async () => {
		render(<SignalsList />, { wrapper: createWrapper() });
		await expect(screen.findByText("85%")).resolves.toBeInTheDocument();
	});
});
