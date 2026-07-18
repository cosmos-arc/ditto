import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { DataProductWorkbench } from "./data-product-workbench";

const DATASET_IDS = [
	"calendar",
	"stock_basic",
	"etf_basic",
	"index_basic",
	"stock_daily",
	"etf_daily",
	"index_daily",
	"adj_factor",
	"fund_adj",
	"stock_status",
	"index_weight",
	"corporate_actions",
	"balance_sheet",
	"income_statement",
	"cash_flow",
	"dividend",
	"valuation_metrics",
	"macro_indicators",
	"commodity_daily",
] as const;

function createWrapper(): ({ children }: { readonly children: ReactNode }) => ReactNode {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }): ReactNode {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

function overviewRows() {
	return DATASET_IDS.map((datasetId, index) => ({
		dataset_id: datasetId,
		r2_scope: "hard",
		maturity: index < 11 ? "initial-focus" : "experimental",
		schedule: datasetId.includes("daily") ? "trading_days" : "source_defined",
		owner: "data-platform",
		raw_target_from: "2015-01-01",
		certified_target_from: "2015-01-01",
		active_certification_report_id: index === 0 ? "cert-calendar-1" : null,
	}));
}

function installReadyHandlers(): void {
	server.use(
		http.get("/api/v1/data-products", () => HttpResponse.json({ data: overviewRows() })),
		http.get("/api/v1/data-products/:datasetId/coverage", ({ params }) =>
			HttpResponse.json({
				data: {
					dataset_id: params.datasetId,
					profile: "research_daily",
					raw_from: "2005-01-04",
					complete_from: "2015-01-05",
					certified_from: "2015-01-05",
					expected_partitions: 2500,
					actual_partitions: 2499,
					gaps: ["2026-07-15"],
					unapproved_gaps: ["2026-07-15"],
				},
			}),
		),
		http.get("/api/v1/data-products/:datasetId/quality", ({ params }) =>
			HttpResponse.json({
				data: {
					dataset_id: params.datasetId,
					profile: "research_daily",
					report_id: "cert-calendar-1",
					dq_rule_version: "dq-v3",
					dq_results: [
						{ name: "partition completeness", evidence_uri: "evidence://dq/completeness", passed: true },
						{ name: "provider parity: tushare vs local_tdx", evidence_uri: "evidence://dq/provider", passed: false },
					],
					pit_replay_results: [{ name: "knowledge date replay", evidence_uri: "evidence://pit/replay", passed: true }],
					freshness_results: [{ name: "T+1 freshness", evidence_uri: "evidence://freshness", passed: true }],
					recovery_results: [{ name: "chunk restore", evidence_uri: "evidence://recovery", passed: true }],
					consumer_results: [{ name: "R1 preflight", evidence_uri: "evidence://consumer", passed: true }],
				},
			}),
		),
		http.get("/api/v1/data-products/:datasetId/runs", ({ params }) =>
			HttpResponse.json({
				data: [
					{
						dataset_id: params.datasetId,
						profile: "research_daily",
						report_id: "cert-calendar-1",
						generated_at: "2026-07-18T03:20:00Z",
						content_hash: "sha256:calendar",
						status: "approved",
						reviewed_by: "operator",
						reviewed_at: "2026-07-18T03:30:00Z",
						revocation_reason: null,
					},
				],
			}),
		),
		http.get("/api/v1/data-products/:datasetId/evidence", ({ params }) =>
			HttpResponse.json({
				data: {
					dataset_id: params.datasetId,
					profile: "research_daily",
					report_id: "cert-calendar-1",
					content_hash: "sha256:calendar",
					source_ids: ["tushare:trade_cal", "local_tdx:calendar"],
					schema_versions: ["calendar:v2"],
					snapshot_ids: ["snapshot-calendar-20260718"],
					fallback_history: ["tushare -> local_tdx (preview only)"],
					override_history: ["coverage exception rejected"],
				},
			}),
		),
		http.get("/api/v1/data-products/:datasetId/license", ({ params }) =>
			HttpResponse.json({
				data: {
					dataset_id: params.datasetId,
					profile: "research_daily",
					report_id: "cert-calendar-1",
					license_record_ids: ["license-tushare-reviewed-v1"],
				},
			}),
		),
	);
}

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
	installReadyHandlers();
});

describe("DataProductWorkbench", () => {
	it("renders all 19 hard-scope products with text-based certification state", async () => {
		render(<DataProductWorkbench />, { wrapper: createWrapper() });

		const catalog = await screen.findByRole("table", { name: "R2 数据产品目录" });
		expect(within(catalog).getAllByRole("row")).toHaveLength(20);
		expect(within(catalog).getByRole("button", { name: /calendar/ })).toHaveTextContent("已认证");
		expect(within(catalog).getByRole("button", { name: /stock_basic/ })).toHaveTextContent("待认证");
		expect(screen.getByText("Bundle readiness: blocked")).toBeInTheDocument();
	});

	it("supports keyboard tab navigation and exposes the three coverage milestones", async () => {
		const user = userEvent.setup();
		render(<DataProductWorkbench />, { wrapper: createWrapper() });
		const overviewTab = await screen.findByRole("tab", { name: "概览" });

		overviewTab.focus();
		await user.keyboard("{ArrowRight}");

		expect(screen.getByRole("tab", { name: "覆盖" })).toHaveAttribute("aria-selected", "true");
		expect(await screen.findByText("2005-01-04")).toBeInTheDocument();
		expect(screen.getAllByText("2015-01-05")).toHaveLength(2);
		expect(screen.getByText("未批准缺口 1")).toBeInTheDocument();
	});

	it("shows DQ, PIT and provider difference evidence without color-only status", async () => {
		const user = userEvent.setup();
		render(<DataProductWorkbench />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("tab", { name: "质量" }));

		expect(await screen.findByText("DQ 与 Provider 差异")).toBeInTheDocument();
		expect(screen.getByText("provider parity: tushare vs local_tdx")).toBeInTheDocument();
		expect(screen.getByText("PIT Replay")).toBeInTheDocument();
		expect(screen.getAllByText(/通过/).length).toBeGreaterThan(0);
		expect(screen.getByText(/失败/)).toBeInTheDocument();
	});

	it("keeps chunk repair disabled until the exact preview phrase is confirmed", async () => {
		const user = userEvent.setup();
		render(<DataProductWorkbench />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("tab", { name: "运行与修复" }));
		expect(await screen.findByText("Chunk 修复与重试")).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "预览 repair" }));

		const confirmation = "data-product:repair:calendar:confirm";
		expect(screen.getByText(confirmation)).toBeInTheDocument();
		const confirmButton = screen.getByRole("button", { name: "生成已确认指令" });
		expect(confirmButton).toBeDisabled();
		await user.type(screen.getByLabelText("输入完整确认短语"), confirmation);
		expect(confirmButton).toBeEnabled();
		await user.click(confirmButton);
		expect(screen.getByRole("status")).toHaveTextContent("已确认 repair");
		expect(screen.getByText(/ditto data-products repair calendar/)).toBeInTheDocument();
	});

	it("binds immutable certification, source snapshots and reviewed licenses", async () => {
		const user = userEvent.setup();
		render(<DataProductWorkbench />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("tab", { name: "证据与许可" }));

		expect(await screen.findByText("snapshot-calendar-20260718")).toBeInTheDocument();
		expect(screen.getByText("license-tushare-reviewed-v1")).toBeInTheDocument();
		expect(screen.getByText("sha256:calendar")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "预览 certify" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "预览 promotion" })).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "预览 revoke" })).toBeInTheDocument();
	});

	it("renders an instructional empty state instead of hardcoded products", async () => {
		server.use(http.get("/api/v1/data-products", () => HttpResponse.json({ data: [] })));

		render(<DataProductWorkbench />, { wrapper: createWrapper() });

		expect(await screen.findByText("尚无 R2 数据产品")).toBeInTheDocument();
		expect(screen.getByText(/先运行 acceptance fixture/)).toBeInTheDocument();
	});
});
