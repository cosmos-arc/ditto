import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useUIPreferences } from "@/features/shell";
import { HomePage } from "./home-dashboard";

function wrapper() {
	const client = new QueryClient({
		defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } },
	});
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
	useUIPreferences.setState({ sidebarCollapsed: false });
});

describe("Home dashboard workflow", () => {
	it("supplies certified Data Product evidence to both Home MarketContext consumers", async () => {
		render(<HomePage />, { wrapper: wrapper() });

		await expect(screen.findAllByText("风险偏好")).resolves.toHaveLength(2);
		expect(screen.getByText("证据 2 · 快照 7")).toBeInTheDocument();
		expect(screen.queryByText("MarketContext 不可用")).not.toBeInTheDocument();
	});
});
