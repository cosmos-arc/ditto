import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { FillLedgerList } from "./fill-ledger-list";

interface TestFill {
	readonly fill_id: string;
	readonly intent_id: string;
	readonly strategy_id: string;
	readonly trade_date: string;
	readonly instrument_id: number;
	readonly direction: "buy" | "sell";
	readonly quantity: number;
	readonly fill_price: number;
	readonly fee: number;
	readonly slippage: number;
	readonly notes: string;
	readonly settlement_date: string;
}

interface TestAdjustment {
	readonly adjustment_id: string;
	readonly fill_id: string;
	readonly adjustment_type: "void" | "replace";
	readonly replacement_fill_id: string | null;
	readonly reason: string;
	readonly created_at: string;
}

const ORIGINAL_FILL: TestFill = {
	fill_id: "fill-original",
	intent_id: "intent-001",
	strategy_id: "strategy-r1",
	trade_date: "2026-07-02",
	instrument_id: 510300,
	direction: "buy",
	quantity: 1000,
	fill_price: 4.32,
	fee: 1.5,
	slippage: 0.02,
	notes: "incorrect broker copy",
	settlement_date: "2026-07-03",
};

const REPLACEMENT_FILL: TestFill = {
	...ORIGINAL_FILL,
	fill_id: "fill-replacement",
	quantity: 800,
	fill_price: 4.31,
	fee: 1.2,
	slippage: 0.01,
	notes: "broker-confirmed replacement",
};

const REPLACE_ADJUSTMENT: TestAdjustment = {
	adjustment_id: "adjustment-replace-001",
	fill_id: ORIGINAL_FILL.fill_id,
	adjustment_type: "replace",
	replacement_fill_id: REPLACEMENT_FILL.fill_id,
	reason: "券商回单数量修正",
	created_at: "2026-07-16T09:31:00+08:00",
};

function createWrapper() {
	const queryClient = new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
			mutations: { retry: false },
		},
	});

	return function Wrapper({ children }: { readonly children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

function useLedgerHandlers(options: {
	readonly raw?: readonly TestFill[];
	readonly effective?: readonly TestFill[];
	readonly adjustments?: readonly TestAdjustment[];
}) {
	const { raw = [ORIGINAL_FILL], effective = raw, adjustments = [] } = options;
	server.use(
		http.get("/api/v1/trade/fills", () => HttpResponse.json({ data: raw })),
		http.get("/api/v1/trade/fills/effective", () => HttpResponse.json({ data: effective })),
		http.get("/api/v1/trade/fill-adjustments", () => HttpResponse.json({ data: adjustments })),
	);
}

beforeEach(() => {
	vi.stubEnv("VITE_USE_MOCK", "false");
});

describe("append-only fill correction ledger", () => {
	it("keeps replaced raw evidence visible and exposes correction actions only on effective fills", async () => {
		useLedgerHandlers({
			raw: [ORIGINAL_FILL, REPLACEMENT_FILL],
			effective: [REPLACEMENT_FILL],
			adjustments: [REPLACE_ADJUSTMENT],
		});

		render(<FillLedgerList />, { wrapper: createWrapper() });

		const originalRow = await screen.findByRole("listitem", { name: /fill-original/ });
		expect(within(originalRow).getByText("已替换")).toBeInTheDocument();
		expect(within(originalRow).getByText("券商回单数量修正")).toBeInTheDocument();
		expect(within(originalRow).getByText(/fill-replacement/)).toBeInTheDocument();
		expect(within(originalRow).queryByRole("button", { name: /成交 fill-original/ })).not.toBeInTheDocument();

		const replacementRow = screen.getByRole("listitem", { name: /fill-replacement/ });
		expect(within(replacementRow).getByText("有效")).toBeInTheDocument();
		expect(within(replacementRow).getByRole("button", { name: "作废成交 fill-replacement" })).toBeEnabled();
		expect(within(replacementRow).getByRole("button", { name: "替换成交 fill-replacement" })).toBeEnabled();
	});

	it("fails closed when effective membership contradicts append-only adjustment evidence", async () => {
		useLedgerHandlers({
			effective: [ORIGINAL_FILL],
			adjustments: [{ ...REPLACE_ADJUSTMENT, adjustment_type: "void", replacement_fill_id: null }],
		});
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const row = await screen.findByRole("listitem", { name: /fill-original/ });
		expect(within(row).getByText("证据冲突")).toBeInTheDocument();
		expect(within(row).getByText(/同时返回有效成交与更正证据/u)).toBeInTheDocument();
		expect(within(row).queryByRole("button", { name: /成交 fill-original/u })).not.toBeInTheDocument();
	});

	it("shows a ledger-wide audit warning and blocks correction when replacement raw evidence is missing", async () => {
		useLedgerHandlers({
			raw: [ORIGINAL_FILL],
			effective: [],
			adjustments: [{ ...REPLACE_ADJUSTMENT, replacement_fill_id: "fill-missing" }],
		});
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const warning = await screen.findByRole("alert", { name: "成交证据一致性告警" });
		expect(warning).toHaveTextContent("发现 1 项成交证据一致性问题");
		expect(warning).toHaveTextContent("替换成交缺少原始证据");
		expect(warning).toHaveTextContent("fill-missing");
		const originalRow = screen.getByRole("listitem", { name: /fill-original/u });
		expect(within(originalRow).getByText("证据冲突")).toBeInTheDocument();
		expect(within(originalRow).queryByRole("button", { name: /成交 fill-original/u })).not.toBeInTheDocument();
	});

	it("marks both sides non-actionable when a replacement is neither effective nor further adjusted", async () => {
		useLedgerHandlers({
			raw: [ORIGINAL_FILL, REPLACEMENT_FILL],
			effective: [],
			adjustments: [REPLACE_ADJUSTMENT],
		});
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const warning = await screen.findByRole("alert", { name: "成交证据一致性告警" });
		expect(warning).toHaveTextContent("替换成交未进入有效链");
		for (const fillId of [ORIGINAL_FILL.fill_id, REPLACEMENT_FILL.fill_id]) {
			const row = screen.getByRole("listitem", { name: new RegExp(fillId, "u") });
			expect(within(row).getByText("证据冲突")).toBeInTheDocument();
			expect(within(row).queryByRole("button", { name: new RegExp(`成交 ${fillId}`, "u") })).not.toBeInTheDocument();
		}
	});

	it("keeps orphan adjustment evidence visible even when no raw fill row exists", async () => {
		const orphan = {
			...REPLACE_ADJUSTMENT,
			adjustment_id: "adjustment-orphan-001",
			fill_id: "fill-orphan",
			replacement_fill_id: "fill-missing",
		};
		useLedgerHandlers({ raw: [], effective: [], adjustments: [orphan] });
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const warning = await screen.findByRole("alert", { name: "成交证据一致性告警" });
		expect(warning).toHaveTextContent("更正事件缺少原始成交");
		expect(warning).toHaveTextContent("adjustment-orphan-001");
		expect(warning).toHaveTextContent("fill-orphan");
		expect(screen.queryByRole("list", { name: "手工成交记录" })).not.toBeInTheDocument();
	});

	it("renders an effective ghost as synthetic unresolved evidence without correction actions", async () => {
		const ghost = { ...ORIGINAL_FILL, fill_id: "fill-ghost" };
		useLedgerHandlers({ raw: [], effective: [ghost], adjustments: [] });
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const warning = await screen.findByRole("alert", { name: "成交证据一致性告警" });
		expect(warning).toHaveTextContent("有效成交缺少原始流水");
		const ghostRow = screen.getByRole("listitem", { name: /fill-ghost/u });
		expect(within(ghostRow).getByText("证据冲突")).toBeInTheDocument();
		expect(within(ghostRow).queryByRole("button", { name: /成交 fill-ghost/u })).not.toBeInTheDocument();
	});

	it("keeps a coherent multi-hop replacement chain actionable only at its effective tip", async () => {
		const middle = { ...REPLACEMENT_FILL, fill_id: "fill-middle" };
		const final = { ...REPLACEMENT_FILL, fill_id: "fill-final", quantity: 700 };
		useLedgerHandlers({
			raw: [ORIGINAL_FILL, middle, final],
			effective: [final],
			adjustments: [
				{ ...REPLACE_ADJUSTMENT, replacement_fill_id: middle.fill_id },
				{
					...REPLACE_ADJUSTMENT,
					adjustment_id: "adjustment-replace-002",
					fill_id: middle.fill_id,
					replacement_fill_id: final.fill_id,
				},
			],
		});
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await screen.findByRole("listitem", { name: /fill-final/u });
		expect(screen.queryByRole("alert", { name: "成交证据一致性告警" })).not.toBeInTheDocument();
		for (const fillId of [ORIGINAL_FILL.fill_id, middle.fill_id]) {
			const row = screen.getByRole("listitem", { name: new RegExp(fillId, "u") });
			expect(within(row).getByText("已替换")).toBeInTheDocument();
			expect(within(row).queryByRole("button", { name: new RegExp(`成交 ${fillId}`, "u") })).not.toBeInTheDocument();
		}
		const finalRow = screen.getByRole("listitem", { name: /fill-final/u });
		expect(within(finalRow).getByRole("button", { name: "作废成交 fill-final" })).toBeEnabled();
		expect(within(finalRow).getByRole("button", { name: "替换成交 fill-final" })).toBeEnabled();
	});

	it("requires a reason and posts an idempotent void event without mutating the original fill", async () => {
		useLedgerHandlers({});
		const submitted: unknown[] = [];
		server.use(
			http.post("/api/v1/trade/fills/:fillId/void", async ({ params, request }) => {
				const body = await request.json();
				submitted.push(body);
				return HttpResponse.json({
					data: {
						...(body as Record<string, unknown>),
						fill_id: params.fillId,
						adjustment_type: "void",
						replacement_fill_id: null,
						created_at: "2026-07-16T10:00:00+08:00",
					},
				});
			}),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const trigger = await screen.findByRole("button", { name: "作废成交 fill-original" });
		await user.click(trigger);
		const dialog = await screen.findByRole("dialog", { name: "作废成交" });
		await user.click(within(dialog).getByRole("button", { name: "确认追加作废" }));

		expect(within(dialog).getByRole("alert")).toHaveTextContent("请填写更正原因");
		expect(submitted).toHaveLength(0);

		await user.type(within(dialog).getByLabelText("更正原因"), "重复录入券商回单");
		await user.click(within(dialog).getByRole("button", { name: "确认追加作废" }));

		await waitFor(() => expect(submitted).toHaveLength(1));
		expect(submitted[0]).toMatchObject({ reason: "重复录入券商回单" });
		expect(submitted[0]).toHaveProperty("adjustment_id", expect.stringMatching(/^adjustment-void-fill-original-/u));
		await expect(screen.findByRole("status", { name: "成交更正结果" })).resolves.toHaveTextContent(
			"fill-original 已追加作废",
		);
	});

	it("posts a linked replacement fill and restores focus when the correction sheet closes", async () => {
		useLedgerHandlers({});
		const submitted: unknown[] = [];
		server.use(
			http.post("/api/v1/trade/fills/:fillId/replace", async ({ params, request }) => {
				const body = await request.json();
				submitted.push(body);
				return HttpResponse.json({
					data: {
						adjustment_id: (body as Record<string, unknown>).adjustment_id,
						fill_id: params.fillId,
						adjustment_type: "replace",
						replacement_fill_id: (body as Record<string, unknown>).replacement_fill_id,
						reason: (body as Record<string, unknown>).reason,
						created_at: "2026-07-16T10:01:00+08:00",
					},
				});
			}),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const trigger = await screen.findByRole("button", { name: "替换成交 fill-original" });
		await user.click(trigger);
		const dialog = await screen.findByRole("dialog", { name: "替换成交" });
		expect(within(dialog).getByLabelText("替换成交数量")).toHaveValue(String(ORIGINAL_FILL.quantity));
		expect(within(dialog).getByLabelText("替换成交价格")).toHaveValue(String(ORIGINAL_FILL.fill_price));

		await user.clear(within(dialog).getByLabelText("替换成交数量"));
		await user.type(within(dialog).getByLabelText("替换成交数量"), "800");
		await user.type(within(dialog).getByLabelText("更正原因"), "券商确认部分成交为 800 股");
		await user.click(within(dialog).getByRole("button", { name: "确认追加替换" }));

		await waitFor(() => expect(submitted).toHaveLength(1));
		expect(submitted[0]).toMatchObject({
			quantity: 800,
			fill_price: ORIGINAL_FILL.fill_price,
			reason: "券商确认部分成交为 800 股",
		});
		expect(submitted[0]).toHaveProperty("adjustment_id", expect.stringMatching(/^adjustment-replace-fill-original-/u));
		expect(submitted[0]).toHaveProperty(
			"replacement_fill_id",
			expect.stringMatching(/^fill-fill-original-replacement-/u),
		);
		await waitFor(() => expect(screen.queryByRole("dialog", { name: "替换成交" })).not.toBeInTheDocument());
		expect(trigger).toHaveFocus();
	});

	it("reuses the same idempotency keys when an unknown network result is retried", async () => {
		useLedgerHandlers({});
		const submitted: Record<string, unknown>[] = [];
		server.use(
			http.post("/api/v1/trade/fills/:fillId/replace", async ({ params, request }) => {
				const body = (await request.json()) as Record<string, unknown>;
				submitted.push(body);
				if (submitted.length === 1) return HttpResponse.error();
				return HttpResponse.json({
					data: {
						adjustment_id: body.adjustment_id,
						fill_id: params.fillId,
						adjustment_type: "replace",
						replacement_fill_id: body.replacement_fill_id,
						reason: body.reason,
						created_at: "2026-07-16T10:02:00+08:00",
					},
				});
			}),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "替换成交 fill-original" }));
		const dialog = await screen.findByRole("dialog", { name: "替换成交" });
		await user.type(within(dialog).getByLabelText("更正原因"), "网络中断后安全重试");
		await user.click(within(dialog).getByRole("button", { name: "确认追加替换" }));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("提交结果未知");
		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		expect(dialog).toBeInTheDocument();
		await user.keyboard("{Escape}");
		expect(dialog).toBeInTheDocument();
		await user.click(within(dialog).getByRole("button", { name: "Close" }));
		expect(dialog).toBeInTheDocument();
		await user.click(within(dialog).getByRole("button", { name: "使用同一标识重试" }));
		await waitFor(() => expect(submitted).toHaveLength(2));
		expect(submitted[1]).toEqual(submitted[0]);
		await expect(screen.findByRole("status", { name: "成交更正结果" })).resolves.toHaveTextContent(
			"fill-original 已追加替换",
		);
	});

	it("treats HTTP 503 as an unknown result and retries the identical correction command", async () => {
		useLedgerHandlers({});
		const submitted: Record<string, unknown>[] = [];
		server.use(
			http.post("/api/v1/trade/fills/:fillId/replace", async ({ params, request }) => {
				const body = (await request.json()) as Record<string, unknown>;
				submitted.push(body);
				if (submitted.length === 1) {
					return HttpResponse.json({ detail: "upstream timeout" }, { status: 503 });
				}
				return HttpResponse.json({
					data: {
						adjustment_id: body.adjustment_id,
						fill_id: params.fillId,
						adjustment_type: "replace",
						replacement_fill_id: body.replacement_fill_id,
						reason: body.reason,
						created_at: "2026-07-16T10:02:30+08:00",
					},
				});
			}),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "替换成交 fill-original" }));
		const dialog = await screen.findByRole("dialog", { name: "替换成交" });
		await user.type(within(dialog).getByLabelText("更正原因"), "503 后安全重试");
		await user.click(within(dialog).getByRole("button", { name: "确认追加替换" }));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("提交结果未知");
		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		await user.keyboard("{Escape}");
		await user.click(within(dialog).getByRole("button", { name: "Close" }));
		expect(dialog).toBeInTheDocument();
		await user.click(within(dialog).getByRole("button", { name: "使用同一标识重试" }));

		await waitFor(() => expect(submitted).toHaveLength(2));
		expect(submitted[1]).toEqual(submitted[0]);
		await expect(screen.findByRole("status", { name: "成交更正结果" })).resolves.toHaveTextContent(
			"fill-original 已追加替换",
		);
	});

	it("keeps the sheet open and explains backend correction conflicts", async () => {
		useLedgerHandlers({});
		server.use(
			http.post("/api/v1/trade/fills/:fillId/void", () =>
				HttpResponse.json(
					{
						detail: "fill fill-original was already adjusted",
						error_code: "fill_adjustment_conflict",
					},
					{ status: 409 },
				),
			),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "作废成交 fill-original" }));
		const dialog = await screen.findByRole("dialog", { name: "作废成交" });
		await user.type(within(dialog).getByLabelText("更正原因"), "重复录入");
		await user.click(within(dialog).getByRole("button", { name: "确认追加作废" }));

		const alert = await within(dialog).findByRole("alert");
		expect(alert).toHaveTextContent("更正冲突");
		expect(alert).toHaveTextContent("fill fill-original was already adjusted");
		expect(dialog).toBeInTheDocument();
	});

	it("treats an explicit HTTP 422 response as a definite failure that may be closed", async () => {
		useLedgerHandlers({});
		server.use(
			http.post("/api/v1/trade/fills/:fillId/void", () =>
				HttpResponse.json({ detail: "更正原因不符合规则" }, { status: 422 }),
			),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "作废成交 fill-original" }));
		const dialog = await screen.findByRole("dialog", { name: "作废成交" });
		await user.type(within(dialog).getByLabelText("更正原因"), "确定失败可修改");
		await user.click(within(dialog).getByRole("button", { name: "确认追加作废" }));

		await expect(within(dialog).findByRole("alert")).resolves.toHaveTextContent("成交更正失败：更正原因不符合规则");
		expect(within(dialog).queryByRole("button", { name: "使用同一标识重试" })).not.toBeInTheDocument();
		expect(within(dialog).getByRole("button", { name: "取消" })).toBeEnabled();
		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		await waitFor(() => expect(screen.queryByRole("dialog", { name: "作废成交" })).not.toBeInTheDocument());
	});

	it("blocks every close path while a correction request is pending", async () => {
		useLedgerHandlers({});
		let releaseResponse: () => void = () => undefined;
		const responseGate = new Promise<void>((resolve) => {
			releaseResponse = resolve;
		});
		server.use(
			http.post("/api/v1/trade/fills/:fillId/void", async ({ params, request }) => {
				const body = (await request.json()) as Record<string, unknown>;
				await responseGate;
				return HttpResponse.json({
					data: {
						...body,
						fill_id: params.fillId,
						adjustment_type: "void",
						replacement_fill_id: null,
						created_at: "2026-07-16T10:03:00+08:00",
					},
				});
			}),
		);
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "作废成交 fill-original" }));
		const dialog = await screen.findByRole("dialog", { name: "作废成交" });
		await user.type(within(dialog).getByLabelText("更正原因"), "等待后端确认");
		await user.click(within(dialog).getByRole("button", { name: "确认追加作废" }));
		await expect(within(dialog).findByRole("button", { name: "追加中" })).resolves.toBeDisabled();

		await user.click(within(dialog).getByRole("button", { name: "取消" }));
		await user.keyboard("{Escape}");
		await user.click(within(dialog).getByRole("button", { name: "Close" }));
		expect(dialog).toBeInTheDocument();

		releaseResponse();
		await expect(screen.findByRole("status", { name: "成交更正结果" })).resolves.toHaveTextContent(
			"fill-original 已追加作废",
		);
	});

	it("keeps long immutable fill and intent identifiers readable in the narrow Sheet", async () => {
		const longFill: TestFill = {
			...ORIGINAL_FILL,
			fill_id: "fill-20260716-510300-manual-broker-confirmation-00000000000000000001",
			intent_id: "intent-seed-etf-industry-rotation-20260716-510300-00000000000000000001",
		};
		useLedgerHandlers({ raw: [longFill], effective: [longFill] });
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: `替换成交 ${longFill.fill_id}` }));
		const dialog = await screen.findByRole("dialog", { name: "替换成交" });
		const evidence = within(dialog).getByRole("region", { name: "不可变原始成交证据" });
		expect(within(evidence).getByText(longFill.fill_id)).toHaveClass("min-w-0", "break-all");
		expect(within(evidence).getByText(longFill.intent_id)).toHaveClass("min-w-0", "break-all");
	});

	it("uses AA evidence text tokens on Sheet overlay surfaces", async () => {
		useLedgerHandlers({});
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "替换成交 fill-original" }));
		const dialog = await screen.findByRole("dialog", { name: "替换成交" });
		const evidence = within(dialog).getByRole("region", { name: "不可变原始成交证据" });
		expect(within(evidence).getByText(ORIGINAL_FILL.fill_id)).toHaveClass("text-(--color-foreground-secondary)");
		expect(within(evidence).getByText("意图")).toHaveClass("text-(--color-foreground-secondary)");
		expect(within(evidence).getByText(ORIGINAL_FILL.notes)).toHaveClass("text-(--color-foreground-secondary)");
		expect(within(dialog).getByText("更正事件 ID")).toHaveClass("text-(--color-foreground-secondary)");
		expect(within(dialog).getByText("替换成交 ID")).toHaveClass("text-(--color-foreground-secondary)");
	});

	it("closes with Escape and restores keyboard focus to the invoking action", async () => {
		useLedgerHandlers({});
		const user = userEvent.setup();
		render(<FillLedgerList />, { wrapper: createWrapper() });

		const trigger = await screen.findByRole("button", { name: "作废成交 fill-original" });
		await user.click(trigger);
		await expect(screen.findByRole("dialog", { name: "作废成交" })).resolves.toBeInTheDocument();
		await user.keyboard("{Escape}");

		await waitFor(() => expect(screen.queryByRole("dialog", { name: "作废成交" })).not.toBeInTheDocument());
		expect(trigger).toHaveFocus();
	});
});
