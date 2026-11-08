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

describe("IntelligencePage composition", () => {
	it("does not pretend a date range was bookmarked or cleared", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "收藏视角" }));
		expect(screen.getByRole("status", { name: "收藏视角暂不可用" })).toBeInTheDocument();
		expect(screen.queryByText("视角已收藏")).not.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "关闭收藏视角暂不可用" }));
		expect(screen.getByRole("button", { name: "收藏视角" })).toHaveFocus();
		await user.click(screen.getByRole("button", { name: "清除收藏" }));
		expect(screen.getByRole("status", { name: "清除收藏暂不可用" })).toBeInTheDocument();
	});

	it("提供日期范围、实验开关与证据说明", () => {
		render(<IntelligencePage />, { wrapper: wrapper() });
		expect(screen.getByLabelText("开始日期")).toBeInTheDocument();
		expect(screen.getByLabelText("截至日期")).toBeInTheDocument();
		expect(screen.getByText("证据边界")).toBeInTheDocument();
	});

	it("缺少 snapshot 时在 Copilot overlay 中保持阻断", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: wrapper() });
		await user.click(screen.getByRole("button", { name: "发送 Copilot" }));
		expect(screen.getByRole("dialog", { name: "发送到 Copilot" })).toHaveTextContent(/snapshot identity/);
	});
});
