import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { CalendarPage } from "./calendar-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("CalendarPage", () => {
	it("展示 calendar 数据产品覆盖而非虚构宏观事件", async () => {
		render(<CalendarPage />, { wrapper: wrapper() });
		await expect(screen.findByText("交易日历覆盖")).resolves.toBeInTheDocument();
		expect((await screen.findAllByText("2015-01-05")).length).toBe(2);
		expect(screen.queryByText(/CPI 同比/)).not.toBeInTheDocument();
	});

	it("未批准缺口作为质量阻断显式呈现", async () => {
		render(<CalendarPage />, { wrapper: wrapper() });
		await expect(screen.findByText("2026-07-15")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/存在 1 个未批准缺口/)).resolves.toBeInTheDocument();
	});

	it("覆盖详情 overlay 不伪造宏观事件", async () => {
		const user = userEvent.setup();
		render(<CalendarPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "覆盖详情" }));
		expect(screen.getByRole("dialog", { name: "日历覆盖详情" })).toHaveTextContent("事件明细");
		expect(screen.getByRole("dialog", { name: "日历覆盖详情" })).toHaveTextContent("未公开");
	});
});
