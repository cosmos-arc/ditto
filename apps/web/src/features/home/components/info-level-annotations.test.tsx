import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { homeHandlers } from "@/mocks/handlers/home";
import { HomePage } from "./home-page";

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

beforeEach(() => {
	server.use(...homeHandlers);
});

describe("HomePage info-level annotations", () => {
	it("annotates 5 L1 information units", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		// Wait for all data to load (banner text appears after mock resolves)
		await screen.findByText("今日盈亏");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("decision-banner");
		expect(l1UnitNames).toContain("priority-queue");
		expect(l1UnitNames).toContain("market-pulse");
		expect(l1UnitNames).toContain("global-alerts");
		expect(l1UnitNames).toContain("data-health");
		expect(l1Units).toHaveLength(5);
	});

	it("annotates 3 L2 information units", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		await screen.findByText("今日盈亏");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("research-progress");
		expect(l2UnitNames).toContain("agent-findings");
		expect(l2UnitNames).toContain("workspace-placeholder");
		expect(l2Units).toHaveLength(3);
	});
});
