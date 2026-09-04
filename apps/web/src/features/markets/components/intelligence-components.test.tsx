import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { IntelligencePage } from "./intelligence-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("IntelligencePage", () => {
	it("experimental 宏观数据默认关闭", () => {
		render(<IntelligencePage />, { wrapper: wrapper() });
		expect(screen.getByText("实验数据未启用")).toBeInTheDocument();
		expect(screen.queryByText("PMI 制造业")).not.toBeInTheDocument();
	});

	it("经用户显式允许后按日期查询宏观指标", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("checkbox", { name: /允许 experimental/ }));
		await expect(screen.findByText("PMI 制造业")).resolves.toBeInTheDocument();
		expect((await screen.findAllByText("2026-07-31")).length).toBe(2);
		await expect(screen.findByText(/snapshot identity 未报告/)).resolves.toBeInTheDocument();
	});
});
