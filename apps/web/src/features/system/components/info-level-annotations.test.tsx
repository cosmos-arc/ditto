import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { systemHandlers } from "@/mocks/handlers/system";
import { server } from "@/mocks/server";
import { SystemPage } from "./system-page";

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
	server.use(...systemHandlers);
});

describe("SystemPage info-level annotations", () => {
	it("annotates the 2 primary evidence units", async () => {
		render(<SystemPage />, { wrapper: createWrapper() });

		await screen.findByText("Remediation backlog");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toEqual(["catalog-assets", "remediation"]);
		expect(l1Units).toHaveLength(2);
	});

	it("annotates 3 L2 information units", async () => {
		render(<SystemPage />, { wrapper: createWrapper() });

		await screen.findByText("Source health");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("source-health");
		expect(l2UnitNames).toContain("fallback");
		expect(l2UnitNames).toContain("promotion");
		expect(l2Units).toHaveLength(3);
	});
});
