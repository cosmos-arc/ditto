import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { platformHandlers } from "@/mocks/handlers/platform";
import { server } from "@/mocks/server";
import { PlatformPage } from "./platform-page";

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
	server.use(...platformHandlers);
});

describe("PlatformPage info-level annotations", () => {
	it("annotates 3 L1 information units", async () => {
		render(<PlatformPage />, { wrapper: createWrapper() });

		await screen.findByText("Data Providers");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("providers");
		expect(l1UnitNames).toContain("pipelines");
		expect(l1UnitNames).toContain("alerts");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 3 L2 information units", async () => {
		render(<PlatformPage />, { wrapper: createWrapper() });

		await screen.findByText("Data Providers");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("tasks");
		expect(l2UnitNames).toContain("resources");
		expect(l2UnitNames).toContain("events");
		expect(l2Units).toHaveLength(3);
	});
});
