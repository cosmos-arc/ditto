import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { ASharesPage } from "./a-shares-page";
import { CalendarPage } from "./calendar-page";
import { IntelligencePage } from "./intelligence-page";
import { MarketsPage } from "./markets-page";
import { WatchlistPage } from "./watchlist-page";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

beforeEach(() => localStorage.clear());

describe("market information hierarchy", () => {
	it("annotates market coverage, directory and rows", async () => {
		render(<MarketsPage />, { wrapper: wrapper() });
		await screen.findByText("贵州茅台");
		expect(document.querySelector("[data-info-unit='market-boundary']")).toBeInTheDocument();
		expect(document.querySelector("[data-info-unit='instrument-directory']")).toBeInTheDocument();
		expect(document.querySelectorAll("[data-info-unit='instrument-row']")).toHaveLength(4);
	});

	it("annotates A-share coverage and identity rows", async () => {
		render(<ASharesPage />, { wrapper: wrapper() });
		await screen.findByText("贵州茅台");
		expect(document.querySelector("[data-info-unit='a-share-coverage']")).toBeInTheDocument();
		expect(document.querySelectorAll("[data-info-unit='a-share-row']")).toHaveLength(3);
	});

	it("annotates calendar milestones and partition integrity", async () => {
		render(<CalendarPage />, { wrapper: wrapper() });
		await screen.findByText("2026-07-15");
		expect(document.querySelector("[data-info-unit='coverage-milestones']")).toBeInTheDocument();
		expect(document.querySelector("[data-info-unit='partition-integrity']")).toBeInTheDocument();
		expect(document.querySelectorAll("[data-info-unit='coverage-milestone']")).toHaveLength(3);
	});

	it("annotates macro rows only after explicit opt-in", async () => {
		const user = userEvent.setup();
		render(<IntelligencePage />, { wrapper: wrapper() });
		expect(document.querySelectorAll("[data-info-unit='macro-indicator-row']")).toHaveLength(0);
		await user.click(screen.getByRole("checkbox", { name: /允许 experimental/ }));
		await screen.findByText("PMI 制造业");
		expect(document.querySelectorAll("[data-info-unit='macro-indicator-row']")).toHaveLength(2);
	});

	it("annotates watchlist toolbar and boundary", async () => {
		render(<WatchlistPage />, { wrapper: wrapper() });
		await screen.findByText("尚未添加标的");
		expect(document.querySelector("[data-info-unit='watchlist-toolbar']")).toBeInTheDocument();
		expect(document.querySelector("[data-info-unit='watchlist-summary']")).toBeInTheDocument();
		expect(document.querySelector("[data-info-unit='watchlist-catalog']")).toBeInTheDocument();
		expect(document.querySelector("[data-info-unit='watchlist-boundary']")).toBeInTheDocument();
	});
});
