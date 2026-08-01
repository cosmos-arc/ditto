import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { StrategyVersionsView } from "./strategy-versions-view";

function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}

describe("StrategyVersionsView immutable detail", () => {
	it("loads the selected historical version's canonical server payload", async () => {
		let requestedPath = "";
		server.use(
			http.get("/api/v1/strategies/:strategyId/versions/:version", ({ request }) => {
				requestedPath = new URL(request.url).pathname;
				return HttpResponse.json({
					data: {
						strategy_id: "seed_etf_industry_rotation",
						version: 2,
						parent_version: 1,
						spec_hash: "b".repeat(64),
						state: "deprecated",
						review_outcome: "approved",
						created_at: "2026-07-20T00:00:00Z",
						canonical_spec: { schema_version: 2, strategy_family_id: "seed_etf_industry_rotation" },
					},
				});
			}),
		);

		const user = userEvent.setup();
		render(<StrategyVersionsView id="seed_etf_industry_rotation" />, { wrapper });
		await user.click(await screen.findByRole("button", { name: /查看 v2/ }));

		await expect(screen.findByText("Canonical Spec")).resolves.toBeInTheDocument();
		expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
		expect(screen.getByText(/strategy_family_id/)).toBeInTheDocument();
		expect(requestedPath).toBe("/api/v1/strategies/seed_etf_industry_rotation/versions/2");
	});

	it("shows the typed 404 and never falls back to the current strategy payload", async () => {
		server.use(
			http.get("/api/v1/strategies/:strategyId/versions/:version", () =>
				HttpResponse.json({ detail: "version missing", error_code: "STRATEGY_VERSION_NOT_FOUND" }, { status: 404 }),
			),
		);
		const user = userEvent.setup();
		render(<StrategyVersionsView id="seed_etf_industry_rotation" />, { wrapper });
		await user.click(await screen.findByRole("button", { name: /查看 v1/ }));

		await expect(screen.findByText(/STRATEGY_VERSION_NOT_FOUND/)).resolves.toBeInTheDocument();
		expect(screen.queryByText(/strategy_family_id/)).not.toBeInTheDocument();
	});
});
