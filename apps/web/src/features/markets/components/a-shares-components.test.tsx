import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { ASharesPage } from "./a-shares-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

describe("ASharesPage", () => {
	it("按交易所展示活跃 A 股身份覆盖", async () => {
		render(<ASharesPage />, { wrapper: wrapper() });

		await expect(screen.findByText("A 股身份覆盖")).resolves.toBeInTheDocument();
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
	});

	it("不会把 metadata 列表冒充收盘快照", async () => {
		render(<ASharesPage />, { wrapper: wrapper() });
		await expect(screen.findByText(/价格与涨跌未查询/)).resolves.toBeInTheDocument();
	});

	it("AI overlay 在缺少行情快照时保持阻断", async () => {
		const user = userEvent.setup();
		render(<ASharesPage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "AI 解读" }));
		expect(screen.getByRole("dialog", { name: "AI 解读" })).toHaveTextContent("行情 snapshot");
	});
});
