import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { MarketsPage } from "@/workflows/market-pages";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("MarketsPage public evidence boundary", () => {
	it("live 模式也使用公开合同而非 prototype-only 空态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<MarketsPage />, { wrapper: wrapper() });

		await expect(screen.findByText("市场覆盖")).resolves.toBeInTheDocument();
		expect(screen.queryByText("prototype only")).not.toBeInTheDocument();
	});

	it("展示真实 metadata 聚合，不伪造指数价格或资金流", async () => {
		render(<MarketsPage />, { wrapper: wrapper() });

		expect((await screen.findAllByText("SSE")).length).toBeGreaterThan(0);
		expect((await screen.findAllByText("SZSE")).length).toBeGreaterThan(0);
		await expect(screen.findByText("4 个标的")).resolves.toBeInTheDocument();
		expect(screen.queryByText(/北向资金/)).not.toBeInTheDocument();
	});

	it("明确行情快照证据边界", async () => {
		render(<MarketsPage />, { wrapper: wrapper() });
		await expect(screen.findByText(/未加载价格、涨跌、资金流或相关性/)).resolves.toBeInTheDocument();
	});

	it("展示 MarketContext regime、跨市场宏观事实与影响链", async () => {
		render(<MarketsPage />, { wrapper: wrapper() });

		expect((await screen.findAllByText("Risk On")).length).toBeGreaterThan(0);
		expect(screen.getByText("Macro & Cross-Market")).toBeInTheDocument();
		expect(screen.getByText("global_return_1d")).toBeInTheDocument();
		expect(screen.getByText("cyclical")).toBeInTheDocument();
		expect(screen.getAllByText(/market-regime\.v1/).length).toBeGreaterThan(0);
	});

	it("市场操作打开真实边界 overlay", async () => {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: wrapper() });
		await user.click(await screen.findByRole("button", { name: "市场深度" }));
		expect(screen.getByRole("dialog", { name: "市场深度" })).toHaveTextContent("价格快照");
		expect(screen.getByRole("dialog", { name: "市场深度" })).toHaveTextContent("未查询");
	});
});
