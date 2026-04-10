import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { tradingHandlers } from "@/mocks/handlers/trading";

import { PositionsSummary } from "./positions-summary";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...tradingHandlers));

describe("PositionsSummary", () => {
	it("渲染持仓标题", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("持仓汇总"),
		).resolves.toBeInTheDocument();
	});

	it("使用 DataTable 渲染 8 列表头（含 7日 sparkline）", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		const headers = screen.getAllByRole("columnheader");
		const headerTexts = headers.map((h) => h.textContent);
		expect(headerTexts).toContain("代码");
		expect(headerTexts).toContain("名称");
		expect(headerTexts).toContain("数量");
		expect(headerTexts).toContain("成本");
		expect(headerTexts).toContain("现价");
		expect(headerTexts).toContain("7日");
		expect(headerTexts).toContain("盈亏");
		expect(headerTexts).toContain("盈亏%");
		expect(headers).toHaveLength(8);
	});

	it("渲染所有持仓行", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		const rows = screen.getAllByRole("row");
		// 1 header row + 5 data rows = 6 (summary is a div, not a table row)
		expect(rows).toHaveLength(6);
	});

	it("显示持仓代码", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("000001.SZ"),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("600519.SH"),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("300750.SZ"),
		).resolves.toBeInTheDocument();
	});

	it("显示数值列（成本、现价带 2 位小数）", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		// 成本 avgCost=11.25 → toFixed(2) → "11.25"
		expect(screen.getByText("11.25")).toBeInTheDocument();
		// 现价 currentPrice=1755.5 → toFixed(2) → "1755.50"
		expect(screen.getByText("1755.50")).toBeInTheDocument();
	});

	it("显示冻结标识", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("冻结 1,000"),
		).resolves.toBeInTheDocument();
	});

	it("盈亏正值显示绿色", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		// pnl=8300 → positive, should use market-up color class
		const positiveCells = screen
			.getAllByText(/\+?8,300/)
			.filter((el) =>
				el.classList.contains("text-(--color-market-up)"),
			);
		expect(positiveCells.length).toBeGreaterThanOrEqual(1);
	});

	it("data-slot 为 positions-summary", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		const wrapper = screen
			.getByText("平安银行")
			.closest('[data-slot="positions-summary"]');
		expect(wrapper).toBeTruthy();
	});

	it("包含 DataTable（data-slot=data-table）", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		const table = document.querySelector(
			'[data-slot="data-table"]',
		);
		expect(table).toBeTruthy();
	});

	it("盈亏%显示百分比后缀", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		// pnlPercent=7.38 → "+7.38%"
		expect(screen.getByText("+7.38%")).toBeInTheDocument();
	});

	it("7日 sparkline 列渲染 SVG 元素", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		const sparklines = document.querySelectorAll(
			'[data-slot="sparkline"]',
		);
		// 5 positions, each with sparkline data → 5 sparkline SVGs
		expect(sparklines).toHaveLength(5);
	});

	it("sparkline 颜色根据盈亏方向决定", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		// All mock positions have positive pnl → "up" variant
		const upSparklines = document.querySelectorAll(
			'[data-slot="sparkline"][data-variant="up"]',
		);
		expect(upSparklines).toHaveLength(5);
	});

	it("行背景根据盈亏方向着色", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		// All mock positions have positive pnl → all rows should have market-up background
		const tableBody = document.querySelector("tbody");
		const rows = tableBody?.querySelectorAll("tr");
		expect(rows).toBeTruthy();
		expect(rows!.length).toBe(5);

		for (const row of rows!) {
			// Positive pnl rows should have market-up background color mix
			expect(row.className).toContain("bg-[color-mix");
		}
	});

	it("汇总行显示总盈亏", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(
			screen.findByText("平安银行"),
		).resolves.toBeInTheDocument();

		// Total PnL = 8300 + 15100 + 12640 + 10050 + 8400 = 54490
		const summary = document.querySelector(
			'[data-slot="positions-summary-footer"]',
		);
		expect(summary).toBeTruthy();
		expect(summary!.textContent).toContain("54,490");
	});
});
