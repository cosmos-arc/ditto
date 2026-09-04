import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { marketsHandlers } from "@/mocks/handlers/markets";
import { server } from "@/mocks/server";
import { ScreenerPage } from "./screener-page";

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

// ── ScreenerPage: 3 L1, 2 L2, 3+ L3 ──

describe("ScreenerPage info-level annotations", () => {
	beforeEach(() => server.use(...marketsHandlers));

	it("annotates 3 L1 information units", async () => {
		render(<ScreenerPage />, { wrapper: createWrapper() });

		// Wait for screener results data to load
		await screen.findByText("贵州茅台");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("screener-main");
		expect(l1UnitNames).toContain("screener-results");
		expect(l1UnitNames).toContain("screener-toolbar");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 2 L2 information units", async () => {
		render(<ScreenerPage />, { wrapper: createWrapper() });

		// Wait for screener results data to load
		await screen.findByText("贵州茅台");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("screener-detail");
		expect(l2UnitNames).toContain("screener-list");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates L3 information units for each screener result item", async () => {
		render(<ScreenerPage />, { wrapper: createWrapper() });

		// Wait for screener results data to load
		await screen.findByText("贵州茅台");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames.filter((n) => n === "screener-result-item").length).toBeGreaterThan(0);
		expect(l3Units.length).toBeGreaterThanOrEqual(3);
	});
});
