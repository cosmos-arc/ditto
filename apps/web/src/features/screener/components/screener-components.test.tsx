import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { useScreenerStore } from "../stores/screener.store";
import { ScreenerPage } from "./screener-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => {
	useScreenerStore.setState({ selectedIds: [] });
});

describe("ScreenerPage", () => {
	it("按公开 metadata 身份字段筛选", async () => {
		const user = userEvent.setup();
		render(<ScreenerPage />, { wrapper: wrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await user.type(screen.getByLabelText("搜索代码或名称"), "宁德");
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
		expect(screen.queryByText("贵州茅台")).not.toBeInTheDocument();
	});

	it("结果只显示 metadata 字段并支持身份对比", async () => {
		const user = userEvent.setup();
		render(<ScreenerPage />, { wrapper: wrapper() });
		await expect(screen.findByText("600519 · SSE")).resolves.toBeInTheDocument();
		expect(screen.queryByText(/PE /)).not.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "对比 贵州茅台" }));
		await expect(screen.findByText(/已选 1 个标的/)).resolves.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "打开对比" }));
		expect(screen.getByRole("dialog", { name: "身份对比" })).toHaveTextContent("已选择");
	});
});
