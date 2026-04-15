import { describe, it, expect, beforeEach, beforeAll, afterAll } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { homeHandlers } from "@/mocks/handlers/home";
import { tradingHandlers } from "@/mocks/handlers/trading";
import { aiHandlers } from "@/mocks/handlers/ai";
import { platformHandlers } from "@/mocks/handlers/platform";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";
import { strategyHandlers } from "@/mocks/handlers/strategy";
import { marketsHandlers } from "@/mocks/handlers/markets";
import { researchHandlers } from "@/mocks/handlers/research";
import { intelligenceHandlers } from "@/mocks/handlers/intelligence";
import { regimeHandlers } from "@/mocks/handlers/regime";
import { backtestHandlers } from "@/mocks/handlers/backtest";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

/**
 * v3 Interaction Framework Compliance Tests
 *
 * Validates cross-page consistency of v3 design decisions:
 * - D1: L1/L2/L3 information hierarchy
 * - D2: Collapsed sidebar enriched info (MiniSparkline)
 * - D3: Drawer width (440px)
 * - D4: Cross-page consistency
 */
describe("v3 Interaction Framework Compliance", () => {
	beforeAll(() => {
		server.use(
			...homeHandlers,
			...tradingHandlers,
			...aiHandlers,
			...platformHandlers,
			...instrumentsHandlers,
			...strategyHandlers,
			...marketsHandlers,
			...researchHandlers,
			...intelligenceHandlers,
			...regimeHandlers,
			...backtestHandlers,
		);
	});

	beforeEach(() => {
		const qc = createQueryClient();
	 qc.clear();
	});

	describe("Drawer width token", () => {
		it("drawer component uses --width-drawer (440px) token", async () => {
			const { Drawer } = await import(
				"@/components/indicator/overlay/drawer"
			);
			render(
				<Drawer open={true} onClose={() => {}} title="Test">
					Content
				</Drawer>,
			);
			await waitFor(() => {
				const content = document.querySelector(
					"[data-slot='sheet-content']",
				) as HTMLElement;
				expect(content).toBeTruthy();
				expect(content.className).toContain("w-(--width-drawer)");
			});
		});
	});

	describe("MiniSparkline component", () => {
		it("MiniSparkline is exported from data-viz barrel", async () => {
			const mod = await import("@/components/data-viz");
			expect(mod.MiniSparkline).toBeDefined();
		});
	});

	describe("Collapsed sidebar width consistency", () => {
		it("HomeCollapsedSidebar uses --width-sidebar-collapsed", async () => {
			const { HomeCollapsedSidebar } = await import(
				"@/features/home/components/home-collapsed-sidebar"
			);
			render(<HomeCollapsedSidebar />);
			const el = document.querySelector(
				"[data-slot='sidebar-collapsed']",
			) as HTMLElement;
			expect(el).toBeTruthy();
			expect(el.className).toContain("w-(--width-sidebar-collapsed)");
		});

		it("IntelligenceCollapsedSidebar uses --width-sidebar-collapsed", async () => {
			const { IntelligenceCollapsedSidebar } = await import(
				"@/features/markets/components/intelligence-collapsed-sidebar"
			);
			render(<IntelligenceCollapsedSidebar />);
			const el = document.querySelector(
				"[data-slot='sidebar-collapsed']",
			) as HTMLElement;
			expect(el).toBeTruthy();
			expect(el.className).toContain("w-(--width-sidebar-collapsed)");
		});
	});

	describe("L1/L2/L3 annotation coverage", () => {
		it("Home page has at least one L1 unit", async () => {
			const { HomePage } = await import(
				"@/features/home/components/home-page"
			);
			const wrapper = createWrapper();
			render(<HomePage />, { wrapper });
			await waitFor(() => {
				const l1Units = document.querySelectorAll(
					"[data-info-level='l1']",
				);
				expect(l1Units.length).toBeGreaterThanOrEqual(1);
			});
		});

		it("AI page has at least one L1 unit", async () => {
			const { AiPage } = await import("@/features/ai/components/ai-page");
			const wrapper = createWrapper();
			render(<AiPage />, { wrapper });
			await waitFor(() => {
				const l1Units = document.querySelectorAll(
					"[data-info-level='l1']",
				);
				expect(l1Units.length).toBeGreaterThanOrEqual(1);
			});
		});

		it("Platform page has at least one L1 unit", async () => {
			const { PlatformPage } = await import(
				"@/features/platform/components/platform-page"
			);
			const wrapper = createWrapper();
			render(<PlatformPage />, { wrapper });
			await waitFor(() => {
				const l1Units = document.querySelectorAll(
					"[data-info-level='l1']",
				);
				expect(l1Units.length).toBeGreaterThanOrEqual(1);
			});
		});

		it("Trading page has at least one L1 unit", async () => {
			const { TradingPage } = await import(
				"@/features/trading/components/trading-page"
			);
			const wrapper = createWrapper();
			render(<TradingPage />, { wrapper });
			await waitFor(() => {
				const l1Units = document.querySelectorAll(
					"[data-info-level='l1']",
				);
				expect(l1Units.length).toBeGreaterThanOrEqual(1);
			});
		});

		it("Signals page has at least one L1 unit", async () => {
			const { SignalsPage } = await import(
				"@/features/trading/components/signals-page"
			);
			const wrapper = createWrapper();
			render(<SignalsPage />, { wrapper });
			await waitFor(() => {
				const l1Units = document.querySelectorAll(
					"[data-info-level='l1']",
				);
				expect(l1Units.length).toBeGreaterThanOrEqual(1);
			});
		});

		it("all annotated units have data-info-unit attribute", async () => {
			const { HomePage } = await import(
				"@/features/home/components/home-page"
			);
			const wrapper = createWrapper();
			render(<HomePage />, { wrapper });
			await waitFor(() => {
				const annotated = document.querySelectorAll("[data-info-level]");
				for (const el of annotated) {
					expect(
						el.getAttribute("data-info-unit"),
						`Element with data-info-level="${el.getAttribute("data-info-level")}" is missing data-info-unit`,
					).toBeTruthy();
				}
			});
		});
	});
});
