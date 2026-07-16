import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";
import { server } from "@/mocks/server";
import { InstrumentHubPage } from "./instrument-hub-page";

// Mock TanStack Router's useParams (used by InstrumentHubPage)
vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useParams: () => ({ id: "600519.SH" }),
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

// ── InstrumentHubPage: 3 L1, 2 L2, 12 L3 ──

describe("InstrumentHubPage info-level annotations", () => {
	beforeEach(() => server.use(...instrumentsHandlers));

	it("annotates 3 L1 information units", async () => {
		render(<InstrumentHubPage />, { wrapper: createWrapper() });

		// Wait for instrument name to load (meta strip)
		await screen.findByText("贵州茅台");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("instrument-meta");
		expect(l1UnitNames).toContain("instrument-overview");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 2 L2 information units", async () => {
		render(<InstrumentHubPage />, { wrapper: createWrapper() });

		// Wait for fundamentals data to load
		await screen.findByText("2025Q3");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("financial-statements");
		expect(l2UnitNames).toContain("fundamentals");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates 12 L3 detail items", async () => {
		render(<InstrumentHubPage />, { wrapper: createWrapper() });

		// Wait for fundamentals data to load
		await screen.findByText("2025Q3");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames.filter((n) => n === "income-statement-item")).toHaveLength(4);
		expect(l3UnitNames.filter((n) => n === "fundamental-ratio-item")).toHaveLength(5);
		expect(l3UnitNames.filter((n) => n === "peer-comparison-item")).toHaveLength(3);
		expect(l3Units).toHaveLength(12);
	});
});
