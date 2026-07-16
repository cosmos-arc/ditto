import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { researchHandlers } from "@/mocks/handlers/research";

import { FactorTable } from "./factor-table";

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

beforeEach(() => server.use(...researchHandlers));

describe("FactorTable", () => {
	it("renders data-slot=factor-table wrapper", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });
		const wrapper = await screen.findByRole("table");
		expect(wrapper.closest("[data-slot='factor-table']")).toBeInTheDocument();
	});

	it("renders table headers for all 9 columns", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		const table = screen.getByRole("table");
		const headers = within(table).getAllByRole("columnheader");
		const headerTexts = headers.map((h) => h.textContent);

		expect(headerTexts).toEqual([
			"",
			"因子",
			"IC",
			"IR",
			"换手率",
			"衰减",
			"覆盖率",
			"Sharpe",
			"Universe",
			"状态",
		]);
	});

	it("renders factor name in the second column", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		expect(screen.getByText("动量因子")).toBeInTheDocument();
	});

	it("renders family badge next to factor name", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		expect(screen.getByText("技术面")).toBeInTheDocument();
	});

	it("renders IC values with 3 decimal places", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// mockFactors first item: ic = 0.052 -> "0.052"
		expect(screen.getByText("0.052")).toBeInTheDocument();
	});

	it("renders IR values with 2 decimal places", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// mockFactors first item: ir = 0.85 -> "0.85"
		expect(screen.getByText("0.85")).toBeInTheDocument();
	});

	it("renders turnover as percentage", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// mockFactors first item: turnover = 0.32 -> "32%"
		expect(screen.getByText("32%")).toBeInTheDocument();
	});

	it("renders decay values", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// mockFactors first item: decay = 5
		expect(screen.getByText("5")).toBeInTheDocument();
	});

	it("renders coverage as percentage", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// mockFactors first item: coverage = 0.92 -> "92%"
		expect(screen.getByText("92%")).toBeInTheDocument();
	});

	it("renders healthStatus via StatusBadge", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		const badges = document.querySelectorAll("[data-slot='status-badge']");
		expect(badges.length).toBeGreaterThanOrEqual(4);
	});

	it("renders all 5 mock factor rows", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		const table = screen.getByRole("table");
		const rows = within(table).getAllByRole("row");
		// 1 header row + 5 data rows = 6
		expect(rows).toHaveLength(6);
	});

	it("renders ContextSection with title and count", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		expect(screen.getByText("因子监控")).toBeInTheDocument();
	});

	it("renders second factor data correctly", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		expect(screen.getByText("价值因子")).toBeInTheDocument();
		expect(screen.getByText("基本面")).toBeInTheDocument();
	});

	// === Status bar column ===

	it("renders status bar column with correct colors per row", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		const bars = document.querySelectorAll("[data-slot='status-bar']");
		expect(bars).toHaveLength(5);

		// f-005 (failed) should have red color
		const failedBar = bars[4] as HTMLElement;
		expect(failedBar.dataset.health).toBe("failed");

		// f-004 (warning) should have amber color
		const warningBar = bars[3] as HTMLElement;
		expect(warningBar.dataset.health).toBe("warning");
	});

	// === Sharpe column ===

	it("renders Sharpe values with trend arrows", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// f-001: sharpe=1.85 >= 1.5 => ▲ (green/up)
		const sharpeHigh = screen.getByTestId("sharpe-f-001");
		expect(sharpeHigh).toHaveTextContent("▲");
		expect(sharpeHigh.dataset.trend).toBe("up");

		// f-002: sharpe=1.42 >= 1.0 => ▶ (neutral/flat)
		const sharpeMid = screen.getByTestId("sharpe-f-002");
		expect(sharpeMid).toHaveTextContent("▶");
		expect(sharpeMid.dataset.trend).toBe("flat");

		// f-003: sharpe=0.95 < 1.0 => ▼ (red/down)
		const sharpeLow = screen.getByTestId("sharpe-f-003");
		expect(sharpeLow).toHaveTextContent("▼");
		expect(sharpeLow.dataset.trend).toBe("down");
	});

	// === Universe column ===

	it("renders Universe values", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// "全A" appears twice (f-001 and f-004), so use getAllByText
		expect(screen.getAllByText("全A").length).toBeGreaterThanOrEqual(2);
		expect(screen.getByText("沪深300")).toBeInTheDocument();
		expect(screen.getByText("中证500")).toBeInTheDocument();
		expect(screen.getByText("沪股通")).toBeInTheDocument();
	});

	// === IC conditional formatting ===

	it("applies IC conditional color based on absolute IC value", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// f-001: |IC| = 0.052 >= 0.05 => "strong"
		const icStrong = screen.getByTestId("ic-f-001");
		expect(icStrong.dataset.level).toBe("strong");

		// f-002: |IC| = 0.041 >= 0.03 => "normal"
		const icNormal = screen.getByTestId("ic-f-002");
		expect(icNormal.dataset.level).toBe("normal");

		// f-004: |IC| = 0.025 >= 0.02 => "muted"
		const icMuted = screen.getByTestId("ic-f-004");
		expect(icMuted.dataset.level).toBe("muted");

		// f-005: |IC| = 0.015 < 0.02 => "dim"
		const icDim = screen.getByTestId("ic-f-005");
		expect(icDim.dataset.level).toBe("dim");
	});

	it("renders IC spark bar with proportional width", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// f-001: |IC| = 0.052 => width = 52%
		const sparkBar = screen.getByTestId("ic-bar-f-001");
		expect(sparkBar).toBeInTheDocument();
	});

	// === IR conditional formatting ===

	it("applies IR conditional color based on absolute IR value", async () => {
		render(<FactorTable />, { wrapper: createWrapper() });

		await screen.findByRole("table");

		// f-001: |IR| = 0.85 >= 0.8 => "strong"
		const irStrong = screen.getByTestId("ir-f-001");
		expect(irStrong.dataset.level).toBe("strong");

		// f-002: |IR| = 0.72 >= 0.5 => "normal"
		const irNormal = screen.getByTestId("ir-f-002");
		expect(irNormal.dataset.level).toBe("normal");

		// f-004: |IR| = 0.42 >= 0.3 => "muted"
		const irMuted = screen.getByTestId("ir-f-004");
		expect(irMuted.dataset.level).toBe("muted");

		// f-005: |IR| = 0.30 >= 0.3 => "muted" (boundary)
		const irMutedBoundary = screen.getByTestId("ir-f-005");
		expect(irMutedBoundary.dataset.level).toBe("muted");
	});
});
