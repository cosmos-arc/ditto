import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
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

	it("可按内部 ID 添加并移除真实 metadata 标的", async () => {
		const user = userEvent.setup();
		render(<WatchlistPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "添加标的" }));
		await user.type(screen.getByLabelText("标的内部 ID"), "1000001");
		await user.click(screen.getByRole("button", { name: "确认添加" }));
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
