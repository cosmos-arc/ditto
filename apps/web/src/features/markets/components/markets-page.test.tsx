import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { MarketsPage } from "@/workflows/market-pages";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("MarketsPage public evidence boundary", () => {
	it("does not claim an unsupported viewpoint was saved", async () => {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: wrapper() });
		await user.click(await screen.findByRole("button", { name: "固定视角" }));
		expect(screen.getByText("固定视角暂不可用")).toBeInTheDocument();
		expect(screen.queryByText("视角已固定")).not.toBeInTheDocument();
	});

	it("separates failed context loading from connection state and can retry", async () => {
		server.use(http.get("/api/v1/market/context", () => HttpResponse.json({ detail: "unavailable" }, { status: 422 })));
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: wrapper() });
		await expect(screen.findByText("市场上下文加载失败")).resolves.toBeInTheDocument();
		expect(screen.queryByText("Loading")).not.toBeInTheDocument();
		server.resetHandlers();
		await user.click(screen.getByRole("button", { name: "重试市场上下文" }));
		await expect(screen.findByText("Ready")).resolves.toBeInTheDocument();
	});

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
		await expect(screen.findByText("5 个标的")).resolves.toBeInTheDocument();
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
