import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import type { components } from "@/types/generated/api";
import { ManualAccountWorkspace } from "./manual-account-workspace";

type Ledger = components["schemas"]["AccountLedgerResponse"];

const ledger: Ledger = {
	account: {
		account_id: "manual-a",
		kind: "manual",
		name: "我的实盘记录",
		opened_at: "2026-08-01T00:00:00+08:00",
		currency: "CNY",
	},
	events: [
		{
			account_id: "manual-a",
			account_kind: "manual",
			actor: "local-user",
			attachment_refs: ["broker-confirmation-001"],
			corrects_event_id: null,
			currency: "CNY",
			event_hash: "account-event:sha256:event-001",
			event_id: "event-001",
			event_type: "opening_cash",
			external_reference: null,
			fees: "0.00",
			gross_amount: "100000.00",
			idempotency_key: "opening-cash-001",
			instrument_id: null,
			net_cash: "100000.00",
			note: "券商对账单期初余额",
			price: "0.0000",
			quantity: "0",
			recorded_at: "2026-08-01T08:00:00+08:00",
			replacement_event_type: null,
			reverses_event_id: null,
			settlement_date: "2026-08-01",
			source: "manual_entry",
			tax: "0.00",
			trade_date: "2026-08-01",
		},
	],
	snapshot: {
		account_id: "manual-a",
		account_kind: "manual",
		as_of: "2026-08-31",
		cash: { available: "80885.00", frozen: "0.00", settled: "80885.00", total: "80885.00" },
		currency: "CNY",
		event_count: 3,
		ledger_hash: "account-ledger:sha256:ledger-001",
		positions: [
			{
				available_quantity: "100",
				average_cost: "191.1500",
				instrument_id: 42,
				last_price: "191.1500",
				market_value: "19115.00",
				quantity: "100",
				realized_pnl: "0.00",
				total_fees: "5.00",
				unrealized_pnl: "0.00",
			},
		],
		realized_pnl: "0.00",
		total_fees: "5.00",
		total_value: "100000.00",
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

describe("ManualAccountWorkspace", () => {
	it("shows the immutable identity, rebuilt balances, positions, and integrity evidence", async () => {
		server.use(http.get("/api/v1/manual/accounts/manual-a/ledger", () => HttpResponse.json({ data: ledger })));

		render(<ManualAccountWorkspace accountId="manual-a" asOf="2026-08-31" />, { wrapper: createWrapper() });

		await screen.findByText("MANUAL 手工实际账户");
		expect(screen.getByText("只记录用户确认的实际账户事实")).toBeInTheDocument();
		expect(screen.getByText("80,885.00")).toBeInTheDocument();
		expect(screen.getByText("42")).toBeInTheDocument();
		expect(screen.getByText("account-ledger:sha256:ledger-001")).toBeInTheDocument();
		expect(screen.getByText("不可直接编辑；冲正和更正会追加新事件")).toBeInTheDocument();
	});

	it("previews and records a buy as an immutable event", async () => {
		const user = userEvent.setup();
		let posted: unknown;
		server.use(
			http.get("/api/v1/manual/accounts/manual-a/ledger", () => HttpResponse.json({ data: ledger })),
			http.post("/api/v1/manual/accounts/manual-a/events", async ({ request }) => {
				posted = await request.json();
				return HttpResponse.json(
					{ data: { account: ledger.account, event: ledger.events[0], status: "created" } },
					{ status: 201 },
				);
			}),
		);

		render(<ManualAccountWorkspace accountId="manual-a" asOf="2026-08-31" />, { wrapper: createWrapper() });
		await screen.findByText("流水与数据完整性");

		await user.selectOptions(screen.getByLabelText("事件类型"), "buy");
		await user.clear(screen.getByLabelText("Instrument ID"));
		await user.type(screen.getByLabelText("Instrument ID"), "42");
		await user.clear(screen.getByLabelText("数量"));
		await user.type(screen.getByLabelText("数量"), "100");
		await user.clear(screen.getByLabelText("价格"));
		await user.type(screen.getByLabelText("价格"), "10.00");
		await user.clear(screen.getByLabelText("费用"));
		await user.type(screen.getByLabelText("费用"), "5.00");

		expect(screen.getByText("-1,005.00 CNY")).toBeInTheDocument();
		expect(screen.getByText("+100")).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "记入不可变流水" }));

		await waitFor(() =>
			expect(posted).toMatchObject({
				event_type: "buy",
				instrument_id: 42,
				quantity: "100",
				price: "10.00",
				fees: "5.00",
			}),
		);
		expect(screen.getByText("事件已追加；原记录保持不变")).toBeInTheDocument();
	});

	it("requires a reason and appends a reversal instead of editing the original event", async () => {
		const user = userEvent.setup();
		const reverseRequest = vi.fn();
		server.use(
			http.get("/api/v1/manual/accounts/manual-a/ledger", () => HttpResponse.json({ data: ledger })),
			http.post("/api/v1/manual/accounts/manual-a/reversals", async ({ request }) => {
				reverseRequest(await request.json());
				return HttpResponse.json(
					{ data: { account: ledger.account, event: ledger.events[0], status: "created" } },
					{ status: 201 },
				);
			}),
		);

		render(<ManualAccountWorkspace accountId="manual-a" asOf="2026-08-31" />, { wrapper: createWrapper() });
		await screen.findByText("券商对账单期初余额");
		await user.click(screen.getByRole("button", { name: "冲正 event-001" }));
		expect(screen.getByRole("button", { name: "确认追加冲正" })).toBeDisabled();
		await user.type(screen.getByLabelText("冲正原因"), "期初金额录入错误");
		await user.click(screen.getByRole("button", { name: "确认追加冲正" }));

		await waitFor(() =>
			expect(reverseRequest).toHaveBeenCalledWith(
				expect.objectContaining({ reverses_event_id: "event-001", note: "期初金额录入错误" }),
			),
		);
	});

	it("prefills a correction and posts a complete replacement event", async () => {
		const user = userEvent.setup();
		let correctionBody: unknown;
		server.use(
			http.get("/api/v1/manual/accounts/manual-a/ledger", () => HttpResponse.json({ data: ledger })),
			http.post("/api/v1/manual/accounts/manual-a/corrections", async ({ request }) => {
				correctionBody = await request.json();
				return HttpResponse.json(
					{ data: { account: ledger.account, event: ledger.events[0], status: "created" } },
					{ status: 201 },
				);
			}),
		);

		render(<ManualAccountWorkspace accountId="manual-a" asOf="2026-08-31" />, { wrapper: createWrapper() });
		await screen.findByText("券商对账单期初余额");
		await user.click(screen.getByRole("button", { name: "更正 event-001" }));
		expect(screen.getByText("更正 event-001")).toBeInTheDocument();
		await user.clear(screen.getByLabelText("总额"));
		await user.type(screen.getByLabelText("总额"), "120000");
		await user.click(screen.getByRole("button", { name: "追加更正事件" }));

		await waitFor(() =>
			expect(correctionBody).toMatchObject({
				corrects_event_id: "event-001",
				replacement: { event_type: "opening_cash", gross_amount: "120000", trade_date: "2026-08-01" },
			}),
		);
	});

	it("creates the account and records opening cash during onboarding", async () => {
		const user = userEvent.setup();
		const selected = vi.fn();
		const createdBodies: unknown[] = [];
		server.use(
			http.post("/api/v1/manual/accounts", async ({ request }) => {
				createdBodies.push(await request.json());
				return HttpResponse.json(
					{ data: { account: ledger.account, event: null, status: "created" } },
					{ status: 201 },
				);
			}),
			http.post("/api/v1/manual/accounts/manual-a/events", async ({ request }) => {
				createdBodies.push(await request.json());
				return HttpResponse.json(
					{ data: { account: ledger.account, event: ledger.events[0], status: "created" } },
					{ status: 201 },
				);
			}),
		);

		render(<ManualAccountWorkspace asOf="2026-08-31" onAccountSelected={selected} />, { wrapper: createWrapper() });
		await user.type(screen.getByLabelText("账户 ID"), "manual-a");
		await user.type(screen.getByLabelText("账户名称"), "我的实盘记录");
		await user.clear(screen.getByLabelText("开户日期"));
		await user.type(screen.getByLabelText("开户日期"), "2026-08-01");
		await user.type(screen.getByLabelText("期初现金"), "100000");
		await user.click(screen.getByRole("button", { name: "创建 MANUAL 账户并入账" }));

		await waitFor(() => expect(createdBodies).toHaveLength(2));
		expect(createdBodies[1]).toMatchObject({ event_type: "opening_cash", gross_amount: "100000" });
		expect(selected).toHaveBeenCalledWith("manual-a");
	});
});
