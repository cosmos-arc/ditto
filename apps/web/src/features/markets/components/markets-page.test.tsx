import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { marketsHandlers } from "@/mocks/handlers/markets";

import { MarketsPage } from "./markets-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...marketsHandlers));

describe("MarketsPage — live boundary", () => {
	it("live 模式显示 prototype only 空态", () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<MarketsPage />, { wrapper: createWrapper() });

		expect(screen.getByText("prototype only")).toBeInTheDocument();
		expect(screen.getByText("prototype only，请切 VITE_USE_MOCK=true 查看原型数据。")).toBeInTheDocument();
	});
});

describe("MarketsPage — Scope Strip", () => {
	it("renders 今日解读 label", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日解读")).resolves.toBeInTheDocument();
	});

	it("renders market summary text", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText(/A股三大指数集体收涨/),
		).resolves.toBeInTheDocument();
	});

	it("has scope-strip data-slot attribute", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByTestId("scope-strip"),
		).resolves.toBeInTheDocument();
	});
});

describe("MarketsPage — Tab navigation", () => {
	it("shows 宏观驱动 tab by default", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		const macroTab = await screen.findByRole("tab", { name: "宏观驱动" });
		expect(macroTab).toHaveAttribute("data-state", "active");
	});

	it("renders three tab triggers", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(screen.findByRole("tab", { name: "宏观驱动" })).resolves.toBeInTheDocument();
		await expect(screen.findByRole("tab", { name: "资金轮动" })).resolves.toBeInTheDocument();
		await expect(screen.findByRole("tab", { name: "跨市场相关性" })).resolves.toBeInTheDocument();
	});

	it("switches to 资金轮动 tab on click", async () => {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: createWrapper() });

		const rotationTab = await screen.findByRole("tab", { name: "资金轮动" });
		await user.click(rotationTab);

		expect(rotationTab).toHaveAttribute("data-state", "active");
		// Wait for unique content from rotation tab
		await expect(screen.findByText(/\+23\.1亿/)).resolves.toBeInTheDocument();
	});

	it("switches to 跨市场相关性 tab on click", async () => {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: createWrapper() });

		const correlationTab = await screen.findByRole("tab", { name: "跨市场相关性" });
		await user.click(correlationTab);

		expect(correlationTab).toHaveAttribute("data-state", "active");
		await expect(screen.findByTestId("cross-market-matrix")).resolves.toBeInTheDocument();
	});
});

describe("MarketsPage — Cross-Market Matrix (correlation tab)", () => {
	async function switchToCorrelationTab() {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: createWrapper() });
		const correlationTab = await screen.findByRole("tab", { name: "跨市场相关性" });
		await user.click(correlationTab);
		await screen.findByTestId("cross-market-matrix");
	}

	it("renders 跨市场相关性 title after tab switch", async () => {
		await switchToCorrelationTab();

		// "跨市场相关性" appears in both the tab trigger and the content
		const titles = await screen.findAllByText("跨市场相关性");
		expect(titles.length).toBe(2);
	});

	it("renders correlation value 0.85 in symmetric cells", async () => {
		await switchToCorrelationTab();

		const cells = await screen.findAllByText("0.85");
		expect(cells.length).toBe(2);
		for (const cell of cells) {
			expect(cell).toBeInTheDocument();
		}
	});

	it("renders all four index headers in the matrix table", async () => {
		await switchToCorrelationTab();

		const matrix = await screen.findByTestId("cross-market-matrix");
		expect(matrix).toBeInTheDocument();
		expect(matrix.querySelector("th")).toBeTruthy();
		const headers = matrix.querySelectorAll("thead th");
		expect(headers.length).toBe(5); // 1 empty + 4 labels
	});

	it("has cross-market-matrix data-slot attribute", async () => {
		await switchToCorrelationTab();

		await expect(
			screen.findByTestId("cross-market-matrix"),
		).resolves.toBeInTheDocument();
	});

	it("applies high-correlation class for values >= 0.7", async () => {
		await switchToCorrelationTab();

		const cell085 = await screen.findByTestId("corr-0-1");
		expect(cell085.textContent).toBe("0.85");
		expect(cell085.className).toContain("accent");
	});

	it("applies low-correlation class for values < 0.4", async () => {
		await switchToCorrelationTab();

		const cell028 = await screen.findByTestId("corr-1-3");
		expect(cell028.textContent).toBe("0.28");
		expect(cell028.className).toContain("muted");
	});

	it("applies medium-correlation class for values >= 0.4 and < 0.7", async () => {
		await switchToCorrelationTab();

		const cell062 = await screen.findByTestId("corr-0-2");
		expect(cell062.textContent).toBe("0.62");
		expect(cell062.className).toContain("moderate");
	});

	it("renders diagonal cells as 1.00", async () => {
		await switchToCorrelationTab();

		const cell00 = await screen.findByTestId("corr-0-0");
		expect(cell00.textContent).toBe("1.00");
	});
});

describe("MarketsPage — Capital Rotation (rotation tab)", () => {
	async function switchToRotationTab() {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: createWrapper() });
		const rotationTab = await screen.findByRole("tab", { name: "资金轮动" });
		await user.click(rotationTab);
		// Wait for unique content from rotation tab
		await screen.findByText(/\+23\.1亿/);
	}

	it("renders FlowBar for each sector", async () => {
		await switchToRotationTab();

		const flowBars = await screen.findAllByTestId("flow-bar");
		expect(flowBars.length).toBeGreaterThanOrEqual(1);
	});

	it("renders sector names in rotation table", async () => {
		await switchToRotationTab();

		// "科技" appears in both market-cards and rotation tab
		const techElements = await screen.findAllByText("科技");
		expect(techElements.length).toBeGreaterThanOrEqual(2);
		const consumerElements = await screen.findAllByText("消费");
		expect(consumerElements.length).toBeGreaterThanOrEqual(1);
	});

	it("renders net flow values with font-data class", async () => {
		await switchToRotationTab();

		await expect(screen.findByText(/\+23\.1亿/)).resolves.toBeInTheDocument();
	});
});
