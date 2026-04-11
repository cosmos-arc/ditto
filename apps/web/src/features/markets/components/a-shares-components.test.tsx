import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { marketsHandlers } from "@/mocks/handlers/markets";

import { ASharesOverview } from "./a-shares-overview";
import { ASharesPage } from "./a-shares-page";

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

describe("ASharesOverview", () => {
	it("渲染指数概览", async () => {
		render(<ASharesOverview />, { wrapper: createWrapper() });

		await expect(screen.findByText("上证指数")).resolves.toBeInTheDocument();
		await expect(screen.findByText("深证成指")).resolves.toBeInTheDocument();
	});

	it("显示板块涨幅", async () => {
		render(<ASharesOverview />, { wrapper: createWrapper() });

		await expect(screen.findByText("新能源")).resolves.toBeInTheDocument();
	});
});

describe("ASharesPage", () => {
	it("渲染 activity 面板", async () => {
		render(<ASharesPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("市场快照")).resolves.toBeInTheDocument();
	});

	it("渲染指数概览内容", async () => {
		render(<ASharesPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("上证指数")).resolves.toBeInTheDocument();
	});
});
