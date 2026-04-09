import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { marketsHandlers } from "@/mocks/handlers/markets";

import { ScreenerToolbar } from "./screener-toolbar";
import { ScreenerResults } from "./screener-results";
import { CompareCart } from "./compare-cart";

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

describe("ScreenerToolbar", () => {
	it("渲染预设标签", async () => {
		render(<ScreenerToolbar />, { wrapper: createWrapper() });
		await expect(screen.findByText("高股息")).resolves.toBeInTheDocument();
		await expect(screen.findByText("低估值")).resolves.toBeInTheDocument();
		await expect(screen.findByText("高成长")).resolves.toBeInTheDocument();
	});

	it("显示筛选标题", async () => {
		render(<ScreenerToolbar />, { wrapper: createWrapper() });
		await expect(screen.findByText("筛选条件")).resolves.toBeInTheDocument();
	});
});

describe("ScreenerResults", () => {
	it("渲染结果标题", async () => {
		render(<ScreenerResults />, { wrapper: createWrapper() });
		await expect(screen.findByText("筛选结果")).resolves.toBeInTheDocument();
	});

	it("显示标的结果列表", async () => {
		render(<ScreenerResults />, { wrapper: createWrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
		await expect(screen.findByText("比亚迪")).resolves.toBeInTheDocument();
	});
});

describe("CompareCart", () => {
	it("无选中时不渲染", () => {
		const { container } = render(<CompareCart />, { wrapper: createWrapper() });
		expect(container.innerHTML).toBe("");
	});
});
