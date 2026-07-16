import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
		useParams: () => ({ id: "job-001" }),
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

// ── BacktestPage: 3 L1 (active tab only), 2 L2, 3 L3 ──

describe("BacktestPage info-level annotations", () => {
	beforeEach(() => server.use(...backtestHandlers));

	it("annotates 3 L1 information units (active tab only)", async () => {
		render(<BacktestPage />, { wrapper: createWrapper() });

		// Wait for KPI strip metrics to load
		await screen.findByText("Sharpe");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("backtest-kpi-strip");
		expect(l1UnitNames).toContain("backtest-overview");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 2 L2 information units", async () => {
		render(<BacktestPage />, { wrapper: createWrapper() });

		await screen.findByText("净值曲线");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("nav-curve");
		expect(l2UnitNames).toContain("current-holdings");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates 3 L3 holding items", async () => {
		render(<BacktestPage />, { wrapper: createWrapper() });

		await screen.findByText("贵州茅台");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames.filter((n) => n === "holding-item")).toHaveLength(3);
		expect(l3Units).toHaveLength(3);
	});
});
