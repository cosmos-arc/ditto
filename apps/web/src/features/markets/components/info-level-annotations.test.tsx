import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { marketsHandlers } from "@/mocks/handlers/markets";
import { intelligenceHandlers } from "@/mocks/handlers/intelligence";
import { MarketsPage } from "./markets-page";
import { IntelligencePage } from "./intelligence-page";
import { ASharesPage } from "./a-shares-page";
import { CalendarPage } from "./calendar-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const queryClient = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

// ── MarketsPage: 4 L1, 3 L2 (tabbed), 4 L3 ──
// Radix Tabs unmounts inactive panels, so L2 units are only visible
// when their tab is active.

describe("MarketsPage info-level annotations", () => {
	beforeEach(() => server.use(...marketsHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await screen.findByText("上证A股");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("scope-strip");
		expect(l1UnitNames).toContain("market-cards");
		expect(l1UnitNames).toContain("market-events");
		expect(l1UnitNames).toContain("capital-flows");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates default tab L2 unit (macro-drivers)", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await screen.findByText("上证A股");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("macro-drivers");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates capital-rotation L2 unit when rotation tab is active", async () => {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: createWrapper() });

		await screen.findByText("上证A股");
		const rotationTab = await screen.findByRole("tab", { name: "资金轮动" });
		await user.click(rotationTab);
		// Wait for unique content from rotation tab
		await screen.findByText(/\+23\.1亿/);

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("capital-rotation");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates cross-market-matrix L2 unit when correlation tab is active", async () => {
		const user = userEvent.setup();
		render(<MarketsPage />, { wrapper: createWrapper() });

		await screen.findByText("上证A股");
		const correlationTab = await screen.findByRole("tab", { name: "跨市场相关性" });
		await user.click(correlationTab);
		await screen.findByTestId("cross-market-matrix");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("cross-market-matrix");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates 4 L3 information units (market events in right rail)", async () => {
		render(<MarketsPage />, { wrapper: createWrapper() });

		await screen.findByText("科技板块资金净流入 +12.3 亿");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l3UnitNames.filter((n) => n === "market-event-item")).toHaveLength(4);
		expect(l3Units).toHaveLength(4);
	});
});

// ── IntelligencePage: 4 L1 (3 tabbed + sidebar), 1 L2, 4 L3 ──
// Radix Tabs unmounts inactive panels, so L1 view units are only
// visible when their tab is active.

describe("IntelligencePage info-level annotations", () => {
	beforeEach(() => server.use(...marketsHandlers, ...intelligenceHandlers));

	it("annotates default tab L1 unit (intelligence-flow) and sidebar (ai-interpretation)", async () => {
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await screen.findByText("板块排名");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("intelligence-flow");
		expect(l1UnitNames).toContain("ai-interpretation");
		expect(l1Units).toHaveLength(2);
	});

	it("annotates intelligence-macro L1 unit when macro tab is active", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await screen.findByText("板块排名");
		const macroTab = await screen.findByRole("tab", { name: "宏观指标" });
		await user.click(macroTab);
		await screen.findByText("PMI 制造业");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("intelligence-macro");
		expect(l1UnitNames).toContain("ai-interpretation");
	});

	it("annotates intelligence-fundamentals L1 unit when fundamentals tab is active", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await screen.findByText("板块排名");
		const fundamentalsTab = await screen.findByRole("tab", { name: "基本面" });
		await user.click(fundamentalsTab);
		await screen.findByText("贵州茅台");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("intelligence-fundamentals");
		expect(l1UnitNames).toContain("ai-interpretation");
	});

	it("annotates 1 L2 information unit", async () => {
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await screen.findByText("板块排名");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("analysis-panel");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates 4 L3 information units when macro tab is active", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: createWrapper() });

		await screen.findByText("板块排名");
		const macroTab = await screen.findByRole("tab", { name: "宏观指标" });
		await user.click(macroTab);
		await screen.findByText("经济日历");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l3UnitNames.filter((n) => n === "macro-calendar-item")).toHaveLength(4);
	});
});

// ── ASharesPage: 4 L1, 3 L2, 1 L3 ──

describe("ASharesPage info-level annotations", () => {
	beforeEach(() => server.use(...marketsHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<ASharesPage />, { wrapper: createWrapper() });

		await screen.findByText("上证指数");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("a-shares-main");
		expect(l1UnitNames).toContain("index-overview");
		expect(l1UnitNames).toContain("sector-performance");
		expect(l1UnitNames).toContain("market-snapshot");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 3 L2 information units", async () => {
		render(<ASharesPage />, { wrapper: createWrapper() });

		await screen.findByText("上证指数");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("overview-container");
		expect(l2UnitNames).toContain("snapshot-body");
		expect(l2UnitNames).toContain("snapshot-detail");
		expect(l2Units).toHaveLength(3);
	});

	it("annotates 1 L3 information unit", async () => {
		render(<ASharesPage />, { wrapper: createWrapper() });

		await screen.findByText("市场快照");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l3UnitNames).toContain("snapshot-timestamp");
		expect(l3Units).toHaveLength(1);
	});
});

// ── CalendarPage: 3 L1, 1 L2 ──

describe("CalendarPage info-level annotations", () => {
	beforeEach(() => server.use(...marketsHandlers));

	it("annotates 3 L1 information units", async () => {
		render(<CalendarPage />, { wrapper: createWrapper() });

		await screen.findByRole("heading", { name: "市场日历" });

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("calendar-toolbar");
		expect(l1UnitNames).toContain("calendar-content");
		expect(l1UnitNames).toContain("calendar-title");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 1 L2 information unit", async () => {
		render(<CalendarPage />, { wrapper: createWrapper() });

		await screen.findByRole("heading", { name: "市场日历" });

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("calendar-main");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates 0 L3 information units", async () => {
		render(<CalendarPage />, { wrapper: createWrapper() });

		await screen.findByRole("heading", { name: "市场日历" });

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		expect(l3Units).toHaveLength(0);
	});
});
