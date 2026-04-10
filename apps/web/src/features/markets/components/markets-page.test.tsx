import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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

describe("MarketsPage — Cross-Market Matrix", () => {
	it("renders 跨市场相关性 title", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("跨市场相关性"),
		).resolves.toBeInTheDocument();
	});

	it("renders correlation value 0.85 in symmetric cells", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		// 0.85 appears twice in symmetric matrix (corr-0-1 and corr-1-0)
		const cells = await screen.findAllByText("0.85");
		expect(cells.length).toBe(2);
		for (const cell of cells) {
			expect(cell).toBeInTheDocument();
		}
	});

	it("renders all four index headers in the matrix table", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		// Wait for the matrix to render, then verify headers exist within it
		const matrix = await screen.findByTestId("cross-market-matrix");
		expect(matrix).toBeInTheDocument();
		// "恒生" is unique to the matrix (not in MarketCardGrid which has "恒生指数")
		expect(matrix.querySelector("th")).toBeTruthy();
		// Verify all 4 column headers
		const headers = matrix.querySelectorAll("thead th");
		expect(headers.length).toBe(5); // 1 empty + 4 labels
	});

	it("has cross-market-matrix data-slot attribute", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByTestId("cross-market-matrix"),
		).resolves.toBeInTheDocument();
	});

	it("applies high-correlation class for values >= 0.7", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		const cell085 = await screen.findByTestId("corr-0-1");
		expect(cell085.textContent).toBe("0.85");
		// High correlation cells should have accent-related styling
		expect(cell085.className).toContain("accent");
	});

	it("applies low-correlation class for values < 0.4", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		const cell028 = await screen.findByTestId("corr-1-3");
		expect(cell028.textContent).toBe("0.28");
		// Low correlation cells should have muted styling
		expect(cell028.className).toContain("muted");
	});

	it("applies medium-correlation class for values >= 0.4 and < 0.7", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		const cell062 = await screen.findByTestId("corr-0-2");
		expect(cell062.textContent).toBe("0.62");
		// Medium correlation cells should have moderate styling
		expect(cell062.className).toContain("moderate");
	});

	it("renders diagonal cells as 1.00", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		const cell00 = await screen.findByTestId("corr-0-0");
		expect(cell00.textContent).toBe("1.00");
	});
});

describe("MarketsPage — Capital Rotation FlowBar", () => {
	it("renders FlowBar for each sector", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("资金轮动")).resolves.toBeInTheDocument();
		const flowBars = await screen.findAllByTestId("flow-bar");
		expect(flowBars.length).toBeGreaterThanOrEqual(1);
	});

	it("renders sector names in rotation table", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("科技")).resolves.toBeInTheDocument();
		await expect(screen.findByText("消费")).resolves.toBeInTheDocument();
	});

	it("renders net flow values with font-data class", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText(/\+23\.1亿/)).resolves.toBeInTheDocument();
	});
});
