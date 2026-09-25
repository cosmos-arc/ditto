import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { expect, it } from "vitest";
import { server } from "@/mocks/server";
import { ETFCandidates } from "./etf-candidates";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

it("selects a real ETF entity and exposes asynchronous NAV and missing evidence", async () => {
	const user = userEvent.setup();
	server.use(
		http.get("/api/v1/metadata/etf-reference-snapshots", () =>
			HttpResponse.json({ data: ["snapshot:recorded:etf:one"] }),
		),
		http.get("/api/v1/metadata/etf-candidates", ({ request }) => {
			const exposure = new URL(request.url).searchParams.get("exposure");
			const price = {
				value: 1.2,
				unit: "CNY",
				observed_on: "2026-09-29",
				published_at: "2026-09-29T18:00:00",
				source: "recorded",
				source_snapshot_id: "snapshot:recorded:etf:one",
				eligibility: "display",
				missing_reason: null,
				effective_from: "2026-09-29",
				effective_to: null,
			};
			return HttpResponse.json({
				data:
					exposure && exposure !== "NDX"
						? []
						: [
								{
									instrument_id: 2000003,
									ticker: "513100",
									name: "跨境 ETF",
									exchange: "SSE",
									is_active: true,
									fields: {
										tracking_index: { ...price, value: "NDX", unit: "index" },
										price_close: price,
										nav: { ...price, value: 1.1, observed_on: "2026-09-27" },
										iopv: { ...price, value: null, missing_reason: "no_qualified_observation" },
									},
									tracking: {
										status: "unavailable",
										reason: "currency_or_benchmark_mismatch",
										sample_count: 252,
										tracking_deviation_pct: null,
										tracking_error_pct: null,
										start: "2025-10-01",
										end: "2026-09-30",
										currency: null,
										benchmark_id: "NDX",
										source_snapshot_id: "snapshot:recorded:etf:one",
										method: "252 aligned daily returns",
									},
								},
							],
			});
		}),
	);
	render(<ETFCandidates />, { wrapper: wrapper() });
	await screen.findByRole("option", { name: "snapshot:recorded:etf:one" });
	await user.selectOptions(await screen.findByLabelText("来源快照"), "snapshot:recorded:etf:one");
	await user.type(screen.getByLabelText("指数暴露"), "NDX");
	await user.click(await screen.findByText(/跨境 ETF · 513100 · NDX/));
	const nav = screen.getByText("最近已披露 NAV").parentElement;
	expect(nav).toHaveTextContent("2026-09-27");
	expect(screen.getByText("IOPV").parentElement).toHaveTextContent("no_qualified_observation");
	expect(screen.getByText(/市价与 NAV 可异步/)).toBeInTheDocument();
	expect(screen.getByText(/同口径跟踪评价不可计算：currency_or_benchmark_mismatch/)).toBeInTheDocument();
	expect(screen.getByText(/已对齐 252\/252 日收益 · 基准 NDX/)).toBeInTheDocument();
});
