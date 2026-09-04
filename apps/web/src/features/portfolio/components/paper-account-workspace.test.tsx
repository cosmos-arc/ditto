import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import type { components } from "@/types/generated/api";
import { PaperAccountWorkspace } from "./paper-account-workspace";

type PaperLedger = components["schemas"]["PaperAccountLedgerResponse"];
type PaperSessionRead = components["schemas"]["PaperSessionReadResponse"];

const sessionRead: PaperSessionRead = {
	session: {
		account_id: "paper-a",
		created_at: "2026-08-31T09:00:00+08:00",
		pause_reason: null,
		revision: 1,
		session_id: "paper-s-1",
		status: "running",
		strategy_id: "strategy-1",
		trade_date: "2026-08-31",
		updated_at: "2026-08-31T09:01:00+08:00",
	},
	executions: [
		{
			execution_id: "paper-execution:filled",
			fill: {
				assumption_hash: "fill-assumption:sha256:assumption-1",
				commission: 5,
				direction: "buy",
				event_time: "2026-08-31T15:00:00+08:00",
				fill_id: "paper-fill:1",
				fill_price: 10.01,
				instrument_id: 600519,
				market_lineage_hash: "market-lineage:sha256:lineage-1",
				market_snapshot_hash: "market-snapshot:sha256:snapshot-1",
				order_id: "paper-order-1",
				quantity: 100,
				reference_price: 10,
				settlement_date: "2026-09-01",
				slippage: 1,
				tax: 0,
				total_cost: 5.01,
				trade_date: "2026-08-31",
				transfer_fee: 0.01,
			},
			idempotency_key: "operate-1",
			ledger_event_id: "account-event:paper-1",
			order_id: "paper-order-1",
			order_status: "filled",
			reality_status: "filled",
			reason: null,
			request_hash: "paper-request:sha256:request-1",
			status: "replayed",
		},
		{
			execution_id: "paper-execution:deferred",
			fill: null,
			idempotency_key: "operate-2",
			ledger_event_id: null,
			order_id: "paper-order-2",
			order_status: "submitted",
			reality_status: "deferred",
			reason: "limit_up_no_buy",
			request_hash: "paper-request:sha256:request-2",
			status: "replayed",
		},
	],
	latest_reconciliation: {
		balanced: true,
		checksum: "paper-eod:sha256:eod-1",
		fill_count: 1,
		ledger_fill_count: 1,
		order_count: 2,
		reconciled_at: "2026-08-31T16:00:00+08:00",
		reconciliation_id: "paper-reconciliation:1",
		session_id: "paper-s-1",
		trade_date: "2026-08-31",
	},
};

const ledger: PaperLedger = {
	account: {
		account_id: "paper-a",
		account_kind: "paper",
		currency: "CNY",
		name: "主 Paper 账户",
		opened_at: "2026-08-31T09:00:00+08:00",
	},
	events: [],
	snapshot: {
		account_id: "paper-a",
		account_kind: "paper",
		as_of: "2026-08-31",
		cash: { available: "98994.00", frozen: "0.00", settled: "98994.00", total: "98994.00" },
		currency: "CNY",
		event_count: 2,
		ledger_hash: "account-ledger:sha256:paper-ledger-1",
		positions: [],
		realized_pnl: "0.00",
		total_fees: "5.01",
		total_value: "99995.00",
		unrealized_pnl: "0.00",
		valuation_complete: true,
	},
};

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } },
	});
	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

function useReadHandlers() {
	server.use(
		http.get("/api/v1/paper/sessions/paper-s-1", () => HttpResponse.json({ data: sessionRead })),
		http.get("/api/v1/paper/accounts/paper-a/ledger", () => HttpResponse.json({ data: ledger })),
	);
}

describe("PaperAccountWorkspace", () => {
	it("shows session health, execution exceptions, fill lineage, and drift attribution", async () => {
		useReadHandlers();
		render(<PaperAccountWorkspace accountId="paper-a" sessionId="paper-s-1" asOf="2026-08-31" />, {
			wrapper: createWrapper(),
		});

		await screen.findByText("PAPER 模拟账户");
		expect(screen.getByText("RUNNING")).toBeInTheDocument();
		expect(screen.getByText("日终已平衡")).toBeInTheDocument();
		expect(screen.getByText("limit_up_no_buy")).toBeInTheDocument();
		expect(screen.getByText("成交假设与快照血缘")).toBeInTheDocument();
		expect(screen.getByText("fill-assumption:sha256:assumption-1")).toBeInTheDocument();
		expect(screen.getByText("执行偏差归因")).toBeInTheDocument();
		expect(screen.getByText("1 笔未成交 / 推迟")).toBeInTheDocument();
		expect(screen.getByText("account-ledger:sha256:paper-ledger-1")).toBeInTheDocument();
	});

	it("exposes pause, recovery, and EOD reconciliation as explicit operational actions", async () => {
		const user = userEvent.setup();
		const calls = { pause: vi.fn(), recover: vi.fn(), reconcile: vi.fn() };
		useReadHandlers();
		server.use(
			http.post("/api/v1/paper/sessions/paper-s-1/pause", async ({ request }) => {
				calls.pause(await request.json());
				return HttpResponse.json({
					data: { action: "pause", session: { ...sessionRead.session, status: "paused" }, status: "created" },
				});
			}),
			http.post("/api/v1/paper/sessions/paper-s-1/recover", async ({ request }) => {
				calls.recover(await request.json());
				return HttpResponse.json({ data: { idempotency_key: "recover-1", recovered_execution_count: 2 } });
			}),
			http.post("/api/v1/paper/sessions/paper-s-1/reconcile", async ({ request }) => {
				calls.reconcile(await request.json());
				return HttpResponse.json({ data: sessionRead.latest_reconciliation });
			}),
		);

		render(<PaperAccountWorkspace accountId="paper-a" sessionId="paper-s-1" asOf="2026-08-31" />, {
			wrapper: createWrapper(),
		});
		await screen.findByText("会话控制");
		await user.click(screen.getByRole("button", { name: "日终对账" }));
		await screen.findByText("日终对账通过：1/1 笔成交已入账");
		await user.click(screen.getByRole("button", { name: "恢复账本缺口" }));
		await screen.findByText("恢复检查完成：2 条执行记录已核验");
		await user.click(screen.getByRole("button", { name: "暂停会话" }));
		await waitFor(() => expect(calls.pause).toHaveBeenCalled());
		expect(calls.recover).toHaveBeenCalled();
		expect(calls.reconcile).toHaveBeenCalled();
	});

	it("submits a complete deterministic A-share reality input", async () => {
		const user = userEvent.setup();
		let posted: unknown;
		useReadHandlers();
		server.use(
			http.post("/api/v1/paper/sessions/paper-s-1/orders", async ({ request }) => {
				posted = await request.json();
				return HttpResponse.json({ data: sessionRead.executions[0] }, { status: 201 });
			}),
		);

		render(<PaperAccountWorkspace accountId="paper-a" sessionId="paper-s-1" asOf="2026-08-31" />, {
			wrapper: createWrapper(),
		});
		await screen.findByText("模拟订单");
		await user.click(screen.getByRole("button", { name: "提交模拟订单" }));

		await waitFor(() =>
			expect(posted).toMatchObject({
				instrument_id: 600519,
				quantity: 100,
				side: "buy",
				trade_date: "2026-08-31",
				available_quantity: 0,
				assumption: { assumption_id: "paper-default-v1", slippage_bps: 1, version: 1 },
				market: {
					dataset_id: "stock_daily",
					source: "operator-snapshot",
					source_snapshot_id: "paper-ui:2026-08-31:600519",
				},
				rules: { lot_size: 100, settlement_cycle: 1, stamp_duty_rate: 0.0005 },
			}),
		);
	});

	it("submits ETF-specific dataset and fee rules without stock-tax leakage", async () => {
		const user = userEvent.setup();
		let posted: unknown;
		useReadHandlers();
		server.use(
			http.post("/api/v1/paper/sessions/paper-s-1/orders", async ({ request }) => {
				posted = await request.json();
				return HttpResponse.json({ data: sessionRead.executions[0] }, { status: 201 });
			}),
		);

		render(<PaperAccountWorkspace accountId="paper-a" sessionId="paper-s-1" asOf="2026-08-31" />, {
			wrapper: createWrapper(),
		});
		await screen.findByText("模拟订单");
		await user.selectOptions(screen.getByLabelText("Paper 资产类型"), "etf");
		await user.clear(screen.getByLabelText("Paper Instrument ID"));
		await user.type(screen.getByLabelText("Paper Instrument ID"), "510300");
		await user.click(screen.getByRole("button", { name: "提交模拟订单" }));

		await waitFor(() =>
			expect(posted).toMatchObject({
				instrument_id: 510300,
				market: { dataset_id: "etf_daily" },
				rules: {
					asset_class: "etf",
					board_segment: "fund",
					stamp_duty_rate: 0,
				},
			}),
		);
	});

	it("creates an isolated PAPER account and running session during onboarding", async () => {
		const user = userEvent.setup();
		const selected = vi.fn();
		const bodies: unknown[] = [];
		server.use(
			http.post("/api/v1/paper/accounts", async ({ request }) => {
				bodies.push(await request.json());
				return HttpResponse.json(
					{
						data: {
							account_id: "paper-a",
							account_kind: "paper",
							name: "主 Paper 账户",
							opening_event_id: "event-1",
							status: "created",
						},
					},
					{ status: 201 },
				);
			}),
			http.post("/api/v1/paper/sessions", async ({ request }) => {
				bodies.push(await request.json());
				return HttpResponse.json(
					{ data: { action: "start", session: sessionRead.session, status: "created" } },
					{ status: 201 },
				);
			}),
		);

		render(<PaperAccountWorkspace asOf="2026-08-31" onWorkspaceSelected={selected} />, {
			wrapper: createWrapper(),
		});
		await user.type(screen.getByLabelText("Paper 账户 ID"), "paper-a");
		await user.type(screen.getByLabelText("Paper 账户名称"), "主 Paper 账户");
		await user.type(screen.getByLabelText("Paper 会话 ID"), "paper-s-1");
		await user.type(screen.getByLabelText("策略 ID"), "strategy-1");
		await user.type(screen.getByLabelText("期初现金"), "100000");
		await user.click(screen.getByRole("button", { name: "创建 PAPER 账户并启动会话" }));

		await waitFor(() => expect(bodies).toHaveLength(2));
		expect(bodies[0]).toMatchObject({ account_id: "paper-a", initial_cash: "100000" });
		expect(bodies[1]).toMatchObject({ account_id: "paper-a", session_id: "paper-s-1", start_immediately: true });
		expect(selected).toHaveBeenCalledWith("paper-a", "paper-s-1");
	});
});
