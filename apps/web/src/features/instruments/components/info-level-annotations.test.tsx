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
		useParams: () => ({ id: "1000001" }),
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

// ── InstrumentHubPage information hierarchy ──

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

	it("annotates the evidence sections", async () => {
		render(<InstrumentHubPage />, { wrapper: createWrapper() });

		await screen.findAllByText("1000001");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("instrument-profile");
		expect(l2UnitNames).toContain("fundamental-boundary");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates the six server-reported identity fields", async () => {
		render(<InstrumentHubPage />, { wrapper: createWrapper() });

		await screen.findAllByText("1000001");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames.filter((n) => n === "instrument-profile-item")).toHaveLength(6);
		expect(l3Units).toHaveLength(6);
	});
});
