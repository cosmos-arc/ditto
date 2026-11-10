import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { WatchlistPage } from "@/workflows/market-pages";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => localStorage.clear());

describe("WatchlistPage", () => {
	it("自选列表默认为空且明确仅保存在本机", async () => {
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("尚未添加标的")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/仅保存在当前浏览器/)).resolves.toBeInTheDocument();
	});

	it("按名称检索并加入自选，刷新（重挂载）后按精确身份重开", async () => {
		const user = userEvent.setup();
		const { unmount } = render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "茅台");
		await user.click(screen.getByRole("button", { name: "检索" }));
		const candidate = await screen.findByRole("button", { name: /加入自选 贵州茅台/ });
		await user.click(candidate);
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();

		// 重挂载模拟刷新重开：localStorage 持久化 + 每个对象按精确身份重新解析。
		unmount();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		expect(screen.getByText(/600519 · SSE/)).toBeInTheDocument();
	});

	it("按代码检索也能命中同一标的", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "300750");
		await user.click(screen.getByRole("button", { name: "检索" }));
		await expect(screen.findByRole("button", { name: /加入自选 宁德时代/ })).resolves.toBeInTheDocument();
	});

	it("无命中时明确提示，不产生假结果", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("搜索代码或名称"), "不存在的东西");
		await user.click(screen.getByRole("button", { name: "检索" }));
		await expect(screen.findByText(/没有匹配的标的/)).resolves.toBeInTheDocument();
	});

	it("未知对象不静默消失：目录未找到的 ID 明确展示并保留", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[9999999]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText(/目录中未找到/)).resolves.toBeInTheDocument();
		expect(screen.getByText(/9999999/)).toBeInTheDocument();
		await expect(screen.findByRole("button", { name: "移除 未知标的 9999999" })).resolves.toBeInTheDocument();
	});

	it("已退出对象保留展示并标注退出状态", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[1000005]");
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("退市示例")).resolves.toBeInTheDocument();
		expect(screen.getByText("已退出")).toBeInTheDocument();
	});

	it("解析失败的对象保留并可重试恢复", async () => {
		server.use(
			http.get("/api/v1/metadata/instruments/1000002", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
		);
		localStorage.setItem("ditto.market-watchlist.v1", "[1000002]");
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText(/解析失败/)).resolves.toBeInTheDocument();
		server.resetHandlers();
		await user.click(screen.getByRole("button", { name: "重试" }));
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
	});

	it("移除单个自选后清单更新", async () => {
		localStorage.setItem("ditto.market-watchlist.v1", "[1000001]");
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "移除 贵州茅台" }));
		await expect(screen.findByText("尚未添加标的")).resolves.toBeInTheDocument();
	});

	it("批量删除 overlay 明确只清空本机清单", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "批量删除" }));
		expect(screen.getByRole("dialog", { name: "批量删除自选" })).toHaveTextContent("localStorage");
	});
});
