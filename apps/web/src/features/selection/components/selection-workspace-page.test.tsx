import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { selectionRunInputFixture } from "@/mocks/fixtures/selection";
import { selectionHandlers } from "@/mocks/handlers/selection";
import { server } from "@/mocks/server";
import { SelectionWorkspacePage } from "./selection-workspace-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => {
	localStorage.clear();
	server.use(...selectionHandlers);
});

describe("SelectionWorkspacePage", () => {
	it("starts from the production A-share stock discovery spec", async () => {
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		expect(screen.getByRole("textbox", { name: "SelectionSpec ID" })).toHaveValue("a-share-stock-discovery");
	});

	it("renders saved SelectionRuns with exact candidates, factors, exclusions, and Agent context", async () => {
		const user = userEvent.setup();
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		expect(screen.getAllByText("momentum").length).toBeGreaterThan(0);
		expect(screen.getByText("0.5400")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "贵州茅台" })).toHaveAttribute(
			"href",
			"/instruments/600519?tab=technical&selectionRunId=selection-run%3Asha256%3Arun-one",
		);
		await user.click(screen.getByRole("tab", { name: "排除 1" }));
		expect(screen.getByText("insufficient_liquidity")).toBeInTheDocument();
		expect(screen.getByRole("link", { name: "邯郸钢铁" })).toHaveAttribute(
			"href",
			"/instruments/600001?tab=technical&selectionRunId=selection-run%3Asha256%3Arun-one",
		);

		const memo = screen.getByRole("link", { name: "生成 SelectionMemo" });
		expect(memo).toHaveAttribute("href", expect.stringContaining("contextType=selection"));
		expect(memo).toHaveAttribute("href", expect.stringContaining("contextId=selection-run%3Asha256%3Arun-one"));
	});

	it("compares two exact saved runs and labels the source of drift", async () => {
		const user = userEvent.setup();
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		const selectors = await screen.findAllByRole("checkbox", { name: /加入运行对比/ });
		await user.click(selectors[0] as HTMLElement);
		await user.click(selectors[1] as HTMLElement);
		await user.click(screen.getByRole("button", { name: "比较 2 个运行" }));

		await expect(screen.findByText("数据快照已变化")).resolves.toBeInTheDocument();
		expect(screen.getByText("行业轮动已变化")).toBeInTheDocument();
		expect(screen.getByText("300750 · 1 → 2")).toBeInTheDocument();
	});

	it("saves a typed input draft locally and persists the returned SelectionRun", async () => {
		const user = userEvent.setup();
		render(<SelectionWorkspacePage />, { wrapper: wrapper() });

		await user.click(screen.getByText("新建运行 · 导入规范化输入包"));
		fireEvent.change(screen.getByLabelText("Selection 输入 JSON"), {
			target: { value: JSON.stringify(selectionRunInputFixture) },
		});
		await user.click(screen.getByRole("button", { name: "校验并保存输入" }));
		expect(localStorage.getItem("ditto.selection-run-input.v1")).toContain('"spec_id": "a-share-stock-discovery"');
		await user.click(screen.getByRole("button", { name: "执行 SelectionRun" }));

		await expect(screen.findByText("已保存 SelectionRun run-one")).resolves.toBeInTheDocument();
	});
});
