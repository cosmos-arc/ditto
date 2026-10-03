import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { CalendarPage } from "@/workflows/market-pages";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("CalendarPage", () => {
	it("展示 calendar 摄取状态而非虚构宏观事件", async () => {
		render(<CalendarPage />, { wrapper: wrapper() });
		await expect(screen.findByText("交易日历数据状态")).resolves.toBeInTheDocument();
		await expect(screen.findByText("最新摄取")).resolves.toBeInTheDocument();
		expect(await screen.findByText("2026-09-30")).toBeInTheDocument();
		expect(screen.getByText("成功")).toBeInTheDocument();
		expect(screen.queryByText(/CPI 同比/)).not.toBeInTheDocument();
	});

	it("展示记录数与 catalog 新鲜度", async () => {
		render(<CalendarPage />, { wrapper: wrapper() });
		await expect(screen.findByText("2,499")).resolves.toBeInTheDocument();
		expect(await screen.findByText("2026-10-01T08:00:00Z")).toBeInTheDocument();
	});

	it("摄取状态详情 overlay 不伪造宏观事件", async () => {
		const user = userEvent.setup();
		render(<CalendarPage />, { wrapper: wrapper() });
		await user.click(await screen.findByRole("button", { name: "状态详情" }));
		const dialog = screen.getByRole("dialog", { name: "日历状态详情" });
		expect(dialog).toHaveTextContent("事件明细");
		expect(dialog).toHaveTextContent("未公开");
	});
});
