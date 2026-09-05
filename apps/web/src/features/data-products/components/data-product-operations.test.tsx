import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { dataProductOperationsKeys } from "../api/operations";
import { DataProductOperations } from "./data-product-operations";

function createWrapper(): ({ children }: { readonly children: ReactNode }) => ReactNode {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }): ReactNode {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

function installOperationsHandlers({ promotionStatus = 200 }: { readonly promotionStatus?: number } = {}) {
	server.use(
		http.get("/api/v1/ingestion/catalog/remediation/backlog", () =>
			HttpResponse.json({
				data: {
					generated_at: "2026-08-18T08:00:00Z",
					dataset_ids: ["stock_daily"],
					trade_dates: ["2026-08-18"],
					available_sources: ["wind", "tushare"],
					total_items: 1,
					severity_counts: [{ severity: "high", count: 1 }],
					items: [
						{
							item_id: "rem-stock-daily",
							source: "source_health",
							dataset_id: "stock_daily",
							namespace: "market",
							severity: "high",
							trade_date: "2026-08-18",
							reasons: ["PRIMARY_SOURCE_STALE"],
							suggested_actions: ["activate_fallback"],
							fallback_sources: ["tushare"],
						},
					],
				},
			}),
		),
		http.get("/api/v1/ingestion/catalog/remediation/items/:itemId", ({ params }) =>
			HttpResponse.json({
				data: {
					generated_at: "2026-08-18T08:00:00Z",
					item: {
						item_id: params["itemId"],
						source: "source_health",
						dataset_id: "stock_daily",
						namespace: "market",
						severity: "high",
						trade_date: "2026-08-18",
						reasons: ["PRIMARY_SOURCE_STALE"],
						suggested_actions: ["repair_catalog_freshness"],
						fallback_sources: ["tushare"],
					},
					summary: "Primary source is stale.",
					evidence_requirements: [
						{
							requirement_id: "freshness-evidence",
							source: "source_health",
							status: "missing",
							description: "Refresh source evidence.",
						},
					],
					approval_intents: [
						{
							action: "repair_catalog_freshness",
							intent_type: "write",
							method: "POST",
							path: "/api/v1/ingestion/stock_daily/2026-08-18",
							request_template: { dataset_id: "stock_daily", trade_date: "2026-08-18", force: true },
							required_operator_inputs: [],
						},
					],
				},
			}),
		),
		http.get("/api/v1/ingestion/catalog/source-health", () =>
			HttpResponse.json({
				data: {
					dataset_id: "stock_daily",
					namespace: "market",
					trade_date: "2026-08-18",
					default_source: "wind",
					selected_source: "tushare",
					selected_freshness_status: "ready",
					selected_source_health: { source: "tushare", supported: true, freshness_status: "ready" },
					source_selection_status: "degraded",
					source_selection_blockers: ["PRIMARY_SOURCE_STALE"],
					fallback_sources: ["tushare"],
					unsupported_sources: [],
					sources: [
						{ source: "wind", supported: true, freshness_status: "stale" },
						{ source: "tushare", supported: true, freshness_status: "ready" },
					],
					failover_from_default: true,
				},
			}),
		),
		http.get("/api/v1/ingestion/catalog/source-health/summary", () =>
			HttpResponse.json({
				data: {
					dataset_ids: ["stock_daily"],
					trade_dates: ["2026-08-18"],
					available_sources: ["wind", "tushare"],
					total_reports: 1,
					status_counts: [],
					selected_source_counts: [],
					failover_count: 1,
					no_fallback_source_count: 0,
					revoked_promotion_count: 0,
					attention_required: [],
					attention_reason_counts: [{ reason: "PRIMARY_SOURCE_STALE", count: 1 }],
				},
			}),
		),
		http.get("/api/v1/ingestion/catalog/source-fallback/preview", () =>
			HttpResponse.json({
				data: {
					dataset_id: "stock_daily",
					namespace: "market",
					trade_date: "2026-08-18",
					default_source: "wind",
					selected_source: "tushare",
					selected_freshness_status: "ready",
					policy_status: "active",
					approval_required: true,
					execution_allowed: true,
					source_selection_status: "ready",
					recommended_source: "tushare",
					reason_codes: ["PRIMARY_SOURCE_STALE"],
					recommended_actions: ["draft_policy"],
					fallback_sources: ["tushare"],
					unsupported_sources: [],
					source_selection_blockers: [],
				},
			}),
		),
		http.get("/api/v1/ingestion/catalog/source-fallback/policies", () =>
			HttpResponse.json({
				data: [
					{
						policy_id: "fallback-stock-daily",
						authority_hash: "a".repeat(64),
						authority_payload: { action: "retirement", dataset_id: "stock_daily" },
						dataset_id: "stock_daily",
						namespace: "market",
						trade_date: "2026-08-18",
						default_source: "wind",
						selected_source: "tushare",
						status: "active",
						created_by: "operator",
						created_at: "2026-08-18T07:00:00Z",
						source_selection_status: "ready",
						approval_required: true,
						execution_allowed: true,
						reason_codes: ["PRIMARY_SOURCE_STALE"],
						recommended_actions: [],
						fallback_sources: ["tushare"],
						unsupported_sources: [],
						source_selection_blockers: [],
					},
				],
			}),
		),
		http.get("/api/v1/ingestion/catalog/source-fallback/summary", () =>
			HttpResponse.json({
				data: {
					dataset_ids: ["stock_daily"],
					trade_dates: ["2026-08-18"],
					available_sources: ["wind", "tushare"],
					total_previews: 1,
					approval_required_count: 1,
					execution_allowed_count: 1,
					policy_status_counts: [{ status: "active", count: 1 }],
					recommended_action_counts: [],
					previews: [],
				},
			}),
		),
		http.get("/api/v1/ingestion/catalog/remediation/approvals", () => HttpResponse.json({ data: [] })),
		http.get("/api/v1/ingestion/catalog/promotion/readiness", () =>
			promotionStatus === 200
				? HttpResponse.json({
						data: {
							dataset_count: 1,
							promotable_count: 0,
							active_promotion_count: 0,
							status_counts: [{ status: "blocked", count: 1 }],
							datasets: [
								{
									dataset_id: "stock_daily",
									promotion_status: "blocked",
									active_maturity_promotion: false,
									current_maturity: "experimental",
									missing_criteria: ["provider_parity"],
									rejected_criteria: [],
									required_criteria: ["provider_parity"],
									satisfied_criteria: [],
								},
							],
						},
					})
				: HttpResponse.json({ detail: "promotion unavailable" }, { status: promotionStatus }),
		),
		http.get("/api/v1/ingestion/catalog/promotion/history", () =>
			HttpResponse.json({
				data: [
					{
						action: "revoked",
						action_at: "2026-08-17T08:00:00Z",
						actor: "operator",
						dataset_id: "stock_daily",
						evidence_uri: "ditto://evidence/promotion/provider-parity",
						next_maturity: "experimental",
						previous_maturity: "initial-focus",
						revocation_reason: "failed_revalidation",
					},
				],
			}),
		),
	);
}

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
	installOperationsHandlers();
});

describe("DataProductOperations", () => {
	it("shows remediation, source degradation, active fallback, and promotion blockers", async () => {
		render(<DataProductOperations datasetId="stock_daily" initialTradeDate="2026-08-18" />, {
			wrapper: createWrapper(),
		});

		expect(await screen.findByText("rem-stock-daily")).toBeInTheDocument();
		expect(screen.getAllByText("PRIMARY_SOURCE_STALE").length).toBeGreaterThan(0);
		expect(screen.getByText("source degraded")).toBeInTheDocument();
		expect(screen.getByText("fallback active")).toBeInTheDocument();
		expect(screen.getByText("promotion blocked")).toBeInTheDocument();
		expect(screen.getByText("provider_parity")).toBeInTheDocument();
		expect(await screen.findByRole("button", { name: "预览 remediation request" })).toBeInTheDocument();
		expect(screen.getByText(/freshness-evidence/)).toBeInTheDocument();
		expect(screen.getByText(/ditto:\/\/evidence\/promotion\/provider-parity/)).toBeInTheDocument();
		expect(screen.getByText(new RegExp(`authority ${"a".repeat(64)}`))).toBeInTheDocument();
	});

	it("keeps healthy operations modules usable when one projection fails", async () => {
		installOperationsHandlers({ promotionStatus: 503 });
		render(<DataProductOperations datasetId="stock_daily" initialTradeDate="2026-08-18" />, {
			wrapper: createWrapper(),
		});

		expect(await screen.findByText("部分运营投影不可用")).toBeInTheDocument();
		expect(screen.getByText("promotion: promotion unavailable")).toBeInTheDocument();
		expect(screen.getByText("rem-stock-daily")).toBeInTheDocument();
		expect(screen.getByText("fallback active")).toBeInTheDocument();
	});

	it("renders a closed error state when every base projection fails", async () => {
		const unavailable = () => HttpResponse.json({ detail: "operations unavailable" }, { status: 503 });
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/approvals", unavailable),
			http.get("/api/v1/ingestion/catalog/source-fallback/policies", unavailable),
			http.get("/api/v1/ingestion/catalog/source-fallback/preview", unavailable),
			http.get("/api/v1/ingestion/catalog/source-fallback/summary", unavailable),
			http.get("/api/v1/ingestion/catalog/promotion/readiness", unavailable),
			http.get("/api/v1/ingestion/catalog/promotion/history", unavailable),
			http.get("/api/v1/ingestion/catalog/remediation/backlog", unavailable),
			http.get("/api/v1/ingestion/catalog/source-health", unavailable),
			http.get("/api/v1/ingestion/catalog/source-health/summary", unavailable),
		);
		render(<DataProductOperations datasetId="stock_daily" initialTradeDate="2026-08-18" />, {
			wrapper: createWrapper(),
		});

		expect(await screen.findByText("运营治理不可用")).toBeInTheDocument();
		expect(screen.getByText("error")).toBeInTheDocument();
	});

	it("isolates operations queries by dataset and trade date", () => {
		expect(dataProductOperationsKeys.scope("stock_daily", "2026-08-18")).not.toEqual(
			dataProductOperationsKeys.scope("stock_daily", "2026-08-19"),
		);
		expect(dataProductOperationsKeys.scope("stock_daily", "2026-08-18")).not.toEqual(
			dataProductOperationsKeys.scope("etf_daily", "2026-08-18"),
		);
	});

	it("paginates remediation items and loads the explicitly selected item detail", async () => {
		const user = userEvent.setup();
		const items = Array.from({ length: 7 }, (_, index) => ({
			item_id: `rem-stock-${index + 1}`,
			source: "source_health",
			dataset_id: "stock_daily",
			namespace: "market",
			severity: "high",
			trade_date: "2026-08-18",
			reasons: ["PRIMARY_SOURCE_STALE"],
			suggested_actions: ["repair_catalog_freshness"],
			fallback_sources: ["tushare"],
		}));
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/backlog", () =>
				HttpResponse.json({
					data: {
						generated_at: "2026-08-18T08:00:00Z",
						dataset_ids: ["stock_daily"],
						trade_dates: ["2026-08-18"],
						available_sources: ["wind", "tushare"],
						total_items: items.length,
						severity_counts: [{ severity: "high", count: items.length }],
						items,
					},
				}),
			),
		);
		render(<DataProductOperations datasetId="stock_daily" initialTradeDate="2026-08-18" />, {
			wrapper: createWrapper(),
		});

		expect(await screen.findByRole("button", { name: /rem-stock-1/ })).toHaveAttribute("aria-pressed", "true");
		expect(screen.queryByRole("button", { name: /rem-stock-6/ })).not.toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "下一页 remediation" }));
		await user.click(screen.getByRole("button", { name: /rem-stock-6/ }));

		expect(await screen.findByText("Primary source is stale.")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: /rem-stock-6/ })).toHaveAttribute("aria-pressed", "true");
		expect(screen.getByText("第 2 / 2 页")).toBeInTheDocument();
	});

	it("renders the explicit empty governance state", async () => {
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/backlog", () =>
				HttpResponse.json({
					data: {
						generated_at: "2026-08-18T08:00:00Z",
						dataset_ids: ["stock_daily"],
						trade_dates: ["2026-08-18"],
						available_sources: [],
						total_items: 0,
						severity_counts: [],
						items: [],
					},
				}),
			),
			http.get("/api/v1/ingestion/catalog/source-fallback/policies", () => HttpResponse.json({ data: [] })),
			http.get("/api/v1/ingestion/catalog/promotion/readiness", () =>
				HttpResponse.json({
					data: { dataset_count: 0, promotable_count: 0, active_promotion_count: 0, status_counts: [], datasets: [] },
				}),
			),
		);
		render(<DataProductOperations datasetId="stock_daily" initialTradeDate="2026-08-18" />, {
			wrapper: createWrapper(),
		});

		expect(await screen.findByText("运营投影为空")).toBeInTheDocument();
		expect(screen.getByText(/没有修复、fallback 或晋级治理记录/)).toBeInTheDocument();
	});

	it("marks retained prior-date data stale while the new identity loads", async () => {
		const user = userEvent.setup();
		render(<DataProductOperations datasetId="stock_daily" initialTradeDate="2026-08-18" />, {
			wrapper: createWrapper(),
		});
		expect(await screen.findByText("rem-stock-daily")).toBeInTheDocument();
		server.use(
			http.get("/api/v1/ingestion/catalog/remediation/backlog", async () => {
				await delay(500);
				return HttpResponse.json({
					data: {
						generated_at: "2026-08-19T08:00:00Z",
						dataset_ids: ["stock_daily"],
						trade_dates: ["2026-08-19"],
						available_sources: [],
						total_items: 0,
						severity_counts: [],
						items: [],
					},
				});
			}),
		);

		const dateInput = screen.getByLabelText("治理交易日");
		await user.clear(dateInput);
		await user.type(dateInput, "2026-08-19");

		expect(await screen.findByText("stale")).toBeInTheDocument();
		expect(screen.getByText("rem-stock-daily")).toBeInTheDocument();
	});
});
