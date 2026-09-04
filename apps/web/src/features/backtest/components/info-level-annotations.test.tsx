import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { backtestHandlers } from "@/mocks/handlers/backtest";
import { server } from "@/mocks/server";
import { BacktestPage } from "./backtest-page";

// Mock TanStack Router's useParams (used by BacktestPage)
vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useParams: () => ({ id: "bt-001" }),
	};
});

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

// ── BacktestPage: exact workspace units, with only active-tab records mounted ──

describe("BacktestPage info-level annotations", () => {
	beforeEach(() => server.use(...backtestHandlers));

	it("annotates the four persistent/active L1 information units", async () => {
		render(<BacktestPage />, { wrapper: createWrapper() });

		// Wait for KPI strip metrics to load
		await screen.findByText("Sharpe");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("backtest-meta");
		expect(l1UnitNames).toContain("backtest-tabs");
		expect(l1UnitNames).toContain("backtest-overview");
		expect(l1UnitNames).toContain("backtest-identity");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 2 L2 information units", async () => {
		render(<BacktestPage />, { wrapper: createWrapper() });

		await screen.findByText("净值与基准");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("nav-curve");
		expect(l2UnitNames).toContain("nav-summary");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates exact trade records without synthetic holdings", async () => {
		const user = userEvent.setup();
		render(<BacktestPage />, { wrapper: createWrapper() });

		await screen.findByText("净值与基准");
		await user.click(screen.getByRole("tab", { name: "成交" }));
		await screen.findByText("Instrument #600519");

		const tradeUnits = document.querySelectorAll("[data-info-unit='trade-record']");

		expect(tradeUnits).toHaveLength(2);
		expect(screen.queryByText("当前持仓")).not.toBeInTheDocument();
	});
});
