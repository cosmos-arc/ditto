import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { liveDailyDecisionV3, tradingHandlers } from "@/mocks/handlers/trading";
import { server } from "@/mocks/server";
import { PortfolioPage } from "./portfolio-page";
import { RiskPage } from "./risk-page";
import { TradingPage } from "./trading-page";

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe("R4 live pages", () => {
	beforeEach(() => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		window.history.replaceState({}, "", "/trading?strategy_id=seed_etf_industry_rotation&account_id=paper-a");
		server.use(...tradingHandlers);
	});

	it("renders the R4 cockpit from V3 even when ancillary V2 views fail", async () => {
		const v2Request = vi.fn();
		server.use(
			http.get("/api/v1/trade/daily-decision/v3", () => HttpResponse.json({ data: liveDailyDecisionV3 })),
			http.get("/api/v1/trade/daily-decision/v2", () => {
				v2Request();
				return HttpResponse.json({ detail: "V2 must not drive the R4 cockpit" }, { status: 500 });
			}),
		);

		const { container } = render(<TradingPage />, { wrapper: createWrapper() });

		await screen.findByText("Historical ES99");
		expect(container.querySelector("[data-slot='decision-cockpit']")).toBeInTheDocument();
		const analysis = container.querySelector("[data-slot='analysis']");
		expect(analysis?.querySelector("[data-slot='decision-briefing']")).toBeInTheDocument();
		expect(analysis?.parentElement).toHaveClass("[--height-analysis-band:var(--height-trading-analysis-band)]");
		expect(screen.queryByText("V1a 未接 live")).not.toBeInTheDocument();
		expect(v2Request).toHaveBeenCalled();
	});

	it("renders Portfolio construction evidence from V3", async () => {
		const { container } = render(<PortfolioPage />, { wrapper: createWrapper() });

		await screen.findByText("组合构建证据");
		expect(container.querySelector("[data-slot='portfolio-construction']")).toBeInTheDocument();
		expect(screen.getByText("sha256:mock-policy-r4")).toBeInTheDocument();
		expect(screen.queryByText("experimental live")).not.toBeInTheDocument();
	});

	it("replaces the Risk live placeholder with the V3 decision center", async () => {
		const { container } = render(<RiskPage />, { wrapper: createWrapper() });

		await screen.findByText("Parametric VaR99");
		expect(container.querySelector("[data-slot='risk-decision-center']")).toBeInTheDocument();
		expect(screen.getByText("对账一致")).toBeInTheDocument();
		expect(screen.queryByText("prototype only")).not.toBeInTheDocument();
		expect(screen.queryByText("V1a 未接 live，数据待后端补齐")).not.toBeInTheDocument();
	});
});
