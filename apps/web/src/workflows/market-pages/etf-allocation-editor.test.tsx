import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { afterEach, expect, it } from "vitest";
import type { ETFCandidate } from "@/features/instruments";
import { server } from "@/mocks/server";
import { ETFAllocationEditor } from "./etf-allocation-editor";

function wrapper() {
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return ({ children }: { children: ReactNode }) => (
		<QueryClientProvider client={client}>{children}</QueryClientProvider>
	);
}

const candidate: ETFCandidate = {
	instrumentId: 1,
	name: "沪深300 ETF",
	ticker: "510300",
	exchange: "SSE",
	isActiveCurrent: true,
	fields: {},
	tracking: null,
};

afterEach(() => window.history.replaceState(null, "", "/"));

it("retries one save with the same identity and restores the saved version", async () => {
	const user = userEvent.setup();
	const attempts: Array<{ id: string; key: string }> = [];
	const reviewAttempts: Array<{ action: string; key: string }> = [];
	let stored: Record<string, unknown> | null = null;
	server.use(
		http.get("/api/v1/paper/accounts", () =>
			HttpResponse.json({
				data: {
					accounts: [
						{
							account_id: "paper-a",
							account_kind: "paper",
							account_name: "模拟账户",
							currency: "CNY",
							opened_at: "2026-09-01T00:00:00Z",
						},
					],
				},
			}),
		),
		http.get("/api/v1/portfolio/etf-allocations/:id/versions", () =>
			HttpResponse.json({ data: stored ? [stored] : [] }),
		),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions", async ({ params, request }) => {
			attempts.push({ id: String(params["id"]), key: request.headers.get("Idempotency-Key") ?? "" });
			if (attempts.length === 1) return HttpResponse.json({ error: { code: "TEMPORARY" } }, { status: 503 });
			const body = (await request.json()) as Record<string, unknown>;
			stored = {
				version_id: "version-one",
				allocation_id: String(params["id"]),
				parent_version_id: null,
				asof: body["asof"],
				knowledge_cutoff: body["knowledge_cutoff"],
				source_snapshot_id: body["source_snapshot_id"],
				mode: "equal",
				weights: { "1": "0.80000000" },
				cash_weight: "0.2",
				max_position_weight: "1",
				tracking_exposure: { "000300.SH": "0.80000000" },
				reason: "broad exposure",
				rule_version: "etf-allocation-v1",
				paper_status: "research_only",
				review_status: "research_only",
				created_at: "2026-09-01T09:00:00Z",
			};
			return HttpResponse.json({ data: stored }, { status: 201 });
		}),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions/:versionId/review", async ({ request }) => {
			const body = (await request.json()) as { action: string };
			reviewAttempts.push({ action: body.action, key: request.headers.get("Idempotency-Key") ?? "" });
			if (reviewAttempts.length === 1) return HttpResponse.json({ error: { code: "TEMPORARY" } }, { status: 503 });
			stored = { ...stored, review_status: body.action === "submit" ? "review_pending" : "review_approved" };
			return HttpResponse.json({ data: stored });
		}),
	);
	const editor = (
		<ETFAllocationEditor
			items={[candidate]}
			asof="2026-09-01"
			cutoff="2026-09-01T09:00:00Z"
			cutoffInput="2026-09-01T17:00:00"
			snapshot="snapshot:recorded:etf"
		/>
	);
	const view = render(editor, { wrapper: wrapper() });
	await user.click(screen.getByRole("checkbox", { name: /沪深300 ETF/ }));
	await user.clear(screen.getByLabelText("单仓上限"));
	await user.type(screen.getByLabelText("单仓上限"), "1");
	await user.type(screen.getByLabelText("配置理由"), "broad exposure");
	await user.click(screen.getByRole("button", { name: "保存候选版本" }));
	await screen.findByRole("alert");
	view.unmount();
	const restored = render(editor, { wrapper: wrapper() });
	expect(screen.getByRole("checkbox", { name: /沪深300 ETF/ })).toBeChecked();
	expect(screen.getByLabelText("配置理由")).toHaveValue("broad exposure");
	await user.click(screen.getByRole("button", { name: "保存候选版本" }));
	await screen.findByText(/已保存 version-one/);
	expect(attempts).toHaveLength(2);
	expect(attempts[0]).toEqual(attempts[1]);
	expect(new URLSearchParams(window.location.search).get("etfVersion")).toBe("version-one");
	expect(screen.getByText(/审查批准只确认精确版本/)).toBeInTheDocument();
	await user.type(screen.getByLabelText("审查人"), "operator");
	await user.type(screen.getByLabelText("审查理由"), "checked");
	await user.click(screen.getByRole("button", { name: "提交审查" }));
	await screen.findByText(/审查失败/);
	restored.unmount();
	render(editor, { wrapper: wrapper() });
	await screen.findByRole("button", { name: "提交审查" });
	await user.type(screen.getByLabelText("审查人"), "operator");
	await user.type(screen.getByLabelText("审查理由"), "checked");
	await user.click(screen.getByRole("button", { name: "提交审查" }));
	await screen.findByRole("button", { name: "研究审查通过" });
	expect(reviewAttempts[0]).toEqual(reviewAttempts[1]);
	await user.click(screen.getByRole("button", { name: "研究审查通过" }));
	await screen.findByText(/· review_approved ·/);
	expect(reviewAttempts[2]?.action).toBe("approve");
	const handoffAttempts: string[] = [];
	const executionAttempts: string[] = [];
	server.use(
		http.post("/api/v1/portfolio/etf-allocations/:id/versions/:versionId/paper-authorizations", async ({ request }) => {
			const body = (await request.json()) as { account_id: string; session_id: string; intended_trade_date: string };
			expect(body.account_id).toBe("paper-a");
			expect(body.intended_trade_date).toBe("2026-09-02");
			return HttpResponse.json(
				{ data: { version_id: "version-one", authorization_id: "version-one:paper:receipt" } },
				{ status: 201 },
			);
		}),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions/:versionId/paper-handoffs", async ({ request }) => {
			const body = (await request.json()) as { account_id: string; session_id: string; intended_trade_date: string };
			handoffAttempts.push(request.headers.get("Idempotency-Key") ?? "");
			if (handoffAttempts.length === 1) return HttpResponse.json({ error: { code: "TEMPORARY" } }, { status: 503 });
			return HttpResponse.json(
				{
					data: {
						action: "start",
						status: "created",
						session: {
							account_id: body.account_id,
							session_id: body.session_id,
							strategy_id: `etf-allocation:${new URLSearchParams(window.location.search).get("etfAllocation")}`,
							trade_date: body.intended_trade_date,
							status: "running",
							revision: 1,
							created_at: "2026-09-01T09:00:00Z",
							updated_at: "2026-09-01T09:00:00Z",
							pause_reason: null,
						},
					},
				},
				{ status: 201 },
			);
		}),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions/:versionId/paper-executions", async ({ request }) => {
			const body = (await request.json()) as Record<string, unknown>;
			expect(body["authorization_id"]).toBe("version-one:paper:receipt");
			expect(body["market_snapshot_id"]).toBe("bar-snapshot");
			executionAttempts.push(request.headers.get("Idempotency-Key") ?? "");
			if (executionAttempts.length === 1) return HttpResponse.json({ error: { code: "TEMPORARY" } }, { status: 503 });
			return HttpResponse.json(
				{
					data: {
						outcomes: [
							{
								intent_id: "intent-1",
								instrument_id: 1,
								status: "filled",
								reason: null,
								execution_id: "execution-1",
								ledger_event_id: "event-1",
							},
						],
					},
				},
				{ status: 201 },
			);
		}),
	);
	await user.selectOptions(await screen.findByLabelText("Paper 账户"), "paper-a");
	fireEvent.change(screen.getByLabelText("下一交易日"), { target: { value: "2026-09-02" } });
	await user.type(screen.getByLabelText("Paper 授权人"), "operator");
	await user.type(screen.getByLabelText("Paper 授权理由"), "approved for Paper");
	await user.click(screen.getByRole("button", { name: "授权此版本进入 Paper" }));
	await screen.findByRole("button", { name: "创建 Paper 会话" });
	await user.click(screen.getByRole("button", { name: "创建 Paper 会话" }));
	await screen.findByText(/交接失败/);
	// A refresh retains the exact session and retry key after an uncertain response.
	restored.unmount();
	render(editor, { wrapper: wrapper() });
	await user.click(await screen.findByRole("button", { name: "创建 Paper 会话" }));
	const paperLink = await screen.findByRole("link", { name: "查看 Paper 账户" });
	expect(paperLink).toHaveAttribute("href", expect.stringContaining("/portfolio/paper?account_id=paper-a"));
	expect(handoffAttempts).toHaveLength(2);
	expect(handoffAttempts[0]).toBe(handoffAttempts[1]);
	fireEvent.change(screen.getByLabelText("执行日证据截止时间"), { target: { value: "2026-09-02T17:00" } });
	await user.type(screen.getByLabelText("执行日 ETF 参考快照 ID"), "reference-snapshot");
	await user.type(screen.getByLabelText("执行日 ETF 行情快照 ID"), "bar-snapshot");
	await user.click(screen.getByRole("button", { name: "按已批准意图模拟成交" }));
	await screen.findByText(/Paper 执行失败/);
	await user.click(screen.getByRole("button", { name: "按已批准意图模拟成交" }));
	await screen.findByText(/账本事件 event-1/);
	expect(executionAttempts).toHaveLength(2);
	expect(executionAttempts[0]).toBe(executionAttempts[1]);
});

it("asks for confirmation before the terminal reject transition", async () => {
	const user = userEvent.setup();
	const actions: string[] = [];
	let stored: Record<string, unknown> | null = null;
	server.use(
		http.get("/api/v1/portfolio/etf-allocations/:id/versions", () =>
			HttpResponse.json({ data: stored ? [stored] : [] }),
		),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions", async ({ params }) => {
			stored = {
				version_id: "version-one",
				allocation_id: String(params["id"]),
				parent_version_id: null,
				asof: "2026-09-01",
				knowledge_cutoff: "2026-09-01T09:00:00Z",
				source_snapshot_id: "snapshot:recorded:etf",
				mode: "equal",
				weights: { "1": "0.80000000" },
				cash_weight: "0.2",
				max_position_weight: "1",
				tracking_exposure: { "000300.SH": "0.80000000" },
				reason: "broad exposure",
				rule_version: "etf-allocation-v1",
				paper_status: "research_only",
				review_status: "research_only",
				created_at: "2026-09-01T09:00:00Z",
			};
			return HttpResponse.json({ data: stored }, { status: 201 });
		}),
		http.post("/api/v1/portfolio/etf-allocations/:id/versions/:versionId/review", async ({ request }) => {
			const body = (await request.json()) as { action: string };
			actions.push(body.action);
			stored = {
				...stored,
				review_status: body.action === "submit" ? "review_pending" : "rejected",
			};
			return HttpResponse.json({ data: stored });
		}),
	);
	render(
		<ETFAllocationEditor
			items={[candidate]}
			asof="2026-09-01"
			cutoff="2026-09-01T09:00:00Z"
			cutoffInput="2026-09-01T17:00:00"
			snapshot="snapshot:recorded:etf"
		/>,
		{ wrapper: wrapper() },
	);
	await user.click(screen.getByRole("checkbox", { name: /沪深300 ETF/ }));
	await user.clear(screen.getByLabelText("单仓上限"));
	await user.type(screen.getByLabelText("单仓上限"), "1");
	await user.type(screen.getByLabelText("配置理由"), "broad exposure");
	await user.click(screen.getByRole("button", { name: "保存候选版本" }));
	await screen.findByText(/已保存 version-one/);
	await user.type(screen.getByLabelText("审查人"), "operator");
	await user.type(screen.getByLabelText("审查理由"), "checked");
	await user.click(screen.getByRole("button", { name: "提交审查" }));
	await screen.findByRole("button", { name: "研究审查通过" });
	expect(actions).toEqual(["submit"]);
	await user.click(screen.getByRole("button", { name: "拒绝此版本" }));
	expect(screen.getByRole("button", { name: "确认拒绝" })).toBeInTheDocument();
	await user.click(screen.getByRole("button", { name: "取消" }));
	expect(screen.getByRole("button", { name: "拒绝此版本" })).toBeInTheDocument();
	expect(actions).toEqual(["submit"]);
	await user.click(screen.getByRole("button", { name: "拒绝此版本" }));
	await user.click(screen.getByRole("button", { name: "确认拒绝" }));
	await screen.findByText(/· rejected ·/);
	expect(actions).toEqual(["submit", "reject"]);
});
