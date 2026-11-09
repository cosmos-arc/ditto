import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, expect, it } from "vitest";
import { server } from "@/mocks/server";
import type { BacktestRun } from "../types";
import { BacktestRequestPanel } from "./backtest-request-panel";

const run: BacktestRun = {
	runId: "history-old",
	strategyId: "etf",
	strategyVersion: "1",
	mode: "backtest",
	status: "failed",
	startedAt: "",
	completedAt: "",
	errorMessage: "missing fund_adj",
	parentRunId: "",
	benchmarkReturn: null,
	progressPct: 0,
	currentStep: "",
	completedDays: 0,
	totalDays: 0,
};
const request = {
	run_id: run.runId,
	purpose: "historical_reconstruction",
	start_date: "2014-10-13",
	end_date: "2014-11-07",
	initial_cash: 1000000,
	universe: "declared-pool",
	input_status: "blocked",
	frozen_at: "2026-11-09T01:00:00+00:00",
	reason: "missing fund_adj",
	members: ["510300.SH"],
	limitations: ["历史可得性未认证"],
	sources: [
		{
			dataset: "etf_daily",
			source: "tushare",
			snapshot_id: "snapshot:original",
			checksum: "abc",
			request_start: "2014-01-01",
			request_end: "2014-12-31",
			received_at: "2026-10-12T00:00:00+00:00",
			observed_at: "2026-10-12T00:00:00+00:00",
			rows: 100,
			verified: true,
		},
	],
};
function wrapper({ children }: { readonly children: ReactNode }) {
	return (
		<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
			{children}
		</QueryClientProvider>
	);
}
beforeEach(() => {
	sessionStorage.clear();
	server.use(http.get("/api/v1/backtests/runs/:id/request", () => HttpResponse.json({ data: request })));
});

it("reopens 2014 scope with real 2026 receipt and recovers once after a lost response/reload", async () => {
	const user = userEvent.setup();
	const keys: (string | null)[] = [];
	server.use(
		http.post("/api/v1/backtests/runs/:id/retry", ({ request: req }) => {
			keys.push(req.headers.get("Idempotency-Key"));
			return keys.length === 1
				? HttpResponse.error()
				: HttpResponse.json(
						{
							data: { run_id: "history-new", parent_run_id: run.runId, status: "pending" },
						},
						{ status: 202 },
					);
		}),
	);
	const first = render(<BacktestRequestPanel run={run} />, { wrapper });
	await screen.findByText(/请求区间 2014-10-13/);
	expect(screen.getByText(/实际入库 2026-10-12/)).toBeVisible();
	expect(screen.getByText(/510300.SH/)).toBeVisible();
	await user.click(screen.getByRole("button", { name: "补证后沿原配置新建运行" }));
	await screen.findByText(/再次点击将核对同一次恢复/);
	first.unmount();
	const second = render(<BacktestRequestPanel run={run} />, { wrapper });
	await user.click(await screen.findByRole("button", { name: "补证后沿原配置新建运行" }));
	const link = await screen.findByRole("link", { name: "打开补证后的新运行" });
	expect(link).toHaveAttribute("href", "/research/backtests/history-new");
	expect(keys[0]).toBeTruthy();
	expect(keys[1]).toBe(keys[0]);
	expect(screen.getByText("missing fund_adj")).toBeVisible();
	second.unmount();
	render(<BacktestRequestPanel run={run} />, { wrapper });
	expect(await screen.findByRole("link", { name: "打开补证后的新运行" })).toBeVisible();
	expect(screen.queryByRole("button", { name: "补证后沿原配置新建运行" })).not.toBeInTheDocument();
});

it("keeps an unreadable request explicit and lets the user retry reading", async () => {
	const user = userEvent.setup();
	let calls = 0;
	server.use(
		http.get("/api/v1/backtests/runs/:id/request", () =>
			++calls === 1
				? HttpResponse.json({ detail: "暂时无法读取", error_code: "UNAVAILABLE" }, { status: 503 })
				: HttpResponse.json({ data: request }),
		),
	);
	render(<BacktestRequestPanel run={run} />, { wrapper });
	await user.click(await screen.findByRole("button", { name: "重试请求读取" }));
	expect(await screen.findByText(/请求区间 2014-10-13/)).toBeVisible();
});

it.each([
	{ parent_run_id: run.runId, status: "pending" },
	{ run_id: 123, parent_run_id: run.runId, status: "pending" },
	{ run_id: "", parent_run_id: run.runId, status: "pending" },
	{ run_id: "new", parent_run_id: "different", status: "pending" },
	{ run_id: "new", parent_run_id: run.runId, status: "unknown" },
])("rejects malformed recovery receipts without saving a successful link: %j", async (receipt) => {
	server.use(
		http.post("/api/v1/backtests/runs/:id/retry", () => HttpResponse.json({ data: receipt }, { status: 202 })),
	);
	render(<BacktestRequestPanel run={run} />, { wrapper });
	await userEvent.setup().click(await screen.findByRole("button", { name: "补证后沿原配置新建运行" }));
	await screen.findByText(/恢复响应无效/);
	expect(screen.queryByRole("link", { name: "打开补证后的新运行" })).not.toBeInTheDocument();
	expect(new URLSearchParams(sessionStorage.getItem(`ditto:backtest-recovery:${run.runId}`) ?? "").has("runId")).toBe(
		false,
	);
});

it.each([{ run_id: "another-run" }, { purpose: "unknown" }, { input_status: "unknown" }])(
	"rejects mismatched request identity or semantics: %j",
	async (invalid) => {
		server.use(
			http.get("/api/v1/backtests/runs/:id/request", () => HttpResponse.json({ data: { ...request, ...invalid } })),
		);
		render(<BacktestRequestPanel run={run} />, { wrapper });
		await screen.findByText(/请求来源响应无效/);
		expect(screen.queryByRole("button", { name: "补证后沿原配置新建运行" })).not.toBeInTheDocument();
		expect(screen.queryByText(/实际入库/)).not.toBeInTheDocument();
	},
);

it("shows an old request without optional scope evidence as unrecorded", async () => {
	server.use(
		http.get("/api/v1/backtests/runs/:id/request", () =>
			HttpResponse.json({
				data: {
					run_id: run.runId,
					purpose: "unclassified",
					input_status: "unrecorded",
					universe: "",
					frozen_at: "",
					reason: "",
					start_date: null,
					end_date: null,
					initial_cash: null,
				},
			}),
		),
	);
	render(<BacktestRequestPanel run={run} />, { wrapper });
	await screen.findByText(/旧请求未记录用途.*未记录冻结预检/);
	expect(screen.getByText(/请求区间 未记录 → 未记录.*初始资金 未记录/)).toBeVisible();
	expect(screen.getByText(/证券池 未记录.*冻结证券 尚未解析/)).toBeVisible();
	expect(screen.getByText("尚无已保存的冻结来源。")).toBeVisible();
	expect(screen.queryByText(/载荷校验通过/)).not.toBeInTheDocument();
});

it("reads saved daily exclusions with keyboard selection and explicit trading-day units", async () => {
	server.use(
		http.get("/api/v1/backtests/runs/:id/request", () =>
			HttpResponse.json({
				data: {
					...request,
					participation: [
						{
							instrument_id: 1,
							symbol: "510300.SH",
							trade_date: "2014-10-13",
							status: "warmup",
							warmup_available: 3,
							warmup_required: 60,
							evaluated: false,
						},
						{
							instrument_id: 1,
							symbol: "510300.SH",
							trade_date: "2014-10-14",
							status: "outside_universe",
							warmup_available: 4,
							warmup_required: 60,
							evaluated: true,
						},
					],
				},
			}),
		),
	);
	const user = userEvent.setup();
	render(<BacktestRequestPanel run={run} />, { wrapper });
	const select = await screen.findByLabelText("逐日参与日期");
	expect(screen.getByText("交易日预热不足")).toBeVisible();
	expect(screen.getByText("3 / 60 交易日")).toBeVisible();
	expect(screen.getByText("预检；尚无执行证据")).toBeVisible();
	select.focus();
	await user.selectOptions(select, "2014-10-14");
	expect(select).toHaveFocus();
	expect(screen.getByText("当日不在证券池")).toBeVisible();
	expect(screen.getByText("当日已执行")).toBeVisible();
});

it.each([{ evaluated: "false" }, { evaluated: true, execution_rule: 10 }])(
	"rejects malformed saved eligibility or rule: %j",
	async (invalid) => {
		server.use(
			http.get("/api/v1/backtests/runs/:id/request", () =>
				HttpResponse.json({
					data: {
						...request,
						participation: [
							{
								instrument_id: 1,
								symbol: "510300.SH",
								trade_date: "2014-10-13",
								status: "eligible",
								warmup_available: 60,
								warmup_required: 60,
								...invalid,
							},
						],
					},
				}),
			),
		);
		render(<BacktestRequestPanel run={run} />, { wrapper });
		expect(await screen.findByRole("alert")).toHaveTextContent("逐日参与记录无效");
		expect(screen.queryByText("当日已执行")).not.toBeInTheDocument();
	},
);

it("reopens the saved daily execution rule with dates and trading units", async () => {
	server.use(
		http.get("/api/v1/backtests/runs/:id/request", () =>
			HttpResponse.json({
				data: {
					...request,
					participation: [
						{
							instrument_id: 1005567,
							symbol: "001246.SZ",
							trade_date: "2026-10-14",
							status: "eligible",
							warmup_available: 5,
							warmup_required: 1,
							evaluated: true,
							execution_rule: "XSHE/main/2026-10-14 · 涨跌幅 10% · 买入 100 股 · 报价 0.01 元 · T+1",
						},
					],
				},
			}),
		),
	);
	render(<BacktestRequestPanel run={run} />, { wrapper });
	expect(await screen.findByRole("columnheader", { name: "执行规则" })).toBeVisible();
	expect(screen.getByText(/XSHE\/main\/2026-10-14/)).toBeVisible();
});
