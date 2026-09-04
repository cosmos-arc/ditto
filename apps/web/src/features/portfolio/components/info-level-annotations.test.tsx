import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { ordersHandlers } from "@/mocks/handlers/orders";
import { portfolioHandlers } from "@/mocks/handlers/portfolio";
import { riskHandlers } from "@/mocks/handlers/risk";
import { server } from "@/mocks/server";
import { OrdersPage } from "./orders-page";
import { PortfolioOverviewPage } from "./portfolio-overview-page";
import { RiskPage } from "./risk-page";
import { SignalsPage } from "./signals-page";

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

// ── SignalsPage: 5 L1, 0 L2, responsive desktop + drawer L3 ──

describe("SignalsPage info-level annotations", () => {
	beforeEach(() => server.use(...portfolioHandlers));

	it("annotates 5 L1 information units", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await screen.findByText("待处理");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("signal-metric-pending");
		expect(l1UnitNames).toContain("signal-metric-confirmed");
		expect(l1UnitNames).toContain("signal-metric-ignored");
		expect(l1UnitNames).toContain("signal-metric-ordered");
		expect(l1UnitNames).toContain("signals-list");
		expect(l1Units).toHaveLength(5);
	});

	it("annotates 0 L2 information units", async () => {
		render(<SignalsPage />, { wrapper: createWrapper() });

		await screen.findByText("待处理");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		expect(l2Units).toHaveLength(0);
	});

	it("annotates 1 L3 information unit", async () => {
		const user = userEvent.setup();
		render(<SignalsPage />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: /000001\.SZ.*动量突破/ }));
		await screen.findAllByText("涨跌停检查");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames).toContain("signal-detail");
		expect(l3Units).toHaveLength(2);
	});
});

// ── OrdersPage: 4 L1, 4 L2, responsive desktop + drawer L3 ──

describe("OrdersPage info-level annotations", () => {
	beforeEach(() => server.use(...portfolioHandlers, ...ordersHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<OrdersPage />, { wrapper: createWrapper() });

		await screen.findByText("待提交");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("order-metric-pending");
		expect(l1UnitNames).toContain("order-metric-submitted");
		expect(l1UnitNames).toContain("orders-list");
		expect(l1UnitNames).toContain("fill-ledger");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 3 L2 information units", async () => {
		render(<OrdersPage />, { wrapper: createWrapper() });

		await screen.findByText("待提交");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("order-metric-filled");
		expect(l2UnitNames).toContain("order-metric-failed");
		expect(l2UnitNames).toContain("order-metric-partial");
		expect(l2UnitNames).toContain("signal-to-order-pipeline");
		expect(l2Units).toHaveLength(4);
	});

	it("annotates 1 L3 information unit when drawer is open", async () => {
		const user = userEvent.setup();
		render(<OrdersPage />, { wrapper: createWrapper() });

		await screen.findByText("000001.SZ");
		await user.click(screen.getByText("000001.SZ"));
		await screen.findByRole("dialog");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames).toContain("order-detail");
		expect(l3Units).toHaveLength(2);
	});
});

// ── PortfolioOverviewPage: 5 L1, 4 L2 ──

describe("PortfolioOverviewPage info-level annotations", () => {
	beforeEach(() => server.use(...portfolioHandlers));

	it("annotates 5 L1 information units", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await screen.findByText("连续竞价");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("decision-banner");
		expect(l1UnitNames).toContain("equity-pnl");
		expect(l1UnitNames).toContain("positions-summary");
		expect(l1UnitNames).toContain("risk-alerts");
		expect(l1UnitNames).toContain("orders-panel");
		expect(l1Units).toHaveLength(5);
	});

	it("annotates 4 L2 information units", async () => {
		render(<PortfolioOverviewPage />, { wrapper: createWrapper() });

		await screen.findByText("连续竞价");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("session-strip");
		expect(l2UnitNames).toContain("signals-queue");
		expect(l2UnitNames).toContain("risk-alerts-signals");
		expect(l2UnitNames).toContain("risk-alerts-orders");
		expect(l2Units).toHaveLength(4);
	});
});

// ── RiskPage: 4 L1, 2 L2 ──

describe("RiskPage info-level annotations", () => {
	beforeEach(() => server.use(...riskHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<RiskPage />, { wrapper: createWrapper() });

		await screen.findByText("VaR(95%)");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("risk-primary-strip");
		expect(l1UnitNames).toContain("risk-gauges");
		expect(l1UnitNames).toContain("risk-dashboard");
		expect(l1UnitNames).toContain("risk-activity-rail");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 2 L2 information units", async () => {
		const user = userEvent.setup();
		render(<RiskPage />, { wrapper: createWrapper() });

		await screen.findByText("单日 VaR 超限");
		await user.click(screen.getByText("单日 VaR 超限").closest("div")!);

		await waitFor(() => {
			const l2Units = document.querySelectorAll("[data-info-level='l2']");
			const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

			expect(l2UnitNames).toContain("risk-analysis-band");
			expect(l2UnitNames).toContain("breach-detail");
			expect(l2Units).toHaveLength(2);
		});
	});
});
